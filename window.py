# -*- coding: utf-8 -*-
"""
TxtPress — 电子书格式转换工具。主窗口，Tab 布局，绑定所有用户交互。

这个文件是程序的"骨架"——负责所有 UI 控件的创建、布局和事件绑定。
代码量最大，但逻辑清晰：分为 3 个 Tab，每个 Tab 有"设置"和"操作"两部分。

架构设计：
  MainWindow (QMainWindow)
    ├── QTabWidget
    │   ├── Tab 0: TXT → EPUB  (生成电子书)
    │   ├── Tab 1: EPUB → TXT  (提取文本)
    │   └── Tab 2: MOBI → TXT  (额外的格式支持)
    └── 状态栏（QStatusBar）
        ├── 进度条（QProgressBar，默认隐藏）
        └── 取消按钮（默认隐藏）

交互模式：
  1. 用户填写/选择文件 → 点击转换 → 创建业务对象（Txt2Epub 等）
  2. 通过 _run_worker 在后台线程执行耗时操作
  3. 转换过程中通过信号实时更新进度条和状态栏
  4. 完成后弹窗询问是否打开输出目录

文件结构：
  1. 辅助控件（_ClickableLabel, _DropLineEdit）
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
import subprocess
import datetime

from loguru import logger
import chardet

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QGroupBox, QLabel, QLineEdit, QComboBox,
    QPushButton, QPlainTextEdit, QCheckBox, QProgressBar,
    QFileDialog, QMessageBox,
)
from PyQt6.QtGui import QIcon, QPixmap, QImage
from pathlib import Path
from opencc import OpenCC

from models import AppConfig, BookInfo
from services import Txt2Epub, Epub2Txt, Epub2Mobi, convert_mobi_to_txt, DEFAULT_CHAPTER_REGEX, _DEFAULT_DESC
from worker import ProgressWorker
from dialogs import ChapterDialog, AboutDialog


# ---- 资源路径 ----
# _BASE_DIR: 当前文件所在目录，用于定位资源文件和 config.json
# 注意：__file__ 在打包成 exe 后可能是相对路径或临时路径，
# os.path.abspath(__file__) 确保拿到的是规范的绝对路径。
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RES_DIR = os.path.join(_BASE_DIR, 'resources', 'images')
_CONFIG_PATH = os.path.join(_BASE_DIR, 'config.json')
_ENCODE_DETECT_SIZE = 4096  # 编码检测时读取的文件前 4096 字节
_MIN_REGEX_LEN = 5          # 自定义正则的最少字符数（太短可能是误输入）


# ---- 辅助控件：可点击标签 ----
# QLabel 默认没有 clicked 信号，这个子类加了一个。
# 在 tab1 和 tab2 中，点击封面图片可以更换封面。
# 为什么不直接用 QPushButton？因为 QPushButton 不能显示图片缩放效果，
# 而 QLabel 设置 setScaledContents(True) 可以自动缩放图片到合适大小。

class _ClickableLabel(QLabel):
    """支持 clicked 信号的 QLabel。

    用法：
        label = _ClickableLabel()
        label.clicked.connect(do_something)

    原理：
    重写 mousePressEvent（鼠标按下事件），
    在事件处理器中发射自定义的 clicked 信号。
    """
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        """重写鼠标点击事件，发射 clicked 信号。

        注意：使用 mousePressEvent（按下时触发）而不是 mouseReleaseEvent（释放时触发），
        因为前者响应更快，用户体验更好。
        """
        self.clicked.emit()


class _DropLineEdit(QLineEdit):
    """支持拖放文件的 QLineEdit，通过构造参数指定接受的扩展名。

    用法：
        le = _DropLineEdit('.txt')  # 只接受 .txt 文件

    拖放检测流程：
    dragEnterEvent: 检查拖入内容是否包含文件 URL，且是否符合扩展名要求
    dropEvent:      如果通过检查，把文件路径填入文本框
    """
    def __init__(self, ext: str, parent=None):
        super().__init__(parent)
        self._ext = ext
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        """拖入事件：检查文件扩展名是否符合要求。"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(self._ext):
                event.acceptProposedAction()

    def dropEvent(self, event):
        """放下事件：将文件路径填入文本框。"""
        urls = event.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


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

    QMainWindow 自带了：
    - setCentralWidget()  中央控件（我们放 QTabWidget）
    - statusBar()         状态栏（我们放进度条和取消按钮）
    - closeEvent()        窗口关闭事件（我们保存配置）

    设计决策：
    - 状态变量（_txt_cover, _epub_cover_path 等）在 __init__ 中集中声明，
      方便维护者快速了解窗口有哪些跨方法共享的状态。
    - UI 构建拆分为 _setup_tab1/2/3 方法，每个方法不超过 80 行。
    - 槽函数命名 _on_xxx，一目了然是事件处理器。
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
        # QMainWindow 的布局是固定的：中央区域 + 菜单栏 + 状态栏
        # 我们创建一个 QWidget 作为中央控件，在里面放 QTabWidget
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
        # 状态栏右下角固定显示进度条和取消按钮（默认隐藏，转换时显示）
        # addPermanentWidget 将控件放在状态栏右侧（不会被临时消息顶走）
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setFixedHeight(14)
        self.statusBar().addPermanentWidget(self._progress_bar)
        self._cancel_btn = QPushButton('取消')
        self._cancel_btn.setObjectName('btn_reset')
        self._cancel_btn.setVisible(False)
        self._cancel_btn.setFixedWidth(50)
        self._cancel_btn.setFixedHeight(22)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self.statusBar().addPermanentWidget(self._cancel_btn)
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

        布局思路：
        - 每个区域用一个 QGroupBox 包裹（带标题边框的分组框）
        - 组内用 QVBoxLayout 垂直排列，行内用 QHBoxLayout 水平排列
        - setSpacing / setContentsMargins 控制间距，让界面不拥挤
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

        self._le_txt = _DropLineEdit('.txt')
        self._le_txt.setPlaceholderText('选择 TXT 源文件…')
        h = self._create_file_row('TXT 文件:', self._le_txt,
                                  self._on_browse_txt)
        gl.addLayout(h)

        self._le_epub = QLineEdit()
        self._le_epub.setPlaceholderText('自动生成或手动选择…')
        h = self._create_file_row('EPUB 保存:', self._le_epub,
                                  self._on_browse_epub)
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
        # 注意：tab1 和 tab2 各有一个封面标签，但 objectName 都叫 'cover_label'，
        # 这样 QSS 样式可以同时作用于两个封面标签。
        h = QHBoxLayout()
        self._cover_label = _ClickableLabel()
        self._cover_label.setObjectName('cover_label')
        self._cover_label.setFixedSize(100, 140)  # 封面比例约 5:7，接近真实书封面
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
        # 用 QPlainTextEdit（多行输入）而不是 QLineEdit 来放正则，
        # 因为复杂的正则需要换行查看和编辑。
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
        self._te_reg.setPlainText(
            self._config.chapter_regex or DEFAULT_CHAPTER_REGEX)
        h.addWidget(self._te_reg)
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 操作 ----
        # 底部按钮区域：辅助功能在左，主要操作在右
        # 用 addStretch() 把按钮推到两边
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

    # ================================================================
    # Tab 2: EPUB → TXT
    # ================================================================

    def _setup_tab2(self):
        """
        构建 Tab 2 的 UI 控件。

        相比 Tab 1，增加了"繁简转换"选项和多种输出模式。
        布局结构与 Tab 1 类似：源文件 → 书籍信息 → 选项 → 操作。

        两个 Tab 的"书籍信息"区域的 UI 几乎相同但数据不共享：
        - tab1 的书籍信息用于创建新的 EPUB
        - tab2 的书籍信息从已有 EPUB 读取，并可写回
        之所以不共用，是为了避免用户在一个 tab 输入的数据污染另一个 tab。
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(2, 4, 2, 4)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        self._le_in_epub = _DropLineEdit('.epub')
        self._le_in_epub.setPlaceholderText('选择 EPUB 源文件…')
        h = self._create_file_row('EPUB 文件:', self._le_in_epub,
                                  self._on_browse_in_epub)
        gl.addLayout(h)

        self._le_out_txt = QLineEdit()
        self._le_out_txt.setPlaceholderText('自动生成或手动选择…')
        h = self._create_file_row('TXT 保存:', self._le_out_txt,
                                  self._on_browse_out_txt)
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

        # 封面 + 操作按钮区域
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
        # 这里用双反斜杠是因为在 Python 字符串中 \\n 就是 "\n"（两个字符）
        # Qt 会在 ComboBox 中显示 "\n"，触发编码时替换为 \n（一个换行符）
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
        没有复杂的设置项，因为 MOBI→TXT 不需要什么配置。
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)
        layout.setContentsMargins(2, 4, 2, 4)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(8)

        self._le_mobi = QLineEdit()
        self._le_mobi.setPlaceholderText('选择 MOBI 源文件…')
        h = self._create_file_row('MOBI 文件:', self._le_mobi,
                                  self._on_browse_mobi)
        gl.addLayout(h)

        self._le_mobi_txt = QLineEdit()
        self._le_mobi_txt.setPlaceholderText('自动生成或手动选择…')
        h = self._create_file_row('TXT 保存:', self._le_mobi_txt,
                                  self._on_browse_mobi_txt)
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
        在大多数键盘上它们对应同一个按键，但在某些布局下可能不同。

        QKeySequence 支持多种格式：
        - 'Ctrl+Return'    字符串格式
        - QKeySequence('...')  同上
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

        拖放流程：
        1. 用户拖动文件到窗口上 → dragEnterEvent 检查是否符合条件
        2. 符合条件 → acceptProposedAction() 显示拖放提示图标
        3. 用户松手（放下）→ dropEvent 处理
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

        自动填充逻辑：
        - EPUB 输出路径 = TXT 同目录 + 同名 .epub
        - 书名和作者 = 文件名（不含扩展名）
        - 描述 = _DEFAULT_DESC（默认描述文字）

        编码检测：
        用 chardet 库读取文件前 4096 字节判断编码。
        检测结果仅供参考，用户可以在"高级选项"中手动选择合适的编码。
        """
        self._le_txt.setText(path)
        self._txt_dir, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)

        # 自动填充：书名/作者用文件名，EPUB 输出路径与 TXT 同目录
        self._le_epub.setText(os.path.join(self._txt_dir, base + '.epub'))
        self._le_title.setText(base.strip())
        self._le_author.setText(base.strip())
        self._le_txt_desc.setText(_DEFAULT_DESC)

        # 编码检测——读取文件前 4096 字节自动判断编码
        # chardet.detect 返回 {"encoding": "utf-8", "confidence": 0.99, ...}
        with open(path, 'rb') as f:
            data = f.read(_ENCODE_DETECT_SIZE)
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

    def _pick_image(self, title='选择封面') -> str:
        """打开图片选择对话框，返回选中路径或空字符串。

        在 tab1 和 tab2 中被 _on_choose_cover 和 _on_choose_cover2 调用。
        提取为独立方法避免重复代码。
        """
        path, _ = QFileDialog.getOpenFileName(
            self, title, '.', 'Images (*.jpg *.png *.jpeg);;All Files(*)')
        return path or ''

    def _on_choose_cover(self):
        """选择封面图片（tab1）。"""
        path = self._pick_image()
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

        异常处理：
        - 如果文件不存在 → 警告提示
        - 如果解析出错 → 弹出错误对话框 + 日志记录
        这样可以避免用户因为乱选文件导致程序崩溃。
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
            if len(reg) >= _MIN_REGEX_LEN:
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
        self._te_reg.setPlainText(DEFAULT_CHAPTER_REGEX)
        self._ordered_chapters = None
        self.statusBar().showMessage('已重置')
        logger.info('tab1 重置')

    def _on_convert_tab1(self):
        """
        开始 TXT→EPUB 转换。

        1. 校验输入（文件存在、输出路径已填）
        2. 创建 Txt2Epub 实例，设置用户填写的属性
        3. 通过 _run_worker 在后台线程执行

        注意：只有用户填写了值的字段才会传给转换器，
        空字段使用 Txt2Epub 的默认值。这样可以保持默认行为一致性。
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
        if len(reg) >= _MIN_REGEX_LEN:
            conv.regex = reg
        # 如果有自定义章节顺序，传给转换器
        conv.set_chapter_order(self._ordered_chapters)

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

        用 NotImplementedError 而不是静默失败，让用户知道这是待实现功能。
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

        提取流程：
        1. 创建 Epub2Txt 实例（会同时读取 EPUB 到内存）
        2. 用 get_info() 提取 DC 元数据
        3. 用 get_cover() 提取封面图片
        4. 填充到对应的 QLineEdit 和 _cover_label2

        注意：
        - 日期从 ISO 格式转为友好的显示格式（yyyy-mm-dd HH:MM:SS）
        - 如果转换失败（错误的 EPUB 文件），弹出警告而不是崩溃
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
        path = self._pick_image('选择封面')
        if path:
            self._epub_cover_path = path
            self._cover_label2.setPixmap(QPixmap(path))

    def _on_save_metadata(self):
        """
        保存元信息到 EPUB。

        把用户在 tab2 书籍信息区填写的内容写回 EPUB 文件。
        包括：标题、作者、贡献者、日期、描述、封面。

        流程：
        1. 验证 EPUB 文件存在
        2. 创建 BookInfo 填入当前 UI 数据
        3. 如果有新封面图片，读取其二进制数据
        4. 调用 Epub2Txt.modi() 写回文件
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

    def _run_epub_to_txt(self, chapter_mode: bool):
        """EPUB→TXT 转换（合并/按章节通用入口）。

        因为合并转换和按章节导出的输入校验和参数设置几乎一样，
        提取为公共方法，减少重复代码。

        Args:
            chapter_mode: True=按章节导出, False=合并转换
        """
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

        target = reader.convert_chapter if chapter_mode else reader.convert
        msg = '按章节导出完成' if chapter_mode else 'EPUB→TXT 转换完成'
        self._run_worker(
            target=lambda progress, status: target(
                fanjian=fanjian, progress=progress, status=status),
            success_msg=msg,
            dir_to_open=os.path.dirname(txt_path),
        )

    def _on_convert_tab2(self):
        """EPUB→TXT 合并转换。"""
        self._run_epub_to_txt(False)

    def _on_convert_chapter(self):
        """EPUB→TXT 按章节导出。"""
        self._run_epub_to_txt(True)

    def _on_extract_images(self):
        """
        提取 EPUB 内嵌图片。

        将 EPUB 中的所有图片提取到输出目录的 images/ 子目录下。
        完成后询问用户是否打开目录。

        用户体验：
        - 提取成功 → 弹窗显示数量，询问是否打开目录
        - 没有图片 → 消息提示"未找到图片"
        - 提取出错 → 弹窗显示错误信息
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

        为什么在这里同时改文件名？
        用户勾选繁简转换，说明文件是繁体的，
        那么输出的 TXT 文件名也应该用简体，保持一致性。

        注意：Qt.CheckState.Checked.value 等于 2（即 Qt.Checked 的值），
        stateChanged 信号传入的是 int 而不是 Qt.CheckState 枚举。
        """
        epub_path = self._le_in_epub.text().strip()
        if not epub_path:
            return
        d, fname = os.path.split(epub_path)
        base, ext = os.path.splitext(fname)
        if state == Qt.CheckState.Checked.value:
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

        def _do(progress, status):
            """后台执行 MOBI 转换的入口函数。"""
            if status:
                status('正在转换 MOBI→TXT…')
            convert_mobi_to_txt(Path(mobi_path), Path(txt_path))

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

    @staticmethod
    def _create_file_row(label: str, line_edit: QLineEdit,
                         browse_callback) -> QHBoxLayout:
        """创建一个带标签 + 输入框 + 浏览按钮的水平行布局。

        在三个 Tab 中被多次复用：
        Tab 1: TXT 文件行、EPUB 保存行
        Tab 2: EPUB 文件行、TXT 保存行
        Tab 3: MOBI 文件行、TXT 保存行

        提取为静态方法避免重复布局代码。
        """
        h = QHBoxLayout()
        h.addWidget(QLabel(label))
        h.addWidget(line_edit)
        btn = QPushButton('浏览')
        btn.setObjectName('btn_browse')
        btn.clicked.connect(browse_callback)
        h.addWidget(btn)
        return h

    # ================================================================
    # 后台线程管理
    # ================================================================

    def _run_worker(self, target, success_msg: str, dir_to_open: str):
        """
        启动后台线程执行耗时转换。

        这是连接 UI 和 Worker 的关键方法：
        1. 创建 ProgressWorker，传入业务函数
        2. 连接进度/状态/完成信号到 UI 更新
        3. 禁用标签页防止重复操作
        4. 启动线程

        信号连接原理：
        - worker.progress.connect(_progress)：子线程 emit 进度 → 主线程更新进度条
        - worker.status.connect(_status)：子线程 emit 状态 → 主线程更新状态栏
        - worker.finished.connect(_done)：子线程结束 → 主线程恢复界面

        PyQt 的信号-槽机制自动处理线程切换：
        从子线程 emit 信号，槽函数在主线程执行（因为槽函数属于主线程的对象）。
        不需要手动加锁或使用 QMetaObject.invokeMethod。

        Args:
            target: 业务函数，签名 target(progress, status)
            success_msg: 成功后的状态栏消息
            dir_to_open: 成功后询问是否打开的目录
        """

        # ---- 信号处理闭包 ----
        # 闭包可以访问 self（外部函数的 __init__ 中定义的控件），
        # 所以在槽函数里可以直接操作 UI。

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
            self._cancel_btn.setVisible(False)
            self._tabs.setEnabled(True)
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
        self._cancel_btn.setVisible(True)
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setText('取消')
        self._tabs.setEnabled(False)  # 禁用标签页，防止用户重复点击
        self._worker.start()

    def _on_cancel_clicked(self):
        """用户点击取消按钮。

        调用 worker.cancel() 只设置一个标记，
        真正的停止发生在下一次 progress 回调时。
        如果业务函数长时间没有调用 progress，取消会有延迟感。
        这是设计上可以接受的——总比强行终止线程导致数据损坏好。
        """
        if self._worker:
            self._worker.cancel()
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText('取消中…')
            self.statusBar().showMessage('正在取消…')

    # ================================================================
    # 辅助
    # ================================================================

    def _ask_open_dir(self, dirname: str):
        """
        转换完成后弹窗询问是否打开输出目录。

        只对存在的目录弹窗。
        使用 QMessageBox 的静态方法拼接风格（Builder 模式），
        可以自由组合图标、按钮、消息文本。
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
        """跨平台打开文件管理器。

        各平台的命令：
        - Windows: os.startfile()（内置，不需要 subprocess）
        - macOS:   open 命令
        - Linux:   xdg-open 命令（大多数桌面环境预装）

        为什么不直接用 Python 的 webbrowser 模块？
        webbrowser.open('file:///path') 在某些系统上会打开浏览器而不是文件管理器。
        """
        if not dirname:
            return
        logger.info(f'打开目录: {dirname}')
        if sys.platform == 'win32':
            os.startfile(dirname)
        elif sys.platform == 'darwin':
            subprocess.run(['open', dirname], check=False)
        else:
            subprocess.run(['xdg-open', dirname], check=False)

    def _save_config(self):
        """
        保存当前设置到 config.json。

        包括两个 Tab 的编码、分隔符、正则和繁简转换设置。
        下次启动时通过 _restore_config 恢复。

        注意：这里保存的是"输出编码"（tab2 的编码 ComboBox），
        而 tab1 的编码存储的是 ComboBox index（因为还有"自动检测"选项）。
        """
        self._config = AppConfig(
            txt_encoding=self._cb_encode.currentIndex(),
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
        这样即使 config.json 被手动编辑成了非法值，也不会崩溃。
        """
        cfg = self._config
        # 编码（txt_encoding 存储的是 ComboBox index）
        # 范围检查避免 config.json 损坏导致 IndexError
        if 0 <= cfg.txt_encoding < self._cb_encode.count():
            self._cb_encode.setCurrentIndex(cfg.txt_encoding)
        idx = self._cb_out_code.findText(cfg.out_encoding)
        if idx >= 0:
            self._cb_out_code.setCurrentIndex(idx)
        # 分隔符
        idx = self._cb_sep.findText(cfg.chapter_sep)
        if idx >= 0:
            self._cb_sep.setCurrentIndex(idx)
        # 正则
        self._te_reg.setPlainText(
            cfg.chapter_regex or DEFAULT_CHAPTER_REGEX)
        # 繁简
        self._chb_fanjian.setChecked(cfg.fanjian_enabled)

    def closeEvent(self, event):
        """窗口关闭时自动保存配置。

        QMainWindow 内置了 closeEvent，重写它可以在窗口关闭前执行清理操作。
        注意一定要调用 super().closeEvent(event)，否则窗口关不掉。
        """
        self._save_config()
        super().closeEvent(event)
