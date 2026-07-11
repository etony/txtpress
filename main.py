# -*- coding: utf-8 -*-
"""
TxtPress — 电子书格式转换工具。程序入口。

用法：
    python main.py

启动流程：
    1. 创建 QApplication（设置应用名、组织名）
    2. 加载 QSS 样式表（resources/theme.qss）
    3. 设置全局字体（微软雅黑，12px）
    4. 实例化 MainWindow，显示窗口
    5. 进入事件循环

环境要求：
    Python 3.10+
    PyQt6, ebooklib, beautifulsoup4, chardet, opencc-python-reimplemented,
    loguru, mobi

学习提示：
    __future__ import annotations 是 Python 3.7+ 的特性，
    它让类型注解变成字符串（延迟求值），从而支持前向引用和更简洁的联合类型写法。
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

from window import MainWindow


def _load_stylesheet(app: QApplication) -> None:
    """
    加载 QSS 样式表，实现 Material Design 风格的 UI 外观。

    样式表文件位于 resources/theme.qss，定义了全局的颜色、字体、间距等。
    如果文件不存在（比如首次运行），程序会静默跳过，不报错。

    QSS 的工作方式类似 CSS：选择器匹配控件类型/名称/状态，应用样式属性。
    Qt 默认控件在每个平台上长不一样，QSS 可以抹平差异，
    让程序在各平台看起来一致。
    """
    # __file__ 是 main.py 的绝对路径，取它所在目录再拼接 resources/theme.qss
    qss_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'resources', 'theme.qss',
    )
    if os.path.exists(qss_path):
        with open(qss_path, 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())
    # 如果文件不存在，就使用 Qt 默认样式，也不影响使用


def main():
    """程序主入口。"""
    # ---- 高 DPI 适配 ----
    # 在高分辨率屏幕（Retina 等）上，Qt 默认会缩放像素，
    # PassThrough 策略让系统自己处理缩放，避免界面模糊。
    # hasattr 检查是为了兼容旧版 PyQt6（6.0.x），
    # 新版 PyQt6 这个方法一直存在，但保持检查更健壮。
    if hasattr(QApplication, 'setHighDpiScaleFactorRoundingPolicy'):
        from PyQt6.QtCore import Qt
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

    # ---- Qt 应用基础设置 ----
    # 每个 PyQt 程序有且只有一个 QApplication 实例。
    # appName 和 orgName 影响 QSettings 的存储路径。
    app = QApplication(sys.argv)
    app.setApplicationName('TxtPress')
    app.setOrganizationName('etony')

    # ---- 全局字体 ----
    # Microsoft YaHei 是 Windows 上的中文字体，字号 10pt。
    # PreferAntialias 让字体边缘更平滑（抗锯齿）。
    # 注意：在 Linux/macOS 上如果微软雅黑不存在，
    # Qt 会自动 fallback 到系统默认中文字体。
    font = QFont('Microsoft YaHei', 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    # ---- 加载样式与启动窗口 ----
    _load_stylesheet(app)

    # MainWindow 继承 QMainWindow，它自带菜单栏、工具栏、状态栏，
    # 我们用状态栏显示进度和消息。
    window = MainWindow()
    window.show()

    # app.exec() 进入 Qt 事件循环，程序停留在这里直到用户关闭窗口。
    # sys.exit 确保退出码正确（0=正常，非0=异常）。
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
