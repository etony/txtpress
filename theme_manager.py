# -*- coding: utf-8 -*-
"""
主题管理模块 - 支持浅色/深色主题切换
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

from PyQt6.QtWidgets import QApplication
from loguru import logger

from constants import BASE_DIR


class Theme(Enum):
    """主题枚举"""
    LIGHT = 'light'
    DARK = 'dark'


# 浅色主题样式（内嵌备用）
# 与 resources/theme.qss 保持同构（按钮分类 + btn_action 蓝色强调 + 封面/拖放），
# 仅在 theme.qss 缺失时兜底，避免运行时与降级版外观漂移。
LIGHT_THEME = '''
QMainWindow { background-color: #FAFAFA; }
QTabWidget::pane { border: none; background: #FFFFFF; border-radius: 8px; padding: 4px 6px; margin: 2px 4px; border: 1px solid #E8E8E8; }
QGroupBox { font-size: 12px; font-weight: 600; color: #424242; border: 1px solid #E0E0E0; border-radius: 6px; margin-top: 6px; padding: 10px 6px 6px 6px; background: #FFFFFF; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; background: #FFFFFF; margin-top: 2px; color: #1976D2; }
QLineEdit { border: 1px solid #E0E0E0; border-radius: 4px; padding: 4px 8px; background: #FAFAFA; color: #212121; font-size: 12px; min-height: 20px; }
QLineEdit:focus { border-color: #1976D2; background: #FFFFFF; border: 1px solid #1976D2; }
QComboBox { border: 1px solid #E0E0E0; border-radius: 4px; padding: 4px 24px 4px 8px; background: #FAFAFA; color: #212121; font-size: 12px; min-width: 80px; min-height: 20px; }
QLabel { color: #424242; font-size: 12px; background: transparent; }
QCheckBox { spacing: 8px; font-size: 12px; color: #424242; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #BDBDBD; border-radius: 3px; background: #FAFAFA; }
QCheckBox::indicator:checked { background: #1976D2; border-color: #1976D2; }
QTabBar::tab { background: transparent; color: #757575; padding: 10px 24px; font-size: 13px; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #1976D2; border-bottom: 3px solid #1976D2; background: #F5F9FF; }
QStatusBar { background: #F5F5F5; border-top: 1px solid #E0E0E0; color: #757575; font-size: 11px; padding: 2px 8px; }
QPushButton { background-color: #F5F5F5; color: #616161; border: 1px solid #E0E0E0; border-radius: 4px; padding: 6px 16px; font-size: 12px; font-weight: 500; min-height: 18px; }
QPushButton:hover { background-color: #EEEEEE; border-color: #BDBDBD; }
QPushButton:disabled { background-color: #FAFAFA; color: #BDBDBD; border: 1px solid #F0F0F0; }
QPushButton#btn_browse { padding: 4px 10px; font-size: 11px; }
QPushButton#btn_action { background-color: #1976D2; color: #FFFFFF; border: none; padding: 8px 22px; font-size: 13px; font-weight: 600; border-radius: 6px; }
QPushButton#btn_action:hover { background-color: #1565C0; color: #FFFFFF; }
QPushButton#btn_action:pressed { background-color: #0D47A1; color: #FFFFFF; }
QPushButton#btn_action:disabled { background-color: #BBDEFB; color: #FFFFFF; }
QPushButton#btn_reset { background-color: transparent; color: #757575; border: 1px solid #E0E0E0; }
QPushButton#btn_reset:hover { background-color: #F5F5F5; border-color: #BDBDBD; }
#cover_label { border: 1px solid #E0E0E0; background: #F5F5F5; border-radius: 6px; }
#cover_label:hover { background: #E3F2FD; border-color: #1976D2; }
#enc_detect { color: #757575; font-size: 11px; background: transparent; }
QMainWindow[dragging="true"] { background-color: #E3F2FD; border: 2px dashed #1976D2; }
'''

# 深色主题样式
DARK_THEME = '''
QMainWindow { background-color: #1E1E1E; }
QTabWidget::pane { border: none; background: #2D2D2D; border-radius: 8px; padding: 4px 6px; margin: 2px 4px; border: 1px solid #3E3E3E; }
QGroupBox { font-size: 12px; font-weight: 600; color: #CCCCCC; border: 1px solid #3E3E3E; border-radius: 6px; margin-top: 6px; padding: 10px 6px 6px 6px; background: #2D2D2D; }
QLineEdit { border: 1px solid #3E3E3E; border-radius: 4px; padding: 4px 8px; background: #3C3C3C; color: #E0E0E0; font-size: 12px; min-height: 20px; }
QLineEdit:focus { border-color: #4A9EFF; background: #404040; border: 1px solid #4A9EFF; }
QComboBox { border: 1px solid #3E3E3E; border-radius: 4px; padding: 4px 24px 4px 8px; background: #3C3C3C; color: #E0E0E0; font-size: 12px; min-width: 80px; min-height: 20px; }
QPushButton { background-color: #3C3C3C; color: #CCCCCC; border: 1px solid #555555; border-radius: 4px; padding: 6px 16px; font-size: 12px; font-weight: 500; min-height: 18px; }
QPushButton:hover { background-color: #4A4A4A; border-color: #666666; }
QPushButton:pressed { background-color: #555555; color: #FFFFFF; }
QLabel { color: #CCCCCC; font-size: 12px; background: transparent; }
QCheckBox { spacing: 8px; font-size: 12px; color: #CCCCCC; }
QTabBar::tab { background: transparent; color: #888888; padding: 10px 24px; font-size: 13px; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #4A9EFF; border-bottom: 3px solid #4A9EFF; background: #2D2D2D; }
QPushButton#btn_browse { background-color: #3C3C3C; color: #CCCCCC; border: 1px solid #555555; }
QPushButton#btn_browse:hover { background-color: #4A4A4A; border-color: #666666; }
/* 主操作按钮：唯一强调色（蓝底白字），与中性灰按钮拉开层级 */
QPushButton#btn_action { background-color: #4A9EFF; color: #FFFFFF; border: none; font-weight: 600; }
QPushButton#btn_action:hover { background-color: #6FB0FF; color: #FFFFFF; }
QPushButton#btn_action:pressed { background-color: #2E86F5; color: #FFFFFF; }
QPushButton#btn_reset { background-color: transparent; color: #888888; border: 1px solid #555555; }
QPushButton#btn_reset:hover { background-color: #3C3C3C; border-color: #888888; }
QPushButton#btn_info { background-color: #3C3C3C; color: #CCCCCC; border: 1px solid #555555; }
QPushButton#btn_info:hover { background-color: #4A4A4A; border-color: #666666; }
QPushButton#btn_secondary { background-color: #3C3C3C; color: #CCCCCC; border: 1px solid #555555; }
QPushButton#btn_secondary:hover { background-color: #4A4A4A; border-color: #666666; }
QCheckBox::indicator { border: 2px solid #555555; background: #3C3C3C; }
QCheckBox::indicator:checked { background: #1976D2; border-color: #1976D2; }
QComboBox QAbstractItemView { background: #2D2D2D; color: #E0E0E0; selection-background-color: #1E3A5F; }
QScrollBar:vertical { background: #1E1E1E; }
QScrollBar::handle:vertical { background: #555555; }
QScrollBar:horizontal { background: #1E1E1E; }
QScrollBar::handle:horizontal { background: #555555; }
QStatusBar { background: #252526; color: #CCCCCC; border-top: 1px solid #3E3E3E; }
QToolTip { background: #3C3C3C; color: #E0E0E0; }
QMenu { background: #2D2D2D; color: #E0E0E0; border: 1px solid #3E3E3E; }
QMenu::item:selected { background: #1E3A5F; }
/* 封面控件 _ClickableLabel 继承 QWidget 而非 QLabel，
   必须用纯 id 选择器，带 QLabel 前缀会因类型不匹配而不命中 */
#cover_label { background: #3C3C3C; border: 1px solid #3E3E3E; }
#cover_label:hover { background: #1E3A5F; border-color: #4A9EFF; }
#enc_detect { color: #888888; font-size: 11px; background: transparent; }
QMainWindow[dragging="true"] { background: #1E3A5F; border: 2px dashed #4A9EFF; }
'''


class ThemeManager:
    """主题管理器"""
    
    def __init__(self):
        self._current_theme = Theme.LIGHT
        self._app: Optional[QApplication] = None
    
    def set_app(self, app: QApplication):
        """设置QApplication实例"""
        self._app = app
    
    def get_current_theme(self) -> Theme:
        """获取当前主题"""
        return self._current_theme
    
    def set_theme(self, theme: Theme):
        """设置主题"""
        if self._app is None:
            logger.warning('ThemeManager: QApplication未设置')
            return
        
        self._current_theme = theme
        if theme == Theme.DARK:
            self._app.setStyleSheet(DARK_THEME)
            logger.info('已切换到深色主题')
        else:
            # 尝试从文件加载浅色主题
            qss_path = os.path.join(BASE_DIR, 'resources', 'theme.qss')
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    self._app.setStyleSheet(f.read())
            else:
                self._app.setStyleSheet(LIGHT_THEME)
            logger.info('已切换到浅色主题')
    
    def toggle_theme(self):
        """切换主题"""
        if self._current_theme == Theme.LIGHT:
            self.set_theme(Theme.DARK)
        else:
            self.set_theme(Theme.LIGHT)
    

# 全局主题管理器实例
theme_manager = ThemeManager()
