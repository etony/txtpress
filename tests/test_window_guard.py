# -*- coding: utf-8 -*-
"""窗口后台任务 guard 测试：重入保护、竞态语义、关窗早退（offscreen）。

覆盖 Task 10 评审修复：
1. busy 时 _run_worker 被挡且不替换 worker 引用
2. 线程已结束、_done 未执行的间隙 _is_busy 仍为 True（竞态）
3. _closing 置位后 _done 早退（不弹窗、不重开 tabs）

Task 11 三态结果：task_done(成功, 错误消息, 是否被取消)，
成功 / 失败 / 取消三条分支各自的 UI 行为。

Task 12：on_success 回调时机、fail_msg 文案、show_progress 显隐，
以及 _load_epub_file 迁移后的真实 worker 端到端回填。
"""
import os
import sys
import time
import unittest.mock as mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtWidgets import QApplication

import window as wmod


class _FakeWorker:
    """替身 worker：不启动真线程，信号用 Mock 捕获槽函数。"""

    def __init__(self, target):
        self.target = target
        self.progress = mock.Mock()
        self.status = mock.Mock()
        self.task_done = mock.Mock()
        self.running = False
        self.cancelled = False

    def start(self):
        self.running = True

    def isRunning(self):
        return self.running

    def cancel(self):
        self.cancelled = True

    def wait(self, msecs=None):
        return True


@pytest.fixture(scope='session')
def qapp():
    """会话级 QApplication（offscreen，不创建真实窗口）。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    """MainWindow 实例，配置读写全部指向 tmp，绝不污染真实 config.json。"""
    monkeypatch.setattr(wmod, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    win = wmod.MainWindow()
    yield win
    win._worker = None
    win._closing = False
    win.close()


def test_run_worker_blocked_when_busy(main_window):
    """busy 时再次启动被挡，worker 引用不被覆盖。"""
    fake = _FakeWorker(None)
    fake.running = True
    main_window._worker = fake

    main_window._run_worker(lambda p, s: None, '成功', '')

    assert main_window._worker is fake
    assert fake.running is True  # start() 未被再次调用


def test_is_busy_covers_thread_finished_gap(main_window):
    """线程结束但 _done 未执行的间隙，_is_busy 仍为 True 且新任务被挡。"""
    fake = _FakeWorker(None)
    fake.running = False  # isRunning() 已为 False，但 _done 还没跑
    main_window._worker = fake

    assert main_window._is_busy() is True

    main_window._run_worker(lambda p, s: None, '成功', '')
    assert main_window._worker is fake


def test_done_early_return_when_closing(main_window, monkeypatch):
    """经由真实 closeEvent 置位 _closing 后，_done 直接返回。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    main_window._run_worker(lambda p, s: None, '成功消息', '')
    worker = main_window._worker
    done = worker.task_done.connect.call_args.args[0]

    main_window._tabs.setEnabled(False)
    msg_before = main_window.statusBar().currentMessage()

    # 模拟关窗：closeEvent 置位 _closing（save/super 打桩避免真实写配置）
    with mock.patch.object(main_window, '_save_config'), \
            mock.patch.object(wmod.QMainWindow, 'closeEvent'):
        main_window.closeEvent(mock.Mock())
    assert main_window._closing is True
    assert worker.cancelled is True

    # 关窗期间任务结束信号到达
    with mock.patch.object(main_window, '_ask_open_dir') as ask, \
            mock.patch.object(wmod.QMessageBox, 'critical') as crit:
        done(True, '', False)
        done(False, 'boom', False)

    ask.assert_not_called()
    crit.assert_not_called()
    assert main_window._tabs.isEnabled() is False  # 未被 _done 重新启用
    assert main_window._worker is worker
    assert main_window.statusBar().currentMessage() == msg_before


def _run_and_get_done(main_window, monkeypatch, success_msg='成功消息'):
    """启动一个假 worker，返回它的 task_done 槽函数。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    main_window._run_worker(lambda p, s: None, success_msg, '/tmp/out')
    worker = main_window._worker
    done = worker.task_done.connect.call_args.args[0]
    return worker, done


def test_done_success_branch(main_window, monkeypatch):
    """成功：显示成功消息、询问打开目录、重开 tabs、清空 worker。"""
    _, done = _run_and_get_done(main_window, monkeypatch, '全部搞定')
    main_window._tabs.setEnabled(False)

    with mock.patch.object(main_window, '_ask_open_dir') as ask, \
            mock.patch.object(wmod.QMessageBox, 'critical') as crit:
        done(True, '', False)

    ask.assert_called_once_with('/tmp/out')
    crit.assert_not_called()
    assert main_window.statusBar().currentMessage() == '全部搞定'
    assert main_window._tabs.isEnabled() is True
    assert main_window._worker is None


def test_done_cancelled_branch(main_window, monkeypatch):
    """取消：状态栏"已取消"，不询问打开目录、不弹错误框。"""
    _, done = _run_and_get_done(main_window, monkeypatch)
    main_window._tabs.setEnabled(False)

    with mock.patch.object(main_window, '_ask_open_dir') as ask, \
            mock.patch.object(wmod.QMessageBox, 'critical') as crit:
        done(False, '', True)

    ask.assert_not_called()
    crit.assert_not_called()
    assert main_window.statusBar().currentMessage() == '已取消'
    assert main_window._tabs.isEnabled() is True
    assert main_window._worker is None


def test_done_failure_branch(main_window, monkeypatch):
    """失败：弹 QMessageBox.critical，状态栏"转换失败"，不询问打开目录。"""
    _, done = _run_and_get_done(main_window, monkeypatch)
    main_window._tabs.setEnabled(False)

    with mock.patch.object(main_window, '_ask_open_dir') as ask, \
            mock.patch.object(wmod.QMessageBox, 'critical') as crit:
        done(False, 'boom', False)

    ask.assert_not_called()
    crit.assert_called_once()
    assert 'boom' in crit.call_args.args[2]
    assert main_window.statusBar().currentMessage() == '转换失败'
    assert main_window._tabs.isEnabled() is True
    assert main_window._worker is None


def test_close_event_cancels_and_flags_closing(main_window):
    """closeEvent：置 _closing、cancel + wait、保存配置。"""
    fake = _FakeWorker(None)
    fake.running = True
    main_window._worker = fake

    with mock.patch.object(main_window, '_save_config') as save, \
            mock.patch.object(wmod.QMainWindow, 'closeEvent'):
        main_window.closeEvent(mock.Mock())

    assert main_window._closing is True
    assert fake.cancelled is True
    save.assert_called_once()


def test_shortcuts_blocked_when_busy(main_window):
    """busy 时三个快捷键处理器直接 return 并给出状态栏提示。"""
    fake = _FakeWorker(None)
    fake.running = True
    main_window._worker = fake

    with mock.patch.object(main_window, '_on_convert_tab1') as conv, \
            mock.patch.object(main_window, '_on_browse_txt') as browse, \
            mock.patch.object(main_window, '_on_reset_tab1') as reset:
        main_window._on_shortcut_convert()
        main_window._on_shortcut_open()
        main_window._on_shortcut_reset()

    conv.assert_not_called()
    browse.assert_not_called()
    reset.assert_not_called()
    assert main_window.statusBar().currentMessage() == '已有转换任务进行中…'


# ================================================================
# Task 12：on_success / fail_msg / show_progress / 迁移端到端
# ================================================================


def test_done_calls_on_success_before_ask_open_dir(main_window, monkeypatch):
    """成功：on_success 先于状态栏消息与打开目录询问执行。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    order = []
    on_success = mock.Mock(side_effect=lambda: order.append('on_success'))
    main_window._run_worker(lambda p, s: None, success_msg='搞定',
                            dir_to_open='/tmp/out', on_success=on_success)
    worker = main_window._worker
    done = worker.task_done.connect.call_args.args[0]
    main_window._tabs.setEnabled(False)

    with mock.patch.object(main_window, '_ask_open_dir',
                          side_effect=lambda d: order.append('ask')):
        done(True, '', False)

    assert order == ['on_success', 'ask']
    assert main_window.statusBar().currentMessage() == '搞定'
    assert main_window._worker is None


def test_done_skips_on_success_on_failure(main_window, monkeypatch):
    """失败：on_success 不执行，弹窗与状态栏都用 fail_msg 文案。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    on_success = mock.Mock()
    main_window._run_worker(lambda p, s: None,
                            on_success=on_success, fail_msg='读取失败')
    worker = main_window._worker
    done = worker.task_done.connect.call_args.args[0]
    main_window._tabs.setEnabled(False)

    with mock.patch.object(wmod.QMessageBox, 'critical') as crit:
        done(False, 'boom', False)

    on_success.assert_not_called()
    assert '读取失败' in crit.call_args.args[2]
    assert 'boom' in crit.call_args.args[2]
    assert main_window.statusBar().currentMessage() == '读取失败'
    assert main_window._worker is None


def test_show_progress_false_keeps_controls_hidden(main_window, monkeypatch):
    """show_progress=False：进度条与取消按钮保持隐藏，tabs 仍被禁用。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    main_window._run_worker(lambda p, s: None, show_progress=False)

    assert main_window._progress_bar.isHidden() is True
    assert main_window._cancel_btn.isHidden() is True
    assert main_window._tabs.isEnabled() is False
    assert main_window._is_busy() is True


def test_show_progress_true_shows_cancel_button(main_window, monkeypatch):
    """默认 show_progress=True：取消按钮照旧显示（旧行为保持）。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    main_window._run_worker(lambda p, s: None)

    assert main_window._cancel_btn.isHidden() is False
    assert main_window._cancel_btn.text() == '取消'
    assert main_window._cancel_btn.isEnabled() is True


def test_done_resets_cancel_button_state(main_window, monkeypatch):
    """_done 后取消按钮复位为"取消/可用/隐藏"（Task 10 评审项）。"""
    monkeypatch.setattr(wmod, 'ProgressWorker', _FakeWorker)
    main_window._run_worker(lambda p, s: None)
    worker = main_window._worker
    done = worker.task_done.connect.call_args.args[0]

    # 模拟用户点过取消：按钮进入"取消中…"禁用态
    main_window._on_cancel_clicked()
    assert main_window._cancel_btn.text() == '取消中…'
    assert main_window._cancel_btn.isEnabled() is False

    with mock.patch.object(main_window, '_ask_open_dir'):
        done(True, '', False)

    assert main_window._cancel_btn.text() == '取消'
    assert main_window._cancel_btn.isEnabled() is True
    assert main_window._cancel_btn.isHidden() is True


def test_load_epub_file_fills_fields_via_worker(main_window, qapp,
                                                 make_epub):
    """端到端：_load_epub_file 用真实 worker 线程读取 EPUB 并回填 UI。

    覆盖迁移后的行为：字段填充、状态栏"已加载: …"、tabs 重开、
    show_progress=False 下进度条/取消按钮不显示。
    """
    path = make_epub()

    with mock.patch.object(wmod.QMessageBox, 'critical') as crit:
        main_window._load_epub_file(path)
        # 轮询事件循环直到 _done 清空 worker 引用（真实后台线程）
        deadline = time.time() + 15
        while main_window._worker is not None and time.time() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

    crit.assert_not_called()
    assert main_window._worker is None
    assert main_window._le_in_epub.text() == path
    assert main_window._le_out_txt.text().endswith('.txt')
    assert main_window._le_book_title.text() == '测试书'
    assert main_window.statusBar().currentMessage().startswith('已加载')
    assert main_window._tabs.isEnabled() is True
    assert main_window._progress_bar.isHidden() is True
    assert main_window._cancel_btn.isHidden() is True
