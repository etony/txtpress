# -*- coding: utf-8 -*-
"""QSS 选择器修复（Task 16）：浅/深主题同步断言 + offscreen 像素冒烟。

根因：封面控件 `_ClickableLabel` 继承 `QWidget` 而非 `QLabel`，
`QLabel#cover_label` 的类型部分永不匹配，整条规则不命中；
改用纯 id 选择器 `#cover_label`（按 objectName 精确匹配）。
深色主题另缺 `QMainWindow[dragging="true"]` 拖放高亮，补齐并与浅色同步。

验收方式：QSS 命中无法直接查询 → 渲染到 QImage 采样像素，
断言背景色等于选择器声明的值（浅 #F5F5F5 / 深 #3C3C3C；
拖放 浅 #E3F2FD / 深 #1E3A5F）。
"""
import os

# 像素断言依赖 offscreen 平台，强制指定（不被用户环境变量覆盖）
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtWidgets import QApplication, QMainWindow

import theme_manager as tmod
import window as wmod


@pytest.fixture(scope='session')
def qapp():
    """会话级 QApplication（offscreen）。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def _reset_app_style(qapp):
    """用例结束后清空全局样式表，避免深色主题残留污染后续测试模块。"""
    yield
    qapp.setStyleSheet('')


def _light_qss():
    """读取真实浅色主题文件（resources/theme.qss）。"""
    path = os.path.join(tmod.BASE_DIR, 'resources', 'theme.qss')
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _render(widget, width, height):
    """把控件渲染成 QImage，返回中心像素 (r, g, b, a)。"""
    widget.resize(width, height)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    widget.render(painter)
    painter.end()
    color = img.pixelColor(width // 2, height // 2)
    return color.red(), color.green(), color.blue(), color.alpha()


def _cover_center(qss, object_name='cover_label'):
    """在给定 QSS 下渲染封面控件，返回中心像素。"""
    qapp = QApplication.instance()
    qapp.setStyleSheet(qss)
    label = wmod._ClickableLabel()
    label.setObjectName(object_name)
    label.show()
    try:
        return _render(label, 120, 168)
    finally:
        label.close()
        label.deleteLater()


def _drag_center(qss, dragging):
    """在给定 QSS 下渲染置了 dragging 属性的主窗口，返回中心像素。"""
    qapp = QApplication.instance()
    qapp.setStyleSheet(qss)
    win = QMainWindow()
    win.setProperty('dragging', dragging)
    win.show()
    try:
        return _render(win, 400, 300)
    finally:
        win.close()
        win.deleteLater()


# ================================================================
# 文本级：选择器存在且浅/深两份同步
# ================================================================


def test_cover_selector_is_bare_id_in_both_themes():
    """两主题都用纯 id 选择器，且都不再带 QLabel 类型前缀。"""
    light = _light_qss()
    dark = tmod.DARK_THEME
    for qss in (light, dark):
        assert '#cover_label {' in qss
        assert '#cover_label:hover' in qss
        assert 'QLabel#cover_label' not in qss


def test_legacy_selector_absent_from_embedded_light():
    """内嵌 LIGHT_THEME 备用样式里也不应残留坏选择器。"""
    assert 'QLabel#cover_label' not in tmod.LIGHT_THEME


def test_dragging_selector_present_in_both_themes():
    """拖放高亮选择器两主题同步（深色为本次补齐）。"""
    light = _light_qss()
    dark = tmod.DARK_THEME
    assert 'QMainWindow[dragging="true"]' in light
    assert 'QMainWindow[dragging="true"]' in dark
    # 深色高亮按计划配色
    assert '#1E3A5F' in dark
    assert '#4A9EFF' in dark


# ================================================================
# offscreen 像素冒烟：选择器真的命中
# ================================================================


def test_cover_label_selector_hits_in_light_theme(qapp):
    """浅色：#cover_label 命中 _ClickableLabel，背景 = #F5F5F5。"""
    assert _cover_center(_light_qss())[:3] == (245, 245, 245)


def test_cover_label_selector_hits_in_dark_theme(qapp):
    """深色：#cover_label 命中，背景 = #3C3C3C。"""
    assert _cover_center(tmod.DARK_THEME)[:3] == (60, 60, 60)


def test_legacy_qualified_selector_does_not_hit(qapp):
    """回归证据：旧写法 QLabel#cover_label 不命中（背景非 #F5F5F5）。"""
    legacy = _light_qss().replace('#cover_label', 'QLabel#cover_label')
    assert _cover_center(legacy)[:3] != (245, 245, 245)


def test_selector_matches_only_declared_object_name(qapp):
    """id 选择器按 objectName 精确匹配，别的名字不误命中。"""
    assert _cover_center(_light_qss(), 'other_label')[:3] != (245, 245, 245)


def test_drag_highlight_applies_in_both_themes(qapp):
    """dragging=true 时两主题分别渲染出 #E3F2FD / #1E3A5F。"""
    light = _light_qss()
    assert _drag_center(light, True)[:3] == (227, 242, 253)
    assert _drag_center(tmod.DARK_THEME, True)[:3] == (30, 58, 95)


def test_no_drag_highlight_when_property_false(qapp):
    """dragging=false 不触发高亮，回退到各自窗口底色。"""
    light = _light_qss()
    assert _drag_center(light, False)[:3] == (250, 250, 250)  # #FAFAFA
    assert _drag_center(tmod.DARK_THEME, False)[:3] == (30, 30, 30)  # #1E1E1E
