# -*- coding: utf-8 -*-
"""
TxtPress — 电子书格式转换工具。主窗口，Tab 布局，绑定所有用户交互。

这个文件是程序的"骨架"——负责所有 UI 控件的创建、布局和事件绑定。
代码量最大，但逻辑清晰：分为 3 个 Tab，每个 Tab 有"设置"和"操作"两部分。

文件结构：
  1. 辅助控件（_ClickableLabel）
  2. MainWindow 主体
     - __init__:      窗口初始化、状态变量、进度条
     - _setup_tab1:   TXT → EPUB 的 UI 控件
     - _setup_tab2:   EPUB → TXT 的 UI 控件
     - _setup_tab3:   MOBI → TXT 的 UI 控件
     - 快捷键 & 拖放
     - 槽函数（每个按钮的点击逻辑）
     - _run_worker:   后台线程管理
     - 辅助方法：配置保存/恢复、打开目录等
"""

from __future__ import annotations

import os
import re
import sys
import datetime

from loguru import logger
import chardet

from PyQt6.QtCore import Qt, pyqtSlot, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QGroupBox, QLabel, QLineEdit, QComboBox,
    QPushButton, QPlainTextEdit, QCheckBox, QProgressBar,
    QFileDialog, QMessageBox, QApplication,
)
from PyQt6.QtGui import QIcon, QPixmap, QImage

from models import AppConfig, BookInfo
from services import Txt2Epub, Epub2Txt, Epub2Mobi, convert_mobi_to_txt
from worker import ProgressWorker
from dialogs import ChapterDialog, AboutDialog


# ---- 资源路径 ----
# _BASE_DIR: 当前文件所在目录，用于定位资源文件和 config.json
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RES_DIR = os.path.join(_BASE_DIR, 'resources', 'images')  # 图片资源目录
_CONFIG_PATH = os.path.join(_BASE_DIR, 'config.json')       # 配置文件路径


# ---- 辅助控件：可点击标签 ----
# QLabel 默认没有 clicked 信号，这个子类加了一个。
# 在 tab1 和 tab2 中，点击封面图片可以更换封面。

class _ClickableLabel(QLabel):
    """支持 clicked 信号的 QLabel。"""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        """重写鼠标点击事件，发射 clicked 信号。"""
        self.clicked.emit()


# =====================================================================
# 主窗口
# =====================================================================

class MainWindow(QMainWindow):
    """
    Txt↔Epub/Mobi 转换工具主窗口。

    包含三个 Tab：
      0: TXT → EPUB  （生成电子书）
      1: EPUB → TXT  （提取文本）
      2: MOBI → TXT  （额外的格式支持）

    每个 Tab 包含若干 QGroupBox 区域，通过垂直/水平布局排列。
    耗时操作通过 ProgressWorker 在后台线程执行，避免界面卡顿。
    """

    def __init__(self):
        super().__init__()

        # ---- 状态变量 ----
        # 这些变量在窗口生命周期内保持状态，跨函数共享
        self._txt_cover = ''                       # tab1 封面路径（用户选择的）
        self._epub_cover_path = ''                 # tab2 封面路径（用于修改 EPUB 元信息）
        self._txt_dir = ''                         # 当前 TXT 文件所在目录（方便自动填充路径）
        self._epub_dir = ''                        # 当前 EPUB 文件所在目录
        self._config = AppConfig.load(_CONFIG_PATH) # 从 config.json 加载的配置
        self._worker: ProgressWorker | None = None # 当前正在运行的后台线程
        self._ordered_chapters: list[str] | None = None  # 用户通过 ChapterDialog 调整后的章节顺序

        # ---- 窗口基础 ----
        self.setWindowTitle('TxtPress — 电子书格式转换工具')
        self.setWindowIcon(QIcon(os.path.join(_RES_DIR, 'bookinfo.ico')))
        self.setMinimumSize(720, 560)
        self.resize(800, 700)  # 默认窗口大小，确保内容完整显示

        # ---- 中央控件 ----
        # 整个窗口分为：Tab 标签页 + 底部状态栏
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)  # 去掉外边距，让 Tab 撑满
        root.setSpacing(0)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        # 按顺序创建三个 Tab
        self._setup_tab1()   # TXT → EPUB
        self._setup_tab2()   # EPUB → TXT
        self._setup_tab3()   # MOBI → TXT

        # ---- 状态栏 ----
        # 状态栏右下角固定显示进度条（默认隐藏，转换时显示）
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setFixedHeight(14)
        self.statusBar().addPermanentWidget(self._progress_bar)
        self.statusBar().showMessage('就绪')

        # ---- 快捷键 ----
        self._setup_shortcuts()

        # ---- 加载配置（恢复上次设置）----
        self._restore_config()

        logger.info('程序加载完成')

    # ================================================================
    # Tab 1: TXT → EPUB
    # ================================================================

    def _setup_tab1(self):
        """
        构建 Tab 1 的 UI 控件。

        布局（从上到下）：
          源文件    → TXT 文件路径 + EPUB 保存路径
          书籍信息  → 书名 / 作者 / 贡献者 / 日期 / 描述 / 封面
          高级选项  → 文件编码 + 章节正则
          操作      → 目录预览 / 重置 / 开始转换 / →MOBI
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(2, 4, 2, 4)

        # ---- 源文件 ----
        # 用户选择 TXT 源文件和指定 EPUB 输出位置
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        h = QHBoxLayout()
        h.addWidget(QLabel('TXT 文件:'))
        self._le_txt = QLineEdit()
        self._le_txt.setPlaceholderText('选择 TXT 源文件…')
        # 支持从文件管理器直接拖放文件到输入框
        self._le_txt.setAcceptDrops(True)
        self._le_txt.dragEnterEvent = lambda e: self._line_drag_enter(e, '.txt')
        self._le_txt.dropEvent = lambda e: self._line_drop(e, self._le_txt)
        h.addWidget(self._le_txt)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(self._on_browse_txt)
        h.addWidget(btn)
        gl.addLayout(h)

        h = QHBoxLayout()
        h.addWidget(QLabel('EPUB 保存:'))
        self._le_epub = QLineEdit()
        self._le_epub.setPlaceholderText('自动生成或手动选择…')
        h.addWidget(self._le_epub)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(self._on_browse_epub)
        h.addWidget(btn)
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 书籍信息 ----
        # 这些字段会写入 EPUB 的元数据区，阅读器中可以看到
        grp = QGroupBox('书籍信息')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        # 第一行：书名 + 作者
        h = QHBoxLayout()
        h.addWidget(QLabel('书名:'))
        self._le_title = QLineEdit()
        self._le_title.setPlaceholderText('默认 = 文件名')
        h.addWidget(self._le_title)
        h.addWidget(QLabel('作者:'))
        self._le_author = QLineEdit()
        self._le_author.setPlaceholderText('默认 = 作者')
        h.addWidget(self._le_author)
        gl.addLayout(h)

        # 第二行：贡献者 + 日期
        h = QHBoxLayout()
        h.addWidget(QLabel('贡献者:'))
        self._le_txt_contrib = QLineEdit()
        self._le_txt_contrib.setPlaceholderText('默认 etony.an@gmail.com')
        h.addWidget(self._le_txt_contrib)
        h.addWidget(QLabel('日期:'))
        self._le_txt_date = QLineEdit()
        self._le_txt_date.setPlaceholderText('默认当前时间 (yyyy-mm-dd)')
        h.addWidget(self._le_txt_date)
        gl.addLayout(h)

        # 第三行：描述
        h = QHBoxLayout()
        h.addWidget(QLabel('描述:'))
        self._le_txt_desc = QLineEdit()
        self._le_txt_desc.setPlaceholderText('EPUB 描述信息 (dc:description，可选)')
        h.addWidget(self._le_txt_desc)
        gl.addLayout(h)

        # 第四行：封面图片 + 选择按钮
        h = QHBoxLayout()
        self._cover_label = _ClickableLabel()
        self._cover_label.setObjectName('cover_label')
        self._cover_label.setFixedSize(100, 140)
        self._cover_label.setScaledContents(True)  # 图片自动缩放填满标签
        self._cover_label.setPixmap(QPixmap(os.path.join(_RES_DIR, 'cover.jpeg')))
        self._cover_label.clicked.connect(self._on_choose_cover)
        h.addWidget(self._cover_label)
        btn = QPushButton('选择封面')
        btn.setObjectName('btn_secondary')
        btn.setToolTip('选择 EPUB 封面图片')
        btn.clicked.connect(self._on_choose_cover)
        h.addWidget(btn)
        h.addStretch()
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 高级选项 ----
        # 编码和正则表达式，普通用户一般不需要修改
        grp = QGroupBox('高级选项')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        h = QHBoxLayout()
        h.addWidget(QLabel('文件编码:'))
        self._cb_encode = QComboBox()
        self._cb_encode.addItems(
            ['自动检测', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'shift-jis'])
        h.addWidget(self._cb_encode)
        h.addSpacing(20)
        h.addWidget(QLabel('章节正则:'))
        self._te_reg = QPlainTextEdit()
        self._te_reg.setFixedHeight(60)
        self._te_reg.setPlaceholderText('自定义章节匹配正则…')
        self._te_reg.setPlainText(self._config.chapter_regex)
        h.addWidget(self._te_reg)
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 操作 ----
        # 底部按钮区域：辅助功能在左，主要操作在右
        grp = QGroupBox('操作')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        btn = QPushButton('📑 目录预览')
        btn.setToolTip('预览 TXT 文件中的章节列表')
        btn.setObjectName('btn_secondary')
        btn.clicked.connect(self._on_preview_chapters)
        gl.addWidget(btn)

        btn = QPushButton('↺ 重置')
        btn.setObjectName('btn_reset')
        btn.setToolTip('清空所有输入')
        btn.clicked.connect(self._on_reset_tab1)
        gl.addWidget(btn)

        gl.addStretch()

        btn = QPushButton('▶ 开始转换')
        btn.setObjectName('btn_action')
        btn.setToolTip('将 TXT 转换为 EPUB（Ctrl+Enter）')
        btn.clicked.connect(self._on_convert_tab1)
        gl.addWidget(btn)

        btn = QPushButton('→MOBI')
        btn.setObjectName('btn_danger')
        btn.setToolTip('将 EPUB 转换为 MOBI（需要 Calibre）')
        btn.clicked.connect(self._on_convert_mobi)
        gl.addWidget(btn)

        layout.addWidget(grp)
        layout.addStretch()

        self._tabs.addTab(tab, 'TXT → EPUB')

        # 记录 tab1 中的可聚焦控件，供快捷键使用
        self._tab1_focus = [self._le_txt, self._le_epub, self._le_title,
                            self._le_author, self._cb_encode, self._te_reg]

    # ================================================================
    # Tab 2: EPUB → TXT
    # ================================================================

    def _setup_tab2(self):
        """
        构建 Tab 2 的 UI 控件。

        相比 Tab 1，增加了"繁简转换"选项和多种输出模式。
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(2, 4, 2, 4)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        h = QHBoxLayout()
        h.addWidget(QLabel('EPUB 文件:'))
        self._le_in_epub = QLineEdit()
        self._le_in_epub.setPlaceholderText('选择 EPUB 源文件…')
        self._le_in_epub.setAcceptDrops(True)
        self._le_in_epub.dragEnterEvent = lambda e: self._line_drag_enter(e, '.epub')
        self._le_in_epub.dropEvent = lambda e: self._line_drop(e, self._le_in_epub)
        h.addWidget(self._le_in_epub)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(self._on_browse_in_epub)
        h.addWidget(btn)
        gl.addLayout(h)

        h = QHBoxLayout()
        h.addWidget(QLabel('TXT 保存:'))
        self._le_out_txt = QLineEdit()
        self._le_out_txt.setPlaceholderText('自动生成或手动选择…')
        h.addWidget(self._le_out_txt)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(self._on_browse_out_txt)
        h.addWidget(btn)
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 书籍信息 ----
        # 从 EPUB 中读取的元数据，可以修改后写回
        grp = QGroupBox('书籍信息')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        h = QHBoxLayout()
        h.addWidget(QLabel('书名:'))
        self._le_book_title = QLineEdit()
        h.addWidget(self._le_book_title)
        h.addWidget(QLabel('作者:'))
        self._le_book_creator = QLineEdit()
        h.addWidget(self._le_book_creator)
        gl.addLayout(h)

        h = QHBoxLayout()
        h.addWidget(QLabel('贡献者:'))
        self._le_book_contrib = QLineEdit()
        h.addWidget(self._le_book_contrib)
        h.addWidget(QLabel('日期:'))
        self._le_book_date = QLineEdit()
        h.addWidget(self._le_book_date)
        gl.addLayout(h)

        h = QHBoxLayout()
        h.addWidget(QLabel('描述:'))
        self._le_book_desc = QLineEdit()
        self._le_book_desc.setPlaceholderText('EPUB 描述信息 (dc:description)')
        h.addWidget(self._le_book_desc)
        gl.addLayout(h)

        h = QHBoxLayout()
        self._cover_label2 = _ClickableLabel()
        self._cover_label2.setObjectName('cover_label')
        self._cover_label2.setFixedSize(100, 140)
        self._cover_label2.setScaledContents(True)
        self._cover_label2.setPixmap(QPixmap(os.path.join(_RES_DIR, 'cover.jpeg')))
        self._cover_label2.clicked.connect(self._on_choose_cover2)
        h.addWidget(self._cover_label2)

        v = QVBoxLayout()
        btn = QPushButton('更换封面')
        btn.setObjectName('btn_secondary')
        btn.setToolTip('选择新封面图片')
        btn.clicked.connect(self._on_choose_cover2)
        v.addWidget(btn)
        btn = QPushButton('保存元信息')
        btn.setObjectName('btn_browse')
        btn.setToolTip('将当前编辑的元信息写回 EPUB 文件')
        btn.clicked.connect(self._on_save_metadata)
        v.addWidget(btn)
        h.addLayout(v)
        h.addStretch()
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 选项 ----
        # 输出编码、章节分隔符、繁简转换
        grp = QGroupBox('选项')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        gl.addWidget(QLabel('输出编码:'))
        self._cb_out_code = QComboBox()
        self._cb_out_code.addItems(['utf-8', 'gbk', 'gb2312', 'big5'])
        gl.addWidget(self._cb_out_code)

        gl.addSpacing(12)
        gl.addWidget(QLabel('章节分隔:'))
        self._cb_sep = QComboBox()
        # \\n 在显示时为 "\n"，用户选择后被替换成真正的换行符
        self._cb_sep.addItems(['（无）', '\\n', '\\n\\n', '\\n---\\n'])
        gl.addWidget(self._cb_sep)

        gl.addSpacing(12)
        self._chb_fanjian = QCheckBox('繁→简转换')
        self._chb_fanjian.setToolTip('将繁体中文转换为简体中文')
        self._chb_fanjian.stateChanged.connect(self._on_fanjian_toggled)
        gl.addWidget(self._chb_fanjian)
        gl.addStretch()
        layout.addWidget(grp)

        # ---- 操作 ----
        # 合并转换、按章节导出、提取图片、重置
        grp = QGroupBox('操作')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        btn = QPushButton('▶ 合并转换')
        btn.setObjectName('btn_action')
        btn.setToolTip('将 EPUB 所有章节合并为一个 TXT 文件')
        btn.clicked.connect(self._on_convert_tab2)
        gl.addWidget(btn)

        btn = QPushButton('📄 按章节导出')
        btn.setToolTip('每章导出为一个独立的 TXT 文件')
        btn.setObjectName('btn_secondary')
        btn.clicked.connect(self._on_convert_chapter)
        gl.addWidget(btn)

        btn = QPushButton('🖼 提取图片')
        btn.setToolTip('将 EPUB 中的所有图片提取到 images/ 目录')
        btn.setObjectName('btn_secondary')
        btn.clicked.connect(self._on_extract_images)
        gl.addWidget(btn)

        btn = QPushButton('↺ 重置')
        btn.setObjectName('btn_reset')
        btn.clicked.connect(self._on_reset_tab2)
        gl.addWidget(btn)

        layout.addWidget(grp)
        layout.addStretch()

        self._tabs.addTab(tab, 'EPUB → TXT')

    # ================================================================
    # Tab 3: MOBI → TXT
    # ================================================================

    def _setup_tab3(self):
        """
        构建 Tab 3 的 UI 控件。

        最简单的 Tab：选择 MOBI 文件 + 输出 TXT 路径 + 转换按钮。
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(2, 4, 2, 4)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        h = QHBoxLayout()
        h.addWidget(QLabel('MOBI 文件:'))
        self._le_mobi = QLineEdit()
        self._le_mobi.setPlaceholderText('选择 MOBI 源文件…')
        h.addWidget(self._le_mobi)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(self._on_browse_mobi)
        h.addWidget(btn)
        gl.addLayout(h)

        h = QHBoxLayout()
        h.addWidget(QLabel('TXT 保存:'))
        self._le_mobi_txt = QLineEdit()
        self._le_mobi_txt.setPlaceholderText('自动生成或手动选择…')
        h.addWidget(self._le_mobi_txt)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(self._on_browse_mobi_txt)
        h.addWidget(btn)
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 操作 ----
        grp = QGroupBox('操作')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        btn = QPushButton('▶ 转换为 TXT')
        btn.setObjectName('btn_action')
        btn.setToolTip('将 MOBI 文件转换为 TXT')
        btn.clicked.connect(self._on_convert_mobi_to_txt)
        gl.addWidget(btn)

        btn = QPushButton('↺ 重置')
        btn.setObjectName('btn_reset')
        btn.clicked.connect(self._on_reset_tab3)
        gl.addWidget(btn)

        gl.addStretch()
        layout.addWidget(grp)
        layout.addStretch()

        self._tabs.addTab(tab, 'MOBI → TXT')

    # ================================================================
    # 快捷键
    # ================================================================

    def _setup_shortcuts(self):
        """
        注册全局快捷键。

        QShortcut 绑定到窗口（self），即窗口获得焦点时生效。
        Ctrl+Enter 和 Ctrl+Return 是两个不同的键码，都要绑定。
        """
        from PyQt6.QtGui import QShortcut, QKeySequence

        QShortcut(QKeySequence('Ctrl+Return'), self).activated.connect(
            self._on_shortcut_convert)
        QShortcut(QKeySequence('Ctrl+Enter'), self).activated.connect(
            self._on_shortcut_convert)
        QShortcut(QKeySequence('Ctrl+O'), self).activated.connect(
            self._on_shortcut_open)
        QShortcut(QKeySequence('Ctrl+R'), self).activated.connect(
            self._on_shortcut_reset)
        QShortcut(QKeySequence('F1'), self).activated.connect(
            self._on_about)

    # ================================================================
    # Drag & Drop（窗口级 + 行级）
    # ================================================================

    def dragEnterEvent(self, event):
        """
        窗口级拖入事件。

        当用户从文件管理器拖文件到窗口上时触发。
        只接受单个 .txt 或 .epub 文件的拖入。
        """
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                path = urls[0].toLocalFile().lower()
                if path.endswith('.txt') or path.endswith('.epub'):
                    event.acceptProposedAction()

    def dropEvent(self, event):
        """
        窗口级放下事件。

        根据文件类型自动切换到对应 Tab：
        .txt  → 切换到 Tab 1（TXT→EPUB）并加载文件
        .epub → 切换到 Tab 2（EPUB→TXT）并加载文件
        """
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith('.txt'):
                self._tabs.setCurrentIndex(0)
                self._load_txt_file(path)
            elif path.lower().endswith('.epub'):
                self._tabs.setCurrentIndex(1)
                self._load_epub_file(path)

    def _line_drag_enter(self, event, ext: str):
        """行级输入框拖入事件——只接受指定扩展名的文件。"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(ext):
                event.acceptProposedAction()

    def _line_drop(self, event, line_edit: QLineEdit):
        """行级输入框放下事件——将文件路径设到输入框。"""
        urls = event.mimeData().urls()
        if urls:
            line_edit.setText(urls[0].toLocalFile())

    # ================================================================
    # Tab 1：槽函数
    # ================================================================

    def _on_browse_txt(self):
        """浏览按钮——打开文件选择对话框，选择 TXT 文件。"""
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 TXT 文件', '.', '*.txt;;All Files(*)')
        if path:
            self._load_txt_file(path)

    def _load_txt_file(self, path: str):
        """
        加载 TXT 文件到界面。

        这是浏览和拖放的公共入口。做了三件事：
        1. 把路径设到输入框
        2. 自动填充 EPUB 输出路径、书名、作者、描述
        3. 用 chardet 检测文件编码，显示在状态栏
        """
        self._le_txt.setText(path)
        self._txt_dir, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)

        # 自动填充：书名/作者用文件名，EPUB 输出路径与 TXT 同目录
        self._le_epub.setText(os.path.join(self._txt_dir, base + '.epub'))
        self._le_title.setText(base.strip())
        self._le_author.setText(base.strip())
        self._le_txt_desc.setText('原始内容源于互联网，仅供个人学习娱乐使用。')

        # 编码检测——读取文件前 512 字节自动判断编码
        with open(path, 'rb') as f:
            data = f.read(512)
            info = chardet.detect(data)
            enc = info['encoding'] or 'utf-8'
            self.statusBar().showMessage(f'文件: {fname}  编码: {enc}')
            logger.info(f'文件检测: {fname} 编码={enc} 语言={info["language"]}')

        logger.info(f'选择 TXT: {path}')

    def _on_browse_epub(self):
        """浏览——选择 EPUB 保存路径（必须是 .epub 扩展名）。"""
        if not self._le_txt.text():
            self.statusBar().showMessage('请先选择 TXT 文件')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, 'EPUB 保存位置',
            os.path.join(self._txt_dir, 'output'), '*.epub')
        if path:
            self._le_epub.setText(path)

    def _on_choose_cover(self):
        """选择封面图片（tab1）。"""
        path, _ = QFileDialog.getOpenFileName(
            self, '选择封面', '.', 'Images (*.jpg *.png *.jpeg);;All Files(*)')
        if path:
            self._txt_cover = path
            self._cover_label.setPixmap(QPixmap(path))
            logger.info(f'封面: {path}')

    def _on_preview_chapters(self):
        """
        目录预览。

        用当前设置的编码和正则解析 TXT，提取章节标题列表，
        弹出 ChapterDialog 供用户查看、排序、重命名。
        如果用户调整了顺序，保存到 self._ordered_chapters。
        """
        txt = self._le_txt.text().strip()
        if not txt or not os.path.exists(txt):
            QMessageBox.warning(self, '提示', '请先选择有效的 TXT 文件')
            return

        try:
            conv = Txt2Epub(txt, self._le_epub.text() or txt + '.epub')
            if self._cb_encode.currentIndex() != 0:
                conv.encoding = self._cb_encode.currentText()
            reg = self._te_reg.toPlainText().strip()
            if len(reg) >= 5:
                conv.regex = reg
            chapters = conv.get_chapters()
            dlg = ChapterDialog(chapters, self)
            # exec() 返回 QDialog.Accepted（确定）或 Rejected（关闭）
            if dlg.exec():
                ordered = dlg.get_ordered_chapters()
                if ordered != chapters:
                    self._ordered_chapters = ordered
                    self.statusBar().showMessage(
                        f'章节顺序已调整（{len(ordered)} 章）')
                else:
                    self._ordered_chapters = None
        except Exception as e:
            QMessageBox.critical(self, '错误', f'解析目录失败:\n{e}')
            logger.exception('目录预览失败')

    def _on_reset_tab1(self):
        """重置 tab1 的所有输入。"""
        self._le_txt.clear()
        self._le_epub.clear()
        self._le_title.clear()
        self._le_author.clear()
        self._le_txt_contrib.clear()
        self._le_txt_date.clear()
        self._le_txt_desc.clear()
        self._txt_cover = ''
        self._cover_label.setPixmap(
            QPixmap(os.path.join(_RES_DIR, 'cover.jpeg')))
        self._cb_encode.setCurrentIndex(0)
        self._te_reg.setPlainText(self._config.chapter_regex)
        self._ordered_chapters = None
        self.statusBar().showMessage('已重置')
        logger.info('tab1 重置')

    def _on_convert_tab1(self):
        """
        开始 TXT→EPUB 转换。

        1. 校验输入
        2. 创建 Txt2Epub 实例，设置用户填写的属性
        3. 通过 _run_worker 在后台线程执行
        """
        txt = self._le_txt.text().strip()
        epub = self._le_epub.text().strip()
        if not txt or not os.path.exists(txt):
            QMessageBox.warning(self, '提示', '请选择有效的 TXT 文件')
            return
        if not epub:
            QMessageBox.warning(self, '提示', '请指定 EPUB 保存路径')
            return

        self._save_config()

        conv = Txt2Epub(txt, epub)
        # 只把用户填了值的字段传给转换器
        if self._le_title.text().strip():
            conv.title = self._le_title.text().strip()
        if self._le_author.text().strip():
            conv.author = self._le_author.text().strip()
        if self._le_txt_contrib.text().strip():
            conv.contributor = self._le_txt_contrib.text().strip()
        if self._le_txt_date.text().strip():
            conv.date = self._le_txt_date.text().strip()
        if self._le_txt_desc.text().strip():
            conv.description = self._le_txt_desc.text().strip()
        if self._txt_cover:
            conv.cover_path = self._txt_cover
        if self._cb_encode.currentIndex() != 0:
            conv.encoding = self._cb_encode.currentText()
        reg = self._te_reg.toPlainText().strip()
        if len(reg) >= 5:
            conv.regex = reg
        # 如果有自定义章节顺序，传给转换器
        if self._ordered_chapters:
            conv._chapter_order = self._ordered_chapters

        self._run_worker(
            target=conv.convert,
            success_msg='TXT→EPUB 转换完成',
            dir_to_open=os.path.dirname(epub),
        )

    def _on_convert_mobi(self):
        """
        EPUB→MOBI（框架接口）。

        当前只是占位符，因为 MOBI 转换需要 Calibre 的 ebook-convert 工具。
        等后续实现真正转换。
        """
        epub_path = self._le_epub.text().strip()
        if not epub_path:
            QMessageBox.warning(self, '提示', '请先生成或指定 EPUB 文件')
            return
        mobi_path = epub_path.rsplit('.', 1)[0] + '.mobi'
        try:
            conv = Epub2Mobi(epub_path, mobi_path)
            conv.convert()
        except NotImplementedError as e:
            QMessageBox.information(self, '提示', str(e))

    # ================================================================
    # Tab 2：槽函数
    # ================================================================

    def _on_browse_in_epub(self):
        """浏览——选择 EPUB 文件。"""
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 EPUB 文件', '.', '*.epub;;All Files(*)')
        if path:
            self._load_epub_file(path)

    def _load_epub_file(self, path: str):
        """
        加载 EPUB 文件到界面。

        读取 EPUB 的元数据和封面，展示到对应的输入框中。
        用户可以直接修改这些信息并通过"保存元信息"写回。

        Args:
            path: EPUB 文件路径
        """
        self._le_in_epub.setText(path)
        self._epub_dir, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)

        # 自动填充 TXT 输出路径（与 EPUB 同目录同名）
        txt_path = os.path.join(self._epub_dir, base + '.txt')
        self._le_out_txt.setText(txt_path)

        # 提取元数据并填充到输入框
        try:
            reader = Epub2Txt(path, txt_path)
            info = reader.get_info()
            self._le_book_title.setText(info.title)
            self._le_book_creator.setText(info.creator)
            self._le_book_contrib.setText(info.contributor)
            if info.date:
                try:
                    # ISO 格式转成更友好的显示格式
                    dt = datetime.datetime.fromisoformat(info.date)
                    self._le_book_date.setText(
                        dt.strftime('%Y-%m-%d %H:%M:%S'))
                except Exception:
                    self._le_book_date.setText(info.date)
            self._le_book_desc.setText(info.description)

            # 加载封面图片
            cover_data = reader.get_cover()
            if cover_data:
                img = QImage.fromData(cover_data)
                self._cover_label2.setPixmap(QPixmap.fromImage(img))

            logger.info(f'EPUB 信息: {info}')
            self.statusBar().showMessage(f'已加载: {fname}')
        except Exception as e:
            QMessageBox.warning(self, '提示', f'读取 EPUB 失败:\n{e}')
            logger.exception('加载 EPUB 失败')

    def _on_browse_out_txt(self):
        """浏览——选择 TXT 保存路径。"""
        path, _ = QFileDialog.getSaveFileName(
            self, 'TXT 保存位置',
            os.path.join(self._epub_dir, 'output'), '*.txt')
        if path:
            self._le_out_txt.setText(path)

    def _on_choose_cover2(self):
        """选择封面图片（tab2，用于修改 EPUB 元信息）。"""
        path, _ = QFileDialog.getOpenFileName(
            self, '选择封面', '.', 'Images (*.jpg *.png *.jpeg);;All Files(*)')
        if path:
            self._epub_cover_path = path
            self._cover_label2.setPixmap(QPixmap(path))

    def _on_save_metadata(self):
        """
        保存元信息到 EPUB。

        把用户在 tab2 书籍信息区填写的内容写回 EPUB 文件。
        包括：标题、作者、贡献者、日期、描述、封面。
        """
        epub_path = self._le_in_epub.text().strip()
        if not epub_path or not os.path.exists(epub_path):
            QMessageBox.warning(self, '提示', '请先选择 EPUB 文件')
            return

        try:
            reader = Epub2Txt(epub_path, self._le_out_txt.text() or '')
            info = BookInfo(
                title=self._le_book_title.text(),
                creator=self._le_book_creator.text(),
                contributor=self._le_book_contrib.text(),
                date=self._le_book_date.text(),
                description=self._le_book_desc.text(),
            )
            if self._epub_cover_path:
                with open(self._epub_cover_path, 'rb') as f:
                    info.cover = f.read()
            reader.modi(info)
            self.statusBar().showMessage('元信息保存完成')
            logger.info(f'元信息已更新: {epub_path}')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'保存失败:\n{e}')
            logger.exception('保存元信息失败')

    def _on_convert_tab2(self):
        """EPUB→TXT 合并转换——所有章节合并为一个 TXT 文件。"""
        epub_path = self._le_in_epub.text().strip()
        txt_path = self._le_out_txt.text().strip()
        if not epub_path or not os.path.exists(epub_path):
            QMessageBox.warning(self, '提示', '请选择有效的 EPUB 文件')
            return
        if not txt_path:
            QMessageBox.warning(self, '提示', '请指定 TXT 保存路径')
            return

        self._save_config()

        reader = Epub2Txt(epub_path, txt_path)
        if self._cb_out_code.currentIndex() != 0:
            reader.encoding = self._cb_out_code.currentText()
        sep = self._cb_sep.currentText()
        if sep and sep != '（无）':
            reader.sep = sep.replace('\\n', '\n')
        fanjian = self._chb_fanjian.isChecked()

        self._run_worker(
            target=lambda progress, status: reader.convert(
                fanjian=fanjian, progress=progress, status=status),
            success_msg='EPUB→TXT 转换完成',
            dir_to_open=os.path.dirname(txt_path),
        )

    def _on_convert_chapter(self):
        """EPUB→TXT 按章节导出——每章导出为一个独立的 TXT 文件。"""
        epub_path = self._le_in_epub.text().strip()
        txt_path = self._le_out_txt.text().strip()
        if not epub_path or not os.path.exists(epub_path):
            QMessageBox.warning(self, '提示', '请选择有效的 EPUB 文件')
            return
        if not txt_path:
            QMessageBox.warning(self, '提示', '请指定 TXT 保存路径')
            return

        self._save_config()

        reader = Epub2Txt(epub_path, txt_path)
        if self._cb_out_code.currentIndex() != 0:
            reader.encoding = self._cb_out_code.currentText()
        sep = self._cb_sep.currentText()
        if sep and sep != '（无）':
            reader.sep = sep.replace('\\n', '\n')
        fanjian = self._chb_fanjian.isChecked()

        self._run_worker(
            target=lambda progress, status: reader.convert_chapter(
                fanjian=fanjian, progress=progress, status=status),
            success_msg='按章节导出完成',
            dir_to_open=os.path.dirname(txt_path),
        )

    def _on_extract_images(self):
        """
        提取 EPUB 内嵌图片。

        将 EPUB 中的所有图片提取到输出目录的 images/ 子目录下。
        完成后询问用户是否打开目录。
        """
        epub_path = self._le_in_epub.text().strip()
        if not epub_path or not os.path.exists(epub_path):
            QMessageBox.warning(self, '提示', '请先选择 EPUB 文件')
            return

        out_dir = os.path.join(os.path.dirname(epub_path), 'images')
        os.makedirs(out_dir, exist_ok=True)

        try:
            reader = Epub2Txt(epub_path, '')
            files = reader.extract_images(out_dir)
            if files:
                msg = f'成功提取 {len(files)} 张图片到:\n{out_dir}'
                logger.info(msg)
                if QMessageBox.question(
                    self, '提取完成', msg + '\n打开目录？',
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                ) == QMessageBox.StandardButton.Yes:
                    self._open_dir(out_dir)
            else:
                QMessageBox.information(self, '提取完成', '未找到图片')
                logger.info('提取图片: 未找到图片')
        except Exception as e:
            QMessageBox.critical(self, '错误', f'提取失败:\n{e}')
            logger.exception('提取图片失败')

    def _on_fanjian_toggled(self, state):
        """
        繁简转换复选框状态变化。

        勾选时：将 EPUB 文件名（中文部分）转为简体，作为 TXT 文件名。
        取消勾选时：恢复为原始文件名。
        """
        epub_path = self._le_in_epub.text().strip()
        if not epub_path:
            return
        d, fname = os.path.split(epub_path)
        base, ext = os.path.splitext(fname)
        if state == Qt.CheckState.Checked.value:
            from opencc import OpenCC
            cc = OpenCC('t2s')
            new_base = cc.convert(base)
            self._le_out_txt.setText(os.path.join(d, new_base + '.txt'))
        else:
            self._le_out_txt.setText(os.path.join(d, base + '.txt'))

    def _on_reset_tab2(self):
        """重置 tab2 的所有输入。"""
        self._le_in_epub.clear()
        self._le_out_txt.clear()
        self._le_book_title.clear()
        self._le_book_creator.clear()
        self._le_book_contrib.clear()
        self._le_book_date.clear()
        self._le_book_desc.clear()
        self._epub_cover_path = ''
        self._cover_label2.setPixmap(
            QPixmap(os.path.join(_RES_DIR, 'cover.jpeg')))
        self._cb_out_code.setCurrentIndex(0)
        self._cb_sep.setCurrentIndex(0)
        self._chb_fanjian.setChecked(False)
        self.statusBar().showMessage('已重置')
        logger.info('tab2 重置')

    # ================================================================
    # Tab 3：槽函数
    # ================================================================

    def _on_browse_mobi(self):
        """浏览——选择 MOBI 文件，并自动生成 TXT 保存路径。"""
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 MOBI 文件', '.', '*.mobi;;All Files(*)')
        if path:
            self._le_mobi.setText(path)
            d, fname = os.path.split(path)
            base, _ = os.path.splitext(fname)
            self._le_mobi_txt.setText(os.path.join(d, base + '.txt'))

    def _on_browse_mobi_txt(self):
        """浏览——选择 TXT 保存路径。"""
        path, _ = QFileDialog.getSaveFileName(
            self, 'TXT 保存位置', '.', '*.txt')
        if path:
            self._le_mobi_txt.setText(path)

    def _on_convert_mobi_to_txt(self):
        """MOBI→TXT 转换——在后台线程中执行。"""
        mobi_path = self._le_mobi.text().strip()
        if not mobi_path or not os.path.exists(mobi_path):
            QMessageBox.warning(self, '提示', '请选择有效的 MOBI 文件')
            return
        txt_path = self._le_mobi_txt.text().strip()
        if not txt_path:
            QMessageBox.warning(self, '提示', '请指定 TXT 保存路径')
            return

        from pathlib import Path as _Path

        def _do(progress, status):
            """后台执行 MOBI 转换的入口函数。"""
            if status:
                status('正在转换 MOBI→TXT…')
            convert_mobi_to_txt(_Path(mobi_path), _Path(txt_path))

        self._run_worker(
            target=_do,
            success_msg='MOBI→TXT 转换完成',
            dir_to_open=os.path.dirname(txt_path),
        )

    def _on_reset_tab3(self):
        """重置 tab3 的所有输入。"""
        self._le_mobi.clear()
        self._le_mobi_txt.clear()
        self.statusBar().showMessage('已重置')
        logger.info('tab3 重置')

    # ================================================================
    # 快捷键处理
    # ================================================================

    def _on_shortcut_convert(self):
        """Ctrl+Enter: 执行当前 tab 的转换。"""
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._on_convert_tab1()
        elif idx == 1:
            self._on_convert_tab2()
        else:
            self._on_convert_mobi_to_txt()

    def _on_shortcut_open(self):
        """Ctrl+O: 打开文件（根据当前 tab 选择文件类型）。"""
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._on_browse_txt()
        elif idx == 1:
            self._on_browse_in_epub()
        else:
            self._on_browse_mobi()

    def _on_shortcut_reset(self):
        """Ctrl+R: 重置当前 tab。"""
        idx = self._tabs.currentIndex()
        if idx == 0:
            self._on_reset_tab1()
        elif idx == 1:
            self._on_reset_tab2()
        else:
            self._on_reset_tab3()

    def _on_about(self):
        """F1: 显示关于对话框。"""
        dlg = AboutDialog(self)
        dlg.exec()

    # ================================================================
    # 后台线程管理
    # ================================================================

    def _run_worker(self, target, success_msg: str, dir_to_open: str):
        """
        启动后台线程执行耗时转换。

        这是连接 UI 和 Worker 的关键方法：
        1. 创建 ProgressWorker，传入业务函数
        2. 连接进度/状态/完成信号到 UI 更新
        3. 禁用窗口防止重复操作
        4. 启动线程

        Args:
            target: 业务函数，签名 target(progress, status)
            success_msg: 成功后的状态栏消息
            dir_to_open: 成功后询问是否打开的目录
        """

        # ---- 信号处理闭包 ----

        def _progress(cur, tot):
            """更新进度条。"""
            if tot > 0:
                self._progress_bar.setRange(0, tot)
                self._progress_bar.setValue(cur)
            self._progress_bar.setVisible(True)

        def _status(msg):
            """更新状态栏文本。"""
            self.statusBar().showMessage(msg)

        def _done(ok, err):
            """转换完成（成功或失败）。"""
            self._progress_bar.setVisible(False)
            self.setEnabled(True)
            self._worker = None

            if ok:
                logger.info(success_msg)
                self.statusBar().showMessage(success_msg)
                self._ask_open_dir(dir_to_open)
            else:
                QMessageBox.critical(self, '错误', f'转换失败:\n{err}')
                self.statusBar().showMessage('转换失败')

        # ---- 启动线程 ----
        self._worker = ProgressWorker(target)
        self._worker.progress.connect(_progress)
        self._worker.status.connect(_status)
        self._worker.finished.connect(_done)
        self.setEnabled(False)  # 禁用窗口，防止用户重复点击
        self._worker.start()

    # ================================================================
    # 辅助
    # ================================================================

    def _ask_open_dir(self, dirname: str):
        """
        转换完成后弹窗询问是否打开输出目录。

        只对存在的目录弹窗。
        """
        if not dirname or not os.path.isdir(dirname):
            return
        reply = QMessageBox(
            QMessageBox.Icon.Information,
            '信息',
            '转换完成，是否打开存储目录？',
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.No,
        ).exec()
        if reply == QMessageBox.StandardButton.Ok:
            self._open_dir(dirname)

    @staticmethod
    def _open_dir(dirname: str):
        """
        跨平台打开文件管理器。

        Windows 用 os.startfile，Linux 用 xdg-open。
        macOS 也可以用 open 命令，但当前没有处理。
        """
        if not dirname:
            return
        logger.info(f'打开目录: {dirname}')
        if sys.platform == 'win32':
            os.startfile(dirname)
        elif sys.platform == 'linux':
            os.system(f'xdg-open "{dirname}"')

    def _save_config(self):
        """
        保存当前设置到 config.json。

        包括两个 Tab 的编码、分隔符、正则和繁简转换设置。
        下次启动时通过 _restore_config 恢复。
        """
        self._config = AppConfig(
            txt_encoding=self._cb_encode.currentText(),
            out_encoding=self._cb_out_code.currentText(),
            chapter_sep=self._cb_sep.currentText(),
            chapter_regex=self._te_reg.toPlainText().strip(),
            fanjian_enabled=self._chb_fanjian.isChecked(),
        )
        self._config.save(_CONFIG_PATH)

    def _restore_config(self):
        """
        从 config.json 恢复上次的设置。

        findText 匹配下拉框中的文本，匹配不上就保持默认。
        """
        cfg = self._config
        # 编码
        idx = self._cb_encode.findText(cfg.txt_encoding)
        if idx >= 0:
            self._cb_encode.setCurrentIndex(idx)
        idx = self._cb_out_code.findText(cfg.out_encoding)
        if idx >= 0:
            self._cb_out_code.setCurrentIndex(idx)
        # 分隔符
        idx = self._cb_sep.findText(cfg.chapter_sep)
        if idx >= 0:
            self._cb_sep.setCurrentIndex(idx)
        # 正则
        if cfg.chapter_regex:
            self._te_reg.setPlainText(cfg.chapter_regex)
        # 繁简
        self._chb_fanjian.setChecked(cfg.fanjian_enabled)

    def closeEvent(self, event):
        """窗口关闭时自动保存配置。"""
        self._save_config()
        super().closeEvent(event)
