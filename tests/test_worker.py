# -*- coding: utf-8 -*-
"""ProgressWorker.run() 三态 task_done 发射测试（同步直调，不起真线程）。

守护 Task 11 的核心语义，防止回归成原始 bug（取消也发 (True, '')）：
1. 正常完成     -> (True, '', False)
2. 取消（经 progress 取消检查点） -> (False, '', True)
3. 直接抛 CancelledError 也不算普通错误 -> (False, '', True)
4. 异常         -> (False, str(e), False)
5. 晚到取消（完成前无取消检查点） -> (True, '', False)

取消机制（worker.run 内）：注入给 target 的 progress 回调里检查
_cancelled 标志，已置位则抛 CancelledError。所以"取消用例"的 target
必须先调 worker.cancel()、再调用传入的 progress 回调触发检查。

pyqtSignal 直连（同一对象、同一线程）不需要 QApplication，
直接同步调用 worker.run() 即可让槽函数在 emit 时立即执行。
"""
from __future__ import annotations

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from worker import CancelledError, ProgressWorker


def _capture(worker):
    """把 task_done 连到一个捕获列表，返回该列表。"""
    received = []
    worker.task_done.connect(
        lambda ok, err, cancelled: received.append((ok, err, cancelled))
    )
    return received


def test_task_done_on_success():
    """正常完成：emit (True, '', False)。"""
    worker = ProgressWorker(lambda progress, status: progress(1, 1))
    received = _capture(worker)

    worker.run()

    assert received == [(True, '', False)]


def test_task_done_on_cancel_via_progress_checkpoint():
    """取消：target 内 cancel() 后走到 progress 取消检查点 -> (False, '', True)。"""
    holder = {}

    def target(progress, status):
        holder['worker'].cancel()   # 先置取消标志
        progress(1, 1)              # 再走到取消检查点，闭包抛 CancelledError

    worker = ProgressWorker(target)
    holder['worker'] = worker
    received = _capture(worker)

    worker.run()

    assert received == [(False, '', True)]


def test_task_done_when_cancelled_error_raised_directly():
    """CancelledError 直接抛出也不被当成普通错误（err 为空、cancelled=True）。"""

    def target(progress, status):
        raise CancelledError()

    worker = ProgressWorker(target)
    received = _capture(worker)

    worker.run()

    assert received == [(False, '', True)]


def test_task_done_on_exception():
    """异常：emit (False, str(e), False)，错误信息透传。"""

    def target(progress, status):
        raise ValueError('boom')

    worker = ProgressWorker(target)
    received = _capture(worker)

    worker.run()  # logger.exception 会打印 traceback，属预期输出

    assert len(received) == 1
    ok, err, cancelled = received[0]
    assert ok is False
    assert cancelled is False
    assert 'boom' in err


def test_task_done_success_when_cancel_arrives_without_checkpoint():
    """晚到取消：期间 cancel() 被调但 target 没走到取消检查点 -> 仍报成功。

    锁定"产物已写盘就报成功"语义——取消标志只是建议，检查点（progress
    回调）没命中就不会打断已完成的 target。
    """
    holder = {}

    def target(progress, status):
        holder['worker'].cancel()   # 取消标志已置位……
        # ……但此后不再调用 progress，没有取消检查点
        status('快完成了')

    worker = ProgressWorker(target)
    holder['worker'] = worker
    received = _capture(worker)

    worker.run()

    assert received == [(True, '', False)]
