# -*- coding: utf-8 -*-
"""
TxtPress — 后台工作线程，带进度、状态、取消支持的 QThread。

为什么需要这个？
PyQt 的界面（GUI）和后台任务不能在同一个线程里跑。
如果把耗时操作（如文件转换）放在主线程，界面会卡死。
这个 worker 把任务扔到子线程，通过信号把进度/结果传回主线程。

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
    """

    # 定义信号。int,int 和 bool,str 是信号的参数类型。
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, target, args=None, kwargs=None):
        """
        Args:
            target:  实际干活儿的函数，签名 target(progress, status, *args, **kwargs)
                     progress 和 status 是本 worker 注入的回调函数
            args:    传给 target 的额外位置参数
            kwargs:  传给 target 的额外关键字参数
        """
        super().__init__()
        self._target = target
        self._args = args or ()
        self._kwargs = kwargs or {}
        self._cancelled = False  # 用户是否点了取消

    def cancel(self):
        """
        请求取消操作。

        注意这只是设置一个标志位，实际能不能立即取消取决于
        target 函数是否频繁调用了 progress 回调（每次调用都会检查取消标志）。
        """
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """是否已取消（可被 target 检查）。"""
        return self._cancelled

    def run(self):
        """
        QThread 的入口方法，start() 之后自动在子线程执行。

        我们把 progress 和 status 包装成 lambda，注入给 target。
        target 可以像普通函数一样调用它们：
            progress(5, 10)    -> 触发 self.progress.emit(5, 10)
            status('工作中')    -> 触发 self.status.emit('工作中')

        如果用户点了取消，progress 回调会 emit None（即不更新进度条），
        但 target 仍然继续跑。需要 target 自己检查 self.is_cancelled 来决定是否退出。
        """
        try:
            self._target(
                progress=lambda c, t: (
                    self.progress.emit(c, t) if not self._cancelled else None
                ),
                status=lambda s: self.status.emit(s),
                *self._args,
                **self._kwargs,
            )
            # 没有抛异常，且没有被取消 => 成功
            if not self._cancelled:
                self.finished.emit(True, '')
        except Exception as e:
            # 任务抛异常了，把异常信息通过 finished 信号传回去
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))
