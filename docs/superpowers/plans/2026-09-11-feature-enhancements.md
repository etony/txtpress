# Feature Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new features: error message optimization, theme switching, chapter regex presets, and custom EPUB styles.

**Architecture:** Extend existing PyQt6 application with new UI components and configuration options. Each feature is independent and can be implemented separately.

**Tech Stack:** PyQt6, JSON configuration, QSS stylesheets

---

## Feature 1: Error Message Optimization

### Task 1.1: Create error message helper module

**Files:**
- Create: `error_handler.py`
- Modify: `window.py:790-1334`

- [ ] **Step 1: Create error_handler.py with user-friendly error messages**

```python
# -*- coding: utf-8 -*-
"""
错误处理模块 - 提供用户友好的错误提示
"""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget


# 错误码到友好提示的映射
ERROR_MESSAGES = {
    # 文件相关
    'file_not_found': '文件不存在，请检查路径是否正确',
    'file_permission': '没有权限访问该文件，请检查文件权限',
    'file_encoding': '文件编码识别失败，请手动选择正确的编码',
    'file_corrupted': '文件已损坏或格式不正确',
    
    # EPUB相关
    'epub_read_failed': '无法读取EPUB文件，文件可能已损坏',
    'epub_write_failed': '保存EPUB文件失败，请检查磁盘空间和写入权限',
    'epub_invalid': '不是有效的EPUB文件格式',
    
    # MOBI相关
    'mobi_read_failed': '无法读取MOBI文件，文件可能已损坏',
    'mobi_no_html': 'MOBI文件中未找到可提取的HTML内容',
    
    # 转换相关
    'regex_invalid': '正则表达式格式错误，请检查语法',
    'conversion_failed': '转换过程中发生错误',
    'chapter_not_found': '未找到匹配的章节标题',
    
    # 封面相关
    'cover_not_found': '未找到封面图片',
    'cover_format_unsupported': '不支持的图片格式，请使用JPG或PNG',
    
    # 磁盘相关
    'disk_full': '磁盘空间不足，请清理后重试',
    'output_path_invalid': '输出路径无效，请选择有效目录',
}


def get_error_message(error_code: str, detail: str = '') -> str:
    """
    获取用户友好的错误提示信息
    
    Args:
        error_code: 错误码
        detail: 额外的错误详情（可选）
    
    Returns:
        友好的错误提示信息
    """
    base_msg = ERROR_MESSAGES.get(error_code, '发生了未知错误')
    if detail:
        return f'{base_msg}\n\n详细信息: {detail}'
    return base_msg


def show_error(parent: QWidget, title: str, error_code: str, detail: str = ''):
    """
    显示用户友好的错误对话框
    
    Args:
        parent: 父窗口
        title: 对话框标题
        error_code: 错误码
        detail: 额外的错误详情（可选）
    """
    msg = get_error_message(error_code, detail)
    QMessageBox.critical(parent, title, msg)


def show_warning(parent: QWidget, title: str, error_code: str, detail: str = ''):
    """
    显示用户友好的警告对话框
    """
    msg = get_error_message(error_code, detail)
    QMessageBox.warning(parent, title, msg)


def show_info(parent: QWidget, title: str, message: str):
    """
    显示信息提示对话框
    """
    QMessageBox.information(parent, title, message)
```

- [ ] **Step 2: Update window.py to use error_handler**

Replace all QMessageBox calls with error_handler functions. Example for line 790:

```python
# Before:
QMessageBox.warning(self, '提示', '请先选择有效的 TXT 文件')

# After:
from error_handler import show_warning
show_warning(self, '提示', 'file_not_found')
```

- [ ] **Step 3: Commit changes**

```bash
git add error_handler.py window.py
git commit -m "feat: add user-friendly error messages module"
```

---

## Feature 2: Theme Switching

### Task 2.1: Create theme manager module

**Files:**
- Create: `theme_manager.py`
- Modify: `window.py`, `resources/theme.qss`

- [ ] **Step 1: Create theme_manager.py**

```python
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

from constants import RES_DIR


class Theme(Enum):
    """主题枚举"""
    LIGHT = 'light'
    DARK = 'dark'


# 浅色主题样式
LIGHT_THEME = '''
QMainWindow { background-color: #FAFAFA; }
QTabWidget::pane { border: none; background: #FFFFFF; border-radius: 8px; padding: 4px 6px; margin: 2px 4px; border: 1px solid #E8E8E8; }
QGroupBox { font-size: 12px; font-weight: 600; color: #424242; border: 1px solid #E0E0E0; border-radius: 6px; margin-top: 6px; padding: 10px 6px 6px 6px; background: #FFFFFF; }
QLineEdit { border: 1px solid #E0E0E0; border-radius: 4px; padding: 4px 8px; background: #FAFAFA; color: #212121; font-size: 12px; min-height: 20px; }
QLineEdit:focus { border-color: #1976D2; background: #FFFFFF; border: 1px solid #1976D2; }
QComboBox { border: 1px solid #E0E0E0; border-radius: 4px; padding: 4px 24px 4px 8px; background: #FAFAFA; color: #212121; font-size: 12px; min-width: 80px; min-height: 20px; }
QPushButton { background-color: #1976D2; color: #FFFFFF; border: none; border-radius: 4px; padding: 6px 16px; font-size: 12px; font-weight: 500; min-height: 18px; }
QPushButton:hover { background-color: #1565C0; }
QLabel { color: #424242; font-size: 12px; background: transparent; }
QCheckBox { spacing: 8px; font-size: 12px; color: #424242; }
'''

# 深色主题样式
DARK_THEME = '''
QMainWindow { background-color: #1E1E1E; }
QTabWidget::pane { border: none; background: #2D2D2D; border-radius: 8px; padding: 4px 6px; margin: 2px 4px; border: 1px solid #3E3E3E; }
QGroupBox { font-size: 12px; font-weight: 600; color: #CCCCCC; border: 1px solid #3E3E3E; border-radius: 6px; margin-top: 6px; padding: 10px 6px 6px 6px; background: #2D2D2D; }
QLineEdit { border: 1px solid #3E3E3E; border-radius: 4px; padding: 4px 8px; background: #3C3C3C; color: #E0E0E0; font-size: 12px; min-height: 20px; }
QLineEdit:focus { border-color: #4A9EFF; background: #404040; border: 1px solid #4A9EFF; }
QComboBox { border: 1px solid #3E3E3E; border-radius: 4px; padding: 4px 24px 4px 8px; background: #3C3C3C; color: #E0E0E0; font-size: 12px; min-width: 80px; min-height: 20px; }
QPushButton { background-color: #0D47A1; color: #FFFFFF; border: none; border-radius: 4px; padding: 6px 16px; font-size: 12px; font-weight: 500; min-height: 18px; }
QPushButton:hover { background-color: #1565C0; }
QLabel { color: #CCCCCC; font-size: 12px; background: transparent; }
QCheckBox { spacing: 8px; font-size: 12px; color: #CCCCCC; }
QTabBar::tab { background: transparent; color: #888888; padding: 10px 24px; font-size: 13px; }
QTabBar::tab:selected { color: #4A9EFF; border-bottom: 3px solid #4A9EFF; background: #2D2D2D; }
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
        else:
            # 尝试从文件加载浅色主题
            qss_path = os.path.join(RES_DIR, '..', 'theme.qss')
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    self._app.setStyleSheet(f.read())
            else:
                self._app.setStyleSheet(LIGHT_THEME)
        
        logger.info(f'主题已切换: {theme.value}')
    
    def toggle_theme(self):
        """切换主题"""
        if self._current_theme == Theme.LIGHT:
            self.set_theme(Theme.DARK)
        else:
            self.set_theme(Theme.LIGHT)


# 全局主题管理器实例
theme_manager = ThemeManager()
```

- [ ] **Step 2: Add theme toggle button to window.py**

Add to `__init__` method after status bar setup:

```python
# ---- 主题切换按钮 ----
from theme_manager import theme_manager, Theme
self._theme_manager = theme_manager
self._theme_manager.set_app(QApplication.instance())

self._theme_btn = QPushButton('🌙')
self._theme_btn.setFixedSize(30, 22)
self._theme_btn.setToolTip('切换深色/浅色主题')
self._theme_btn.clicked.connect(self._toggle_theme)
self.statusBar().addPermanentWidget(self._theme_btn)
```

Add toggle method:

```python
def _toggle_theme(self):
    """切换主题"""
    self._theme_manager.toggle_theme()
    # 更新按钮图标
    if self._theme_manager.get_current_theme() == Theme.DARK:
        self._theme_btn.setText('☀️')
    else:
        self._theme_btn.setText('🌙')
```

- [ ] **Step 3: Save/restore theme in config**

Update `models.py` AppConfig:

```python
@dataclass
class AppConfig:
    # ... existing fields ...
    theme: str = 'light'  # 新增：主题设置
```

Update `_save_config` and `_restore_config` in window.py.

- [ ] **Step 4: Commit changes**

```bash
git add theme_manager.py window.py models.py
git commit -m "feat: add dark/light theme switching"
```

---

## Feature 3: Chapter Regex Presets

### Task 3.1: Add regex presets UI

**Files:**
- Modify: `window.py:337-359` (tab1 options section)

- [ ] **Step 1: Add regex preset definitions to constants.py**

```python
# 章节正则预设
REGEX_PRESETS = {
    '中文标准（第X章）': r'^\s*([第卷][0123456789一二三四五六七八九十零〇百千两]*[章回部节集卷].*)\s*',
    '数字编号（Chapter X）': r'^\s*(Chapter\s+\d+.*)\s*$',
    '数字编号（第X节）': r'^\s*(第\d+节.*)\s*$',
    '卷+章': r'^\s*(卷[一二三四五六七八九十\d]+.*)\s*$',
    '自定义（用户输入）': '',
}
```

- [ ] **Step 2: Update tab1 options section in window.py**

Replace the chapter regex section:

```python
# ---- 高级选项 ----
grp = QGroupBox('选项')
gl = QVBoxLayout(grp)
gl.setSpacing(10)

row = QHBoxLayout()
row.addWidget(QLabel('文件编码:'))
self._cb_encode = QComboBox()
self._cb_encode.addItems(
    ['自动检测', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'shift-jis'])
row.addWidget(self._cb_encode)
row.addSpacing(12)

# 章节正则预设
row.addWidget(QLabel('正则预设:'))
self._cb_regex_preset = QComboBox()
self._cb_regex_preset.addItems(list(REGEX_PRESETS.keys()))
self._cb_regex_preset.currentTextChanged.connect(self._on_regex_preset_changed)
row.addWidget(self._cb_regex_preset)
row.addStretch()
gl.addLayout(row)

row2 = QHBoxLayout()
row2.addWidget(QLabel('章节正则:'))
self._te_reg = QPlainTextEdit()
self._te_reg.setFixedHeight(60)
self._te_reg.setPlaceholderText('自定义章节匹配正则…（留空使用默认正则）')
self._te_reg.setPlainText(
    self._config.chapter_regex or DEFAULT_CHAPTER_REGEX)
row2.addWidget(self._te_reg)
gl.addLayout(row2)

layout.addWidget(grp)
```

Add preset change handler:

```python
def _on_regex_preset_changed(self, preset_name: str):
    """正则预设变更处理"""
    from constants import REGEX_PRESETS
    regex = REGEX_PRESETS.get(preset_name, '')
    if regex:
        self._te_reg.setPlainText(regex)
    # 如果是"自定义"，清空让用户输入
    if preset_name == '自定义（用户输入）':
        self._te_reg.clear()
```

- [ ] **Step 3: Commit changes**

```bash
git add constants.py window.py
git commit -m "feat: add chapter regex presets"
```

---

## Feature 4: Custom EPUB Styles

### Task 4.1: Add EPUB style customization UI

**Files:**
- Create: `styles/` directory with preset CSS files
- Modify: `window.py` (add style options to tab1)
- Modify: `services.py` (accept custom CSS)

- [ ] **Step 1: Create styles directory with preset CSS files**

Create `styles/default.css`:
```css
@namespace epub "http://www.idpf.org/2007/ops";
body {
    font-family: Cambria, "Liberation Serif", Georgia, "Times New Roman", serif;
}
h1 {
    text-align: left; text-indent: 2em;
    font-family: "Microsoft YaHei", sans-serif;
    font-weight: bold; color: #D2691E; line-height: 300%;
    margin: 30px 0 0 0;
}
h2 {
    text-align: left; text-indent: 2em;
    font-family: "Microsoft YaHei", sans-serif;
    font-weight: bold; color: #D2691E; line-height: 240%;
    margin: 20px 0 0 0;
}
p {
    text-indent: 1.25em; margin: 0; widows: 2; orphans: 2;
}
```

Create `styles/minimal.css`:
```css
@namespace epub "http://www.idpf.org/2007/ops";
body { font-family: serif; line-height: 1.6; }
h1, h2 { text-align: center; margin: 1em 0; }
p { text-indent: 2em; margin: 0.5em 0; }
```

Create `styles/modern.css`:
```css
@namespace epub "http://www.idpf.org/2007/ops";
body { font-family: "Helvetica Neue", Arial, sans-serif; line-height: 1.8; color: #333; }
h1 { font-size: 1.8em; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 0.3em; }
h2 { font-size: 1.4em; color: #34495e; }
p { text-indent: 0; margin: 1em 0; }
```

- [ ] **Step 2: Add style selector to tab1 in window.py**

Add after the chapter regex section:

```python
# EPUB样式选择
row3 = QHBoxLayout()
row3.addWidget(QLabel('EPUB样式:'))
self._cb_epub_style = QComboBox()
self._load_epub_styles()
row3.addWidget(self._cb_epub_style)
row3.addStretch()
gl.addLayout(row3)
```

Add helper method:

```python
def _load_epub_styles(self):
    """加载可用的EPUB样式"""
    styles_dir = os.path.join(RES_DIR, '..', 'styles')
    if os.path.exists(styles_dir):
        for f in sorted(os.listdir(styles_dir)):
            if f.endswith('.css'):
                self._cb_epub_style.addItem(f.replace('.css', ''))
    if self._cb_epub_style.count() == 0:
        self._cb_epub_style.addItem('default')
```

- [ ] **Step 3: Update services.py to accept custom CSS**

Modify Txt2Epub.__init__:

```python
def __init__(self, txt_path: str, epub_path: str):
    # ... existing code ...
    self.css_style = CSS_STYLE  # 默认使用内置CSS
```

Add method to load custom CSS:

```python
def load_css_from_file(self, css_path: str):
    """从文件加载自定义CSS样式"""
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            self.css_style = f.read()
```

Update convert method to use self.css_style instead of CSS_STYLE constant.

- [ ] **Step 4: Connect style selection to conversion**

Update `_on_convert_tab1` in window.py:

```python
# 在创建 Txt2Epub 实例后添加：
style_name = self._cb_epub_style.currentText()
styles_dir = os.path.join(RES_DIR, '..', 'styles')
css_path = os.path.join(styles_dir, f'{style_name}.css')
if os.path.exists(css_path):
    conv.load_css_from_file(css_path)
```

- [ ] **Step 5: Commit changes**

```bash
git add styles/ window.py services.py
git commit -m "feat: add custom EPUB style selection"
```

---

## Integration Tasks

### Task 5.1: Update configuration to persist new settings

**Files:**
- Modify: `models.py`
- Modify: `window.py`

- [ ] **Step 1: Add new fields to AppConfig**

```python
@dataclass
class AppConfig:
    # ... existing fields ...
    theme: str = 'light'
    regex_preset: str = '中文标准（第X章）'
    epub_style: str = 'default'
```

- [ ] **Step 2: Update save/restore config methods**

- [ ] **Step 3: Commit changes**

```bash
git add models.py window.py
git commit -m "feat: persist new feature settings in config"
```

---

## Summary

| Feature | Files Modified | Files Created |
|---------|---------------|---------------|
| Error Messages | window.py | error_handler.py |
| Theme Switching | window.py, models.py | theme_manager.py |
| Regex Presets | window.py, constants.py | - |
| EPUB Styles | window.py, services.py | styles/*.css |

**Total Estimated Time:** 2-3 hours

**Dependencies:** None (features are independent)
