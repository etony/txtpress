# -*- coding: utf-8 -*-
"""Task 18：配置存语义编码值测试。

覆盖计划 Task 18：
1. 往返：语义值（下拉显示文本）save → load 一致
2. 兼容：旧格式 config（ComboBox 序号 int / 数字串）→ 加载得到正确语义值
3. 非法/未知值回退到默认（自动检测）
所有配置读写都指向 tmp，绝不污染真实 config.json。
"""
import json
import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtWidgets import QApplication

import window as wmod
from models import AppConfig


@pytest.fixture(scope='session')
def qapp():
    """会话级 QApplication（offscreen，不创建真实窗口）。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def config_path(tmp_path):
    """隔离的 config.json 路径（models 层测试用）。"""
    return tmp_path / 'config.json'


@pytest.fixture
def make_window(qapp, tmp_path, monkeypatch):
    """配置读写指向 tmp 的 MainWindow 工厂。

    可先写入 config_data 再创建窗口，用于验证旧格式兼容。
    """
    monkeypatch.setattr(wmod, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    created = []

    def _make(config_data=None):
        if config_data is not None:
            (tmp_path / 'config.json').write_text(
                json.dumps(config_data, ensure_ascii=False),
                encoding='utf-8',
            )
        win = wmod.MainWindow()
        created.append(win)
        return win

    yield _make
    for win in created:
        if win._worker is not None:
            win._worker.cancel()
            win._worker.wait(2000)
        win._worker = None
        win._closing = False
        win.close()


# ================================================================
# 子项 1：语义值往返
# ================================================================


def test_models_default_txt_encoding():
    """默认值是语义字符串 '自动检测'，不再是序号 0。"""
    assert AppConfig().txt_encoding == '自动检测'


def test_models_roundtrip_semantic_value(config_path):
    """语义值 save → load 一致。"""
    cfg = AppConfig(txt_encoding='gbk')
    cfg.save(config_path)
    loaded = AppConfig.load(config_path)
    assert loaded.txt_encoding == 'gbk'
    # JSON 里存的也是语义字符串
    data = json.loads(config_path.read_text(encoding='utf-8'))
    assert data['txt_encoding'] == 'gbk'


def test_models_load_legacy_int_does_not_crash(config_path):
    """旧格式（序号 int）加载不崩，值原样保留，由 window 层映射。"""
    config_path.write_text(
        json.dumps({'txt_encoding': 2}), encoding='utf-8')
    loaded = AppConfig.load(config_path)
    assert loaded.txt_encoding == 2


def test_window_save_stores_combo_text(make_window):
    """_save_config 存下拉显示文本（语义值），不是 index。"""
    win = make_window()
    win._tab_txt2epub._cb_encode.setCurrentText('gbk')
    win._save_config()
    data = json.loads(
        Path(wmod.CONFIG_PATH).read_text(encoding='utf-8'))
    assert data['txt_encoding'] == 'gbk'


def test_window_roundtrip_semantic_value(make_window):
    """语义值 save → 新窗口 load → 下拉恢复同一选项。"""
    win1 = make_window()
    win1._tab_txt2epub._cb_encode.setCurrentText('gb18030')
    win1._save_config()

    win2 = make_window()
    assert win2._tab_txt2epub._cb_encode.currentText() == 'gb18030'


# ================================================================
# 子项 2：旧格式（序号）兼容
# ================================================================


def test_window_restore_legacy_int_index(make_window):
    """旧 config 存序号 2 → 恢复成当前下拉第 2 项的文本（gbk）。"""
    win = make_window({'txt_encoding': 2})
    expected = win._tab_txt2epub._cb_encode.itemText(2)
    assert expected == 'gbk'
    assert win._tab_txt2epub._cb_encode.currentText() == 'gbk'


def test_window_restore_legacy_digit_string(make_window):
    """旧 config 存数字串 '4' → 恢复成第 4 项文本（gb18030）。"""
    win = make_window({'txt_encoding': '4'})
    assert win._tab_txt2epub._cb_encode.currentText() == win._tab_txt2epub._cb_encode.itemText(4)
    assert win._tab_txt2epub._cb_encode.currentText() == 'gb18030'


def test_window_restore_legacy_int_out_of_range(make_window):
    """序号越界（选项已增删）→ 回退默认第 0 项，不崩不错位。"""
    win = make_window({'txt_encoding': 99})
    assert win._tab_txt2epub._cb_encode.currentIndex() == 0
    assert win._tab_txt2epub._cb_encode.currentText() == '自动检测'


def test_window_upgrade_legacy_index_on_first_save(make_window):
    """旧序号 config 恢复后首次保存即完成格式升级（2 → 'gbk'）。

    走真实 tmp CONFIG_PATH 隔离：读旧格式 → _restore_config 映射 →
    _save_config 落盘，钉死 JSON 里是 str 语义值而非 int 序号。
    """
    win = make_window({'txt_encoding': 2})
    assert win._tab_txt2epub._cb_encode.currentText() == 'gbk'
    win._save_config()
    data = json.loads(
        Path(wmod.CONFIG_PATH).read_text(encoding='utf-8'))
    assert data['txt_encoding'] == 'gbk'
    assert isinstance(data['txt_encoding'], str)


# ================================================================
# 子项 3：非法/未知值回退
# ================================================================


@pytest.mark.parametrize('raw', [
    '不存在的编码',   # 未知语义值
    None,            # JSON null
    2.0,             # 浮点脏数据
    True,            # bool 脏数据（bool 是 int 子类，须走回退而非序号 1）
    ['gbk'],         # 类型脏数据
    '',              # 空串
])
def test_window_restore_invalid_value_falls_back(make_window, raw):
    """非法/未知值一律回退到默认第 0 项（自动检测），不崩溃。"""
    win = make_window({'txt_encoding': raw})
    assert win._tab_txt2epub._cb_encode.currentIndex() == 0
    assert win._tab_txt2epub._cb_encode.currentText() == '自动检测'


# ================================================================
# 子项 4：全字段 round-trip（_save_config 持久化的每个字段）
# ================================================================


def test_window_full_config_roundtrip(make_window):
    """第一窗把每个持久化字段改成非默认值 → save → 新窗构造 restore → 逐字段断言。

    失败消息带字段名：Tab 控件改名/读写路径破坏时能立刻定位是哪个字段。
    覆盖 _save_config 实际写入 AppConfig 的全部 11 个字段。
    """
    from theme_manager import Theme

    win1 = make_window()
    t1 = win1._tab_txt2epub
    t2 = win1._tab_epub2txt

    def rotate(combo, name):
        """把下拉拨到非默认项（往返必须能恢复出非默认值才算有效覆盖）。"""
        assert combo.count() > 1, f'{name}: 至少需要 2 个选项才能测非默认往返'
        combo.setCurrentIndex((combo.currentIndex() + 1) % combo.count())

    expected = {}
    rotate(t1._cb_encode, 'txt_encoding')
    expected['txt_encoding'] = t1._cb_encode.currentText()
    rotate(t2._cb_out_code, 'out_encoding')
    expected['out_encoding'] = t2._cb_out_code.currentText()
    rotate(t2._cb_sep, 'chapter_sep')
    expected['chapter_sep'] = t2._cb_sep.currentText()
    rotate(t1._cb_regex_preset, 'regex_preset')
    expected['regex_preset'] = t1._cb_regex_preset.currentText()
    # 必须在 rotate regex_preset 之后设置：切预设会连带覆写 _te_reg
    t1._te_reg.setText('§自定义正则§')
    expected['chapter_regex'] = '§自定义正则§'
    t2._chb_fanjian.setChecked(not t2._chb_fanjian.isChecked())
    expected['fanjian_enabled'] = t2._chb_fanjian.isChecked()
    rotate(t1._cb_epub_style, 'epub_style')
    expected['epub_style'] = t1._cb_epub_style.currentText()
    rotate(t1._cb_font, 'font_family')
    expected['font_family'] = t1._cb_font.currentText()
    rotate(t1._cb_toc_style, 'toc_style')
    expected['toc_style'] = t1._cb_toc_style.currentText()
    win1.resize(900, 650)

    # theme 是全局单例：save 后把单例拨回原值，
    # 新窗构造时只有 _restore_config 真正生效才会回到 new_theme
    orig_theme = win1._theme_manager.get_current_theme()
    new_theme = Theme.LIGHT if orig_theme == Theme.DARK else Theme.DARK
    win1._theme_manager.set_theme(new_theme)
    expected['theme'] = new_theme.value

    win1._save_config()
    win1._theme_manager.set_theme(orig_theme)

    try:
        win2 = make_window()
        got = {
            'txt_encoding': win2._tab_txt2epub._cb_encode.currentText(),
            'out_encoding': win2._tab_epub2txt._cb_out_code.currentText(),
            'chapter_sep': win2._tab_epub2txt._cb_sep.currentText(),
            'chapter_regex': win2._tab_txt2epub._te_reg.text(),
            'fanjian_enabled': win2._tab_epub2txt._chb_fanjian.isChecked(),
            'regex_preset': win2._tab_txt2epub._cb_regex_preset.currentText(),
            'epub_style': win2._tab_txt2epub._cb_epub_style.currentText(),
            'font_family': win2._tab_txt2epub._cb_font.currentText(),
            'toc_style': win2._tab_txt2epub._cb_toc_style.currentText(),
            'theme': win2._theme_manager.get_current_theme().value,
        }
        for name, exp in expected.items():
            assert got[name] == exp, (
                f'{name}: 新窗恢复为 {got[name]!r}，期望 {exp!r}')

        # window_geometry 单独断言：offscreen 平台 restoreGeometry 有
        # frameMargins 换算偏差（纯 Qt 复现：save 900 → restore 798），
        # save 侧字节精确往返 + restore 侧高度精确回环、宽度不走默认回退
        saved = json.loads(
            Path(wmod.CONFIG_PATH).read_text(encoding='utf-8'))
        assert bytes.fromhex(saved['window_geometry']) == bytes(
            win1.saveGeometry()), 'window_geometry: 持久化字节 != saveGeometry()'
        assert win2.height() == 650, (
            f'window_geometry: 高度恢复为 {win2.height()}，期望 650')
        assert win2.width() != 800, (
            'window_geometry: 宽度为默认 800，配置几何未生效')
    finally:
        win1._theme_manager.set_theme(orig_theme)
