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
- worker 捕获 CancelledError，当作正常完成处理

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
    worker.finished.connect(on_done)
    worker.start()
"""

from __future__ import annotations

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
    - progress: 更新进度条（当前值，总值）
    - status:   更新状态栏文字
    - finished: 任务结束通知（成功/失败，错误信息）

    业务方只需要提供一个 target 函数，签名是：
        target(progress, status, *args, **kwargs)
    progress 和 status 由本 worker 自动注入，业务方直接调用即可。

    为什么不用 QThread 继承 + 重写 run()？
    传统做法是继承 QThread 并在 run() 里写死逻辑，
    但这样每换一个任务就得新建一个子类。
    这个 worker 把任务作为参数传入（策略模式），更灵活。
    """

    # 定义信号。int,int 和 bool,str 是信号的参数类型。
    # pyqtSignal 在类级别定义，是 PyQt 的元类机制自动处理的。
    progress = pyqtSignal(int, int)   # (completed, total) 进度
    status = pyqtSignal(str)          # 状态栏文本
    finished = pyqtSignal(bool, str)  # (是否成功, 错误消息)

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
        self._cancelled = False  # 用户是否点了取消（线程安全的 bool 标记）

    def cancel(self):
        """请求取消操作。

        只是设一个标记，真正的停止逻辑在 progress 回调中处理。
        主线程调用此方法后，子线程在下一次进度更新时才会感知到取消请求。
        """
        self._cancelled = True

    def run(self):
        """
        QThread 的入口方法，start() 之后自动在子线程执行。

        我们把 progress 和 status 包装成 lambda，注入给 target。
        target 可以像普通函数一样调用它们：
            progress(5, 10)    -> 触发 self.progress.emit(5, 10)
            status('工作中')    -> 触发 self.status.emit('工作中')

        如果用户点了取消，progress 回调抛出 CancelledError，
        run() 捕获后当作成功结束处理。

        注意：lambda 里用 self 没问题，因为 run() 在子线程执行，
        而 self._cancelled 是跨线程共享的一个普通 Python 属性（线程安全不用担心，
        因为在 CPython 中，GIL 保护了简单属性读写的原子性）。
        """
        try:
            self._target(
                progress=lambda c, t: (
                    self.progress.emit(c, t)
                    if not self._cancelled
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
            self.finished.emit(True, '')
        except CancelledError:
            # 用户取消了，当做正常完成（不是错误）
            self.finished.emit(True, '')
        except Exception as e:
            # 任务抛异常了（比如文件不存在、编码错误等），
            # 通过 finished 信号把异常信息传回主线程。
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))
