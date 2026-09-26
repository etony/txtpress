# -*- coding: utf-8 -*-
"""Task 17：重置补齐 / 输出路径保护 / Yes-No 按钮测试。

覆盖计划 Task 17 三个子项：
1. 三 Tab 重置全字段断言表（含补齐字段：正则预设、EPUB 样式、
   正文字体、目录样式、源文件目录缓存、MOBI 封面默认图）
2. 输出路径保护：与输入同文件 / 目录不存在 → 拒绝并提示；
   目标已存在 → Yes/No 覆盖确认；合法路径 → 放行
3. 确认弹窗按钮语义：_ask_open_dir 用 Yes|No（而非 OK/Cancel）
"""
import os
import unittest.mock as mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtWidgets import QApplication

import window as wmod


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
    if win._worker is not None:
        win._worker.cancel()
        win._worker.wait(2000)
    win._worker = None
    win._closing = False
    win.close()


# ================================================================
# 子项 1：三 Tab 重置全字段断言表
# ================================================================


def test_reset_tab1_restores_all_fields(main_window):
    """tab1 重置：全部输入/选项/状态字段回到默认（断言表）。"""
    win = main_window
    # ---- 灌入非默认值 ----
    win._le_txt.setText('/tmp/a.txt')
    win._le_epub.setText('/tmp/a.epub')
    win._le_title.setText('题')
    win._le_author.setText('者')
    win._le_txt_contrib.setText('贡')
    win._le_txt_date.setText('2020-01-01')
    win._le_txt_desc.setText('述')
    win._txt_cover = '/tmp/c.jpg'
    win._cb_encode.setCurrentIndex(3)
    win._cb_regex_preset.setCurrentIndex(1)   # 联动会改写 te_reg
    win._cb_epub_style.setCurrentIndex(1)
    win._cb_font.setCurrentIndex(2)
    win._cb_toc_style.setCurrentIndex(3)
    win._te_reg.setText('custom-regex')
    win._ordered_chapters = [(0, 'x')]
    win._ordered_chapters_src = ('a', 'b', 'c')
    win._detected_encoding = 'gbk'
    win._detected_path = '/tmp/a.txt'
    win._txt_dir = '/tmp'

    win._on_reset_tab1()

    # ---- 断言表：字段 → 期望默认值 ----
    text_defaults = (
        (win._le_txt, ''), (win._le_epub, ''), (win._le_title, ''),
        (win._le_author, ''), (win._le_txt_contrib, ''),
        (win._le_txt_date, ''), (win._le_txt_desc, ''),
        (win._te_reg, wmod.DEFAULT_CHAPTER_REGEX),
    )
    for widget, expected in text_defaults:
        assert widget.text() == expected, widget.accessibleName() or widget
    combo_defaults = (
        (win._cb_encode, 0),
        (win._cb_regex_preset, 0),
        (win._cb_epub_style, 0),
        (win._cb_font, 0),
        (win._cb_toc_style, 0),
    )
    for combo, expected in combo_defaults:
        assert combo.currentIndex() == expected
    assert win._txt_cover == ''
    assert win._cover_label.pixmap() is not None
    assert not win._cover_label.pixmap().isNull()
    assert win._ordered_chapters is None
    assert win._ordered_chapters_src is None
    assert win._detected_encoding == 'utf-8'
    assert win._detected_path is None
    assert win._txt_dir == ''
    assert win.statusBar().currentMessage() == '已重置'


def test_reset_tab2_restores_all_fields(main_window, tmp_path):
    """tab2 重置：全部输入/输出选项/目录缓存回到默认（断言表）。"""
    win = main_window
    # 先勾选繁简（源文件路径尚空，联动槽提前返回，不依赖 OpenCC）
    win._chb_fanjian.setChecked(True)
    win._le_in_epub.setText(str(tmp_path / 'in.epub'))
    win._le_out_txt.setText(str(tmp_path / 'out.txt'))
    win._le_book_title.setText('t')
    win._le_book_creator.setText('c')
    win._le_book_contrib.setText('cb')
    win._le_book_date.setText('2021-02-02')
    win._le_book_desc.setText('d')
    win._epub_cover_path = '/tmp/c.jpg'
    win._cb_out_code.setCurrentIndex(2)
    win._cb_sep.setCurrentIndex(3)
    win._epub_dir = str(tmp_path)

    win._on_reset_tab2()

    # ---- 断言表 ----
    for widget in (win._le_in_epub, win._le_out_txt, win._le_book_title,
                   win._le_book_creator, win._le_book_contrib,
                   win._le_book_date, win._le_book_desc):
        assert widget.text() == ''
    assert win._epub_cover_path == ''
    assert win._cover_label2.pixmap() is not None
    assert not win._cover_label2.pixmap().isNull()
    assert win._cb_out_code.currentIndex() == 0
    assert win._cb_sep.currentIndex() == 0
    assert win._chb_fanjian.isChecked() is False
    assert win._epub_dir == ''
    assert win.statusBar().currentMessage() == '已重置'


def test_reset_tab3_restores_all_fields(main_window, tmp_path):
    """tab3 重置：输入/只读元数据字段清空，封面恢复默认图（断言表）。"""
    win = main_window
    win._le_mobi.setText(str(tmp_path / 'a.mobi'))
    win._le_mobi_txt.setText(str(tmp_path / 'a.txt'))
    win._mobi_book_title.setText('题')
    win._mobi_book_author.setText('者')
    win._mobi_book_publisher.setText('社')
    win._mobi_book_isbn.setText('isbn')
    win._mobi_book_language.setText('zh')
    win._mobi_book_published.setText('2022')
    win._mobi_lbl_cover.setText('无封面')  # 模拟加载后的文字状态

    win._on_reset_tab3()

    # ---- 断言表 ----
    for widget in (win._le_mobi, win._le_mobi_txt, win._mobi_book_title,
                   win._mobi_book_author, win._mobi_book_publisher,
                   win._mobi_book_isbn, win._mobi_book_language,
                   win._mobi_book_published):
        assert widget.text() == ''
    assert win._mobi_lbl_cover.text() == ''
    assert win._mobi_lbl_cover.pixmap() is not None
    assert not win._mobi_lbl_cover.pixmap().isNull()
    assert win.statusBar().currentMessage() == '已重置'


# ================================================================
# 子项 2：输出路径保护
# ================================================================


def test_tab1_rejects_output_equal_to_input(main_window, sample_txt):
    """tab1：输出路径指向输入 TXT 本身 → 拒绝并提示，不启动转换。"""
    win = main_window
    win._le_txt.setText(sample_txt)
    win._le_epub.setText(sample_txt)

    with mock.patch.object(wmod.QMessageBox, 'warning') as warn, \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_tab1()

    warn.assert_called_once()
    assert '输出路径不能与输入文件相同' in warn.call_args.args[2]
    run.assert_not_called()


def test_tab1_rejects_missing_output_dir(main_window, sample_txt, tmp_path):
    """tab1：输出目录不存在 → 拒绝并提示，不启动转换。"""
    win = main_window
    win._le_txt.setText(sample_txt)
    win._le_epub.setText(str(tmp_path / 'no_such_dir' / 'out.epub'))

    with mock.patch.object(wmod.QMessageBox, 'warning') as warn, \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_tab1()

    warn.assert_called_once()
    assert '输出目录不存在' in warn.call_args.args[2]
    run.assert_not_called()


def test_tab1_overwrite_confirmation(main_window, sample_txt, tmp_path):
    """tab1：目标已存在 → Yes/No 覆盖确认；No 拒绝，Yes 放行。"""
    win = main_window
    out = tmp_path / 'exists.epub'
    out.write_bytes(b'x')
    win._le_txt.setText(sample_txt)
    win._le_epub.setText(str(out))

    # 用户选 No → 不转换
    with mock.patch.object(wmod.QMessageBox, 'question',
                           return_value=wmod.QMessageBox.StandardButton.No
                           ) as question, \
            mock.patch.object(wmod.QMessageBox, 'warning'), \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_tab1()

    question.assert_called_once()
    assert question.call_args.args[3] == (
        wmod.QMessageBox.StandardButton.Yes
        | wmod.QMessageBox.StandardButton.No)
    run.assert_not_called()

    # 用户选 Yes → 放行
    with mock.patch.object(wmod.QMessageBox, 'question',
                           return_value=wmod.QMessageBox.StandardButton.Yes), \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_tab1()

    run.assert_called_once()


def test_tab1_allows_clean_output_path(main_window, sample_txt, tmp_path):
    """tab1：合法路径（目录存在、目标不存在）→ 直接放行，不弹确认。"""
    win = main_window
    out = tmp_path / 'new.epub'
    win._le_txt.setText(sample_txt)
    win._le_epub.setText(str(out))

    with mock.patch.object(wmod.QMessageBox, 'question') as question, \
            mock.patch.object(wmod.QMessageBox, 'warning') as warn, \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_tab1()

    question.assert_not_called()
    warn.assert_not_called()
    run.assert_called_once()


def test_tab2_rejects_output_equal_to_input(main_window, make_epub):
    """tab2：TXT 输出路径指向输入 EPUB 本身 → 拒绝。"""
    win = main_window
    path = make_epub()
    win._le_in_epub.setText(path)
    win._le_out_txt.setText(path)

    with mock.patch.object(wmod.QMessageBox, 'warning') as warn, \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_tab2()

    warn.assert_called_once()
    assert '输出路径不能与输入文件相同' in warn.call_args.args[2]
    run.assert_not_called()


def test_tab2_allows_clean_output_path(main_window, make_epub, tmp_path):
    """tab2：合法输出路径 → 放行。"""
    win = main_window
    path = make_epub()
    win._le_in_epub.setText(path)
    win._le_out_txt.setText(str(tmp_path / 'out.txt'))

    with mock.patch.object(wmod.QMessageBox, 'question') as question, \
            mock.patch.object(wmod.QMessageBox, 'warning'), \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_chapter()

    question.assert_not_called()
    run.assert_called_once()


def test_tab3_rejects_missing_output_dir(main_window, tmp_path):
    """tab3：输出目录不存在 → 拒绝并提示，不启动转换。"""
    win = main_window
    mobi = tmp_path / 'a.mobi'
    mobi.write_bytes(b'x')
    win._le_mobi.setText(str(mobi))
    win._le_mobi_txt.setText(str(tmp_path / 'no_such_dir' / 'out.txt'))

    with mock.patch.object(wmod.QMessageBox, 'warning') as warn, \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_mobi_to_txt()

    warn.assert_called_once()
    assert '输出目录不存在' in warn.call_args.args[2]
    run.assert_not_called()


def test_tab3_rejects_output_equal_to_input(main_window, tmp_path):
    """tab3：TXT 输出路径指向输入 MOBI 本身 → 拒绝。"""
    win = main_window
    mobi = tmp_path / 'a.mobi'
    mobi.write_bytes(b'x')
    win._le_mobi.setText(str(mobi))
    win._le_mobi_txt.setText(str(mobi))

    with mock.patch.object(wmod.QMessageBox, 'warning') as warn, \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_mobi_to_txt()

    warn.assert_called_once()
    assert '输出路径不能与输入文件相同' in warn.call_args.args[2]
    run.assert_not_called()


def test_tab3_allows_clean_output_path(main_window, tmp_path):
    """tab3：合法输出路径 → 放行。"""
    win = main_window
    mobi = tmp_path / 'a.mobi'
    mobi.write_bytes(b'x')
    win._le_mobi.setText(str(mobi))
    win._le_mobi_txt.setText(str(tmp_path / 'out.txt'))

    with mock.patch.object(wmod.QMessageBox, 'question') as question, \
            mock.patch.object(wmod.QMessageBox, 'warning'), \
            mock.patch.object(win, '_run_worker') as run:
        win._on_convert_mobi_to_txt()

    question.assert_not_called()
    run.assert_called_once()


# ================================================================
# 子项 3：确认弹窗按钮语义（Yes|No）
# ================================================================


def _patch_exec_return(reply):
    """替换 QMessageBox.exec，记录实例按钮集合并返回指定 reply。"""
    captured = {}

    def fake_exec(self):
        # buttons() 返回 QPushButton 列表，用 standardButton 反查枚举
        captured['buttons'] = [self.standardButton(b)
                               for b in self.buttons()]
        return reply

    return captured, mock.patch.object(wmod.QMessageBox, 'exec', fake_exec)


def test_ask_open_dir_uses_yes_no(main_window, tmp_path):
    """_ask_open_dir：按钮为 Yes|No（非 OK/No），选 Yes 打开目录。"""
    captured, patch_exec = _patch_exec_return(
        wmod.QMessageBox.StandardButton.Yes)

    with patch_exec, mock.patch.object(main_window, '_open_dir') as od:
        main_window._ask_open_dir(str(tmp_path))

    buttons = captured['buttons']
    assert wmod.QMessageBox.StandardButton.Yes in buttons
    assert wmod.QMessageBox.StandardButton.No in buttons
    assert wmod.QMessageBox.StandardButton.Ok not in buttons
    od.assert_called_once_with(str(tmp_path))


def test_ask_open_dir_no_skips_open(main_window, tmp_path):
    """_ask_open_dir：选 No 不打开目录。"""
    _, patch_exec = _patch_exec_return(wmod.QMessageBox.StandardButton.No)

    with patch_exec, mock.patch.object(main_window, '_open_dir') as od:
        main_window._ask_open_dir(str(tmp_path))

    od.assert_not_called()
