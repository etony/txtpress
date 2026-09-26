# -*- coding: utf-8 -*-
"""
TxtPress — 后台工作线程，带进度、状态、取消支持的 QThread。

为什么需要这个？
PyQt 的界面（GUI）和后台任务不能在同一个线程里跑。
如果把耗时操作（如文件转换）放在主线程，界面会卡死。
这个 worker 把任务扔到子线程，通过信号把进度/结果传回主线程。

工作模式：
1. 业务方定义一个 target 函数，签名 target(progress, status, *args)
2. 创建 ProgressWorker，传入 target
3. 连接 worker 的信号到 UI 更新函数
4. worker.start() 在子线程执行 target
5. worker 通过信号通知 UI：进度更新、状态更新、任务完成

取消机制：
- 主线程调用 worker.cancel() 设置 _cancelled = True
- 子线程的 progress 回调检查 _cancelled，如果为 True 则抛出 CancelledError
- worker 捕获 CancelledError，通过 task_done 的第三态（是否被取消）上报，
  既不算成功也不算失败

学习要点：
  QThread 不能在子线程直接操作 UI 控件（会崩溃）。
  pyqtSignal 是线程安全的，可以把数据从子线程送回主线程。
  lambda 闭包在这里用来注入回调函数，比继承重写更灵活（组合优于继承）。

用法：
    def long_task(progress, status):
        for i in range(10):
            if status: status(f'步骤 {i+1}/10')
            if progress: progress(i+1, 10)
            time.sleep(1)

    worker = ProgressWorker(long_task)
    worker.progress.connect(lambda cur, tot: bar.setRange(0, tot) or bar.setValue(cur))
    worker.status.connect(lambda s: statusbar.showMessage(s))
    worker.task_done.connect(on_done)
    worker.start()
"""

from __future__ import annotations

import threading

from loguru import logger
from PyQt6.QtCore import QThread, pyqtSignal


class CancelledError(Exception):
    """用户取消操作时抛出的异常，与普通错误区分。

    设计意图：
    让业务代码可以在任意 point 响应取消请求。
    业务函数不需要每次迭代都检查 if cancelled，
    只需要在 progress 回调中做这件事即可。
    """


class ProgressWorker(QThread):
    """
    通用后台工作线程，通过信号与主线程通信。

    三个信号的作用：
    - progress:  更新进度条（当前值，总值）
    - status:    更新状态栏文字
    - task_done: 任务结束通知（成功, 错误消息, 是否被取消）

    业务方只需要提供一个 target 函数，签名是：
        target(progress, status, *args, **kwargs)
    progress 和 status 由本 worker 自动注入，业务方直接调用即可。

    为什么不用 QThread 继承 + 重写 run()？
    传统做法是继承 QThread 并在 run() 里写死逻辑，
    但这样每换一个任务就得新建一个子类。
    这个 worker 把任务作为参数传入（策略模式），更灵活。
    """

    # 定义信号。pyqtSignal 在类级别定义，PyQt 元类自动处理。
    # 注意：不能叫 finished——那会遮蔽 QThread 内置的 finished() 信号。
    progress = pyqtSignal(int, int)          # (completed, total) 进度
    status = pyqtSignal(str)                 # 状态栏文本
    task_done = pyqtSignal(bool, str, bool)  # (成功, 错误消息, 是否被取消)

    def __init__(self, target, args=None, kwargs=None):
        """
        Args:
            target:  实际干活儿的函数，签名 target(progress, status, *args, **kwargs)
                     progress 和 status 是本 worker 注入的回调函数
                     注意：target 里不要操作 UI 控件，那会导致崩溃。
            args:    传给 target 的额外位置参数
            kwargs:  传给 target 的额外关键字参数
        """
        super().__init__()
        self._target = target
        self._args = args or ()
        self._kwargs = kwargs or {}
        self._cancelled = threading.Event()  # 线程安全的取消标记

    def cancel(self):
        """请求取消操作。

        只是设一个标记，真正的停止逻辑在 progress 回调中处理。
        主线程调用此方法后，子线程在下一次进度更新时才会感知到取消请求。
        """
        self._cancelled.set()

    def run(self):
        """
        QThread 的入口方法，start() 之后自动在子线程执行。

        我们把 progress 和 status 包装成 lambda，注入给 target。
        target 可以像普通函数一样调用它们：
            progress(5, 10)    -> 触发 self.progress.emit(5, 10)
            status('工作中')    -> 触发 self.status.emit('工作中')

        如果用户点了取消，progress 回调抛出 CancelledError，
        run() 捕获后以 task_done 的"被取消"状态上报（既非成功也非失败）。

        注意：lambda 里用 self 没问题，因为 run() 在子线程执行，
        而 self._cancelled 是跨线程共享的一个普通 Python 属性（线程安全不用担心，
        因为在 CPython 中，GIL 保护了简单属性读写的原子性）。
        """
        try:
            self._target(
                progress=lambda c, t: (
                    self.progress.emit(c, t)
                    if not self._cancelled.is_set()
                    # 下面这行是一个 Python 技巧：
                    # (_ for _ in ()).throw(CancelledError())
                    # 创建空生成器 -> 往它里面抛异常 -> 表达式结果为该异常
                    # 这样可以在 lambda 内直接抛出异常，不需要 if/else 分支。
                    else (_ for _ in ()).throw(CancelledError())
                ),
                status=lambda s: self.status.emit(s),
                *self._args,
                **self._kwargs,
            )
            # 没有抛异常 => 成功
            self.task_done.emit(True, '', False)
        except CancelledError:
            # 用户取消：既不是成功也不是错误，单独一种结果
            self.task_done.emit(False, '', True)
        except Exception as e:
            # 任务抛异常了（比如文件不存在、编码错误等），
            # 通过 task_done 信号把异常信息传回主线程。
            logger.exception('后台任务执行失败')
            self.task_done.emit(False, str(e), False)
