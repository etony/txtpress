# -*- coding: utf-8 -*-
"""
TxtPress — 电子书格式转换工具。主窗口，Tab 布局，绑定所有用户交互。

这个文件是程序的"骨架"——负责窗口框架、Tab 装配、全局快捷键、
拖放分发、后台线程调度与配置持久化。三个 Tab 的 UI 构建与槽函数
分别在 tab_txt2epub / tab_epub2txt / tab_mobi2txt 模块中。

架构设计：
  MainWindow (QMainWindow)
    ├── QTabWidget
    │   ├── Tab 0: TXT → EPUB  (生成电子书)  → tab_txt2epub.TabTxt2Epub
    │   ├── Tab 1: EPUB → TXT  (提取文本)    → tab_epub2txt.TabEpub2Txt
    │   └── Tab 2: MOBI → TXT  (额外的格式支持) → tab_mobi2txt.TabMobi2Txt
    └── 状态栏（QStatusBar）
        ├── 进度条（QProgressBar，默认隐藏）
        └── 取消按钮（默认隐藏）

交互模式：
  1. 用户在 Tab 中填写/选择文件 → 点击转换
  2. Tab 通过注入的 run_worker 回调 → MainWindow._run_worker 后台执行
  3. 转换过程中通过信号实时更新进度条和状态栏
  4. 完成后弹窗询问是否打开输出目录

文件结构：
  1. MainWindow 主体
     - __init__:      窗口初始化、Tab 装配、进度条、主题
     - 快捷键 & 拖放（分发到当前 Tab 的 convert/open_file/reset/load_file）
     - _run_worker:   后台线程管理
     - _confirm_output_path / _ask_open_dir: 输出确认与目录打开
     - 配置持久化:    _save_config / _restore_config
"""

from __future__ import annotations

import math
import os

from loguru import logger

from PyQt6.QtCore import QSize
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QTabWidget,
    QPushButton, QProgressBar,
    QMessageBox, QApplication,
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QAction,
)

from models import AppConfig
from services import DEFAULT_CHAPTER_REGEX
from worker import ProgressWorker
from dialogs import AboutDialog
from constants import RES_DIR, CONFIG_PATH
from theme_manager import theme_manager, Theme
from error_handler import show_error
from utils import open_dir
from tab_base import _ClickableLabel  # noqa: F401  再导出，保测试引用路径
from tab_txt2epub import TabTxt2Epub
from tab_epub2txt import TabEpub2Txt
from tab_mobi2txt import TabMobi2Txt


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
        # （tab1/2/3 的控件与私有状态已随 UI 构建迁移到各自的 Tab 类）
        self._config = AppConfig.load(CONFIG_PATH) # 从 config.json 加载的配置
        self._worker: ProgressWorker | None = None # 当前正在运行的后台线程
        self._closing = False                      # 是否正在关窗（关窗期间忽略任务回调/新任务）

        # ---- 窗口基础 ----
        self.setWindowTitle('TxtPress — 电子书格式转换工具')
        self.setWindowIcon(QIcon(os.path.join(RES_DIR, 'bookinfo.ico')))
        self.setMinimumSize(860, 500)

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
        # Tab 通过构造参数拿到本窗口的能力（晚绑定 lambda：测试替换
        # 本对象上的方法后，Tab 调用会路由到替换后的方法）
        self._tab_txt2epub = TabTxt2Epub(
            run_worker=lambda *a, **k: self._run_worker(*a, **k),
            is_busy=lambda: self._is_busy(),
            save_config=lambda: self._save_config(),
            show_status=lambda msg: self.statusBar().showMessage(msg),
            confirm_output_path=lambda *a, **k: self._confirm_output_path(*a, **k),
        )
        self._tabs.addTab(self._tab_txt2epub, 'TXT → EPUB')
        self._tab_epub2txt = TabEpub2Txt(
            run_worker=lambda *a, **k: self._run_worker(*a, **k),
            is_busy=lambda: self._is_busy(),
            save_config=lambda: self._save_config(),
            show_status=lambda msg: self.statusBar().showMessage(msg),
            confirm_output_path=lambda *a, **k: self._confirm_output_path(*a, **k),
        )
        self._tabs.addTab(self._tab_epub2txt, 'EPUB → TXT')
        self._tab_mobi2txt = TabMobi2Txt(
            run_worker=lambda *a, **k: self._run_worker(*a, **k),
            is_busy=lambda: self._is_busy(),
            save_config=lambda: self._save_config(),
            show_status=lambda msg: self.statusBar().showMessage(msg),
            confirm_output_path=lambda *a, **k: self._confirm_output_path(*a, **k),
        )
        self._tabs.addTab(self._tab_mobi2txt, 'MOBI → TXT')

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
        
        # ---- 主题切换按钮 ----
        self._theme_manager = theme_manager
        self._theme_manager.set_app(QApplication.instance())
        self._theme_btn = QPushButton()
        self._theme_btn.setFixedSize(28, 28)
        self._theme_btn.setToolTip('切换深色/浅色主题')
        self._theme_btn.setIcon(self._create_theme_icon('light'))
        self._theme_btn.setIconSize(QSize(18, 18))
        self._theme_btn.clicked.connect(self._toggle_theme)
        self.statusBar().addPermanentWidget(self._theme_btn)
        
        self.statusBar().showMessage('就绪')

        # ---- 快捷键 ----
        self._setup_shortcuts()

        # ---- 菜单栏 ----
        self._setup_menu()

        # ---- 加载配置（恢复上次设置）----
        self._restore_config()

        # 如果没有保存的几何尺寸，使用默认大小
        if not self._config.window_geometry:
            self.resize(800, 700)

        logger.info('程序加载完成')

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

    def _setup_menu(self):
        """构建菜单栏：帮助 → 关于（补充 F1 之外的可见入口）。"""
        menu = self.menuBar().addMenu('帮助(&H)')
        act_about = QAction('关于 TxtPress(&A)', self)
        act_about.setShortcut('F1')
        act_about.triggered.connect(self._on_about)
        menu.addAction(act_about)

    # ================================================================
    # Drag & Drop（窗口级 + 行级）
    # ================================================================

    def dragEnterEvent(self, event):
        """
        窗口级拖入事件。

        当用户从文件管理器拖文件到窗口上时触发。
        只接受单个 .txt、.epub 或 .mobi 文件的拖入。

        拖放流程：
        1. 用户拖动文件到窗口上 → dragEnterEvent 检查是否符合条件
        2. 符合条件 → acceptProposedAction() 显示拖放提示图标
        3. 用户松手（放下）→ dropEvent 处理
        """
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1:
                path = urls[0].toLocalFile().lower()
                if path.endswith(('.txt', '.epub', '.mobi')):
                    self.setProperty('dragging', True)
                    self.style().unpolish(self)
                    self.style().polish(self)
                    event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        """拖离事件：恢复窗口外观。"""
        self.setProperty('dragging', False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        """
        窗口级放下事件。

        根据文件类型自动切换到对应 Tab：
        .txt  → 切换到 Tab 1（TXT→EPUB）并加载文件
        .epub → 切换到 Tab 2（EPUB→TXT）并加载文件
        .mobi → 切换到 Tab 3（MOBI→TXT）并加载文件
        """
        self.setProperty('dragging', False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith('.txt'):
                self._tabs.setCurrentIndex(0)
                self._tab_txt2epub.load_file(path)
            elif path.lower().endswith('.epub'):
                self._tabs.setCurrentIndex(1)
                self._tab_epub2txt.load_file(path)
            elif path.lower().endswith('.mobi'):
                self._tabs.setCurrentIndex(2)
                self._tab_mobi2txt.load_file(path)

    # ================================================================
    # 快捷键处理
    # ================================================================

    def _on_shortcut_convert(self):
        """Ctrl+Enter: 执行当前 tab 的转换。"""
        if self._is_busy():
            self.statusBar().showMessage('已有转换任务进行中…')
            return
        self._tabs.currentWidget().convert()

    def _on_shortcut_open(self):
        """Ctrl+O: 打开文件（根据当前 tab 选择文件类型）。"""
        if self._is_busy():
            self.statusBar().showMessage('已有转换任务进行中…')
            return
        self._tabs.currentWidget().open_file()

    def _on_shortcut_reset(self):
        """Ctrl+R: 重置当前 tab。"""
        if self._is_busy():
            self.statusBar().showMessage('已有转换任务进行中…')
            return
        self._tabs.currentWidget().reset()

    def _on_about(self):
        """F1: 显示关于对话框。"""
        dlg = AboutDialog(self)
        dlg.exec()

    def _toggle_theme(self):
        """切换深色/浅色主题"""
        self._theme_manager.toggle_theme()
        theme = 'dark' if self._theme_manager.get_current_theme().value == 'dark' else 'light'
        self._theme_btn.setIcon(self._create_theme_icon(theme))
        self._save_config()

    def _create_theme_icon(self, theme: str) -> QIcon:
        """创建主题切换图标（太阳/月亮）"""
        size = 18
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if theme == 'light':
            # 浅色主题 -> 显示月亮（点击切换到深色）
            painter.setPen(QPen(QColor('#757575'), 1.5))
            painter.setBrush(QBrush(QColor('#757575')))
            painter.drawEllipse(3, 2, 10, 10)
            painter.setPen(QPen(QColor(0, 0, 0, 0)))
            painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
            painter.drawEllipse(6, 1, 10, 10)
        else:
            # 深色主题 -> 显示太阳（点击切换到浅色）
            painter.setPen(QPen(QColor('#FFB300'), 1.5))
            painter.setBrush(QBrush(QColor('#FFB300')))
            painter.drawEllipse(5, 5, 8, 8)
            pen = QPen(QColor('#FFB300'), 1.5)
            painter.setPen(pen)
            cx, cy = size // 2, size // 2
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                x1 = cx + 6 * math.cos(rad)
                y1 = cy + 6 * math.sin(rad)
                x2 = cx + 8 * math.cos(rad)
                y2 = cy + 8 * math.sin(rad)
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.end()
        return QIcon(pixmap)

    # ================================================================
    # 后台线程管理
    # ================================================================

    def _is_busy(self) -> bool:
        """是否有后台任务尚未结束。

        只判断 worker 引用是否还在，不看 isRunning()：
        线程结束到 _done 在主线程执行之间存在间隙，此时 isRunning()
        已为 False 但旧任务的 _done 还没跑，放行新任务会被旧 _done
        clobber（把新 worker 置 None、重开 tabs）。
        引用清空只发生在 _done 里，恰好覆盖整个间隙。
        """
        return self._worker is not None

    def _run_worker(self, target, success_msg: str = '', dir_to_open: str = '',
                    on_success=None, fail_msg: str = '转换失败',
                    error_code: str = 'conversion_failed',
                    show_progress: bool = True):
        """
        启动后台线程执行耗时操作。

        这是连接 UI 和 Worker 的关键方法：
        1. 创建 ProgressWorker，传入业务函数
        2. 连接进度/状态/完成信号到 UI 更新
        3. 禁用标签页防止重复操作
        4. 启动线程

        信号连接原理：
        - worker.progress.connect(_progress)：子线程 emit 进度 → 主线程更新进度条
        - worker.status.connect(_status)：子线程 emit 状态 → 主线程更新状态栏
        - worker.task_done.connect(_done)：子线程结束 → 主线程恢复界面

        PyQt 的信号-槽机制自动处理线程切换：
        从子线程 emit 信号，槽函数在主线程执行（因为槽函数属于主线程的对象）。
        不需要手动加锁或使用 QMetaObject.invokeMethod。

        Args:
            target: 业务函数，签名 target(progress, status)
            success_msg: 成功后的状态栏消息（空则不显示）
            dir_to_open: 成功后询问是否打开的目录（空则不询问）
            on_success: 成功后在主线程执行的回调（用于回填 UI）
            fail_msg: 失败时的提示前缀
            error_code: error_handler.ERROR_MESSAGES 中的错误码
            show_progress: 是否显示进度条与取消按钮（元数据读取为 False）
        """

        # 关窗期间不启动新任务（此时 worker 可能刚被 _done 清空，
        # 单看 _is_busy 会漏判）；单独判断而非并入 _is_busy，
        # 避免把"关窗中"语义混进"忙"语义
        if self._closing:
            logger.warning('窗口关闭中，忽略启动后台任务的请求')
            return

        if self._is_busy():
            self.statusBar().showMessage('已有转换任务进行中，请等待完成或取消')
            logger.warning('忽略重复启动的后台任务')
            return

        # ---- 信号处理闭包 ----
        # 闭包可以访问 self（外部函数的 __init__ 中定义的控件），
        # 所以在槽函数里可以直接操作 UI。

        def _progress(cur, tot):
            """更新进度条。"""
            if tot > 0:
                self._progress_bar.setRange(0, tot)
                self._progress_bar.setValue(cur)
            if show_progress:
                self._progress_bar.setVisible(True)

        def _status(msg):
            """更新状态栏文本。"""
            self.statusBar().showMessage(msg)

        def _done(ok, err, cancelled):
            """任务结束（成功 / 失败 / 取消）。"""
            if self._closing:
                # 关窗流程已接管：worker 由 closeEvent 的 cancel+wait 处理，
                # 此时弹窗/更新控件可能阻塞退出或访问已销毁的控件
                logger.info('窗口关闭中，忽略任务结束回调')
                return

            self._progress_bar.setVisible(False)
            self._cancel_btn.setVisible(False)
            # 复位取消按钮，避免上一次"取消中…"状态带到下个任务
            self._cancel_btn.setText('取消')
            self._cancel_btn.setEnabled(True)
            self._tabs.setEnabled(True)
            self._worker = None

            if cancelled:
                logger.info('任务已取消')
                self.statusBar().showMessage('已取消')
            elif ok:
                if on_success is not None:
                    try:
                        on_success()
                    except Exception as e:
                        # 回填逻辑异常不能让进程闪退，走既有失败弹窗分支
                        logger.exception('任务回填处理失败')
                        QMessageBox.critical(self, '错误', f'{fail_msg}:\n{e}')
                        self.statusBar().showMessage(fail_msg)
                        return
                if success_msg:
                    logger.info(success_msg)
                    self.statusBar().showMessage(success_msg)
                if dir_to_open:
                    self._ask_open_dir(dir_to_open)
            else:
                show_error(self, '错误', error_code, err)
                self.statusBar().showMessage(fail_msg)

        # ---- 启动线程 ----
        self._worker = ProgressWorker(target)
        self._worker.progress.connect(_progress)
        self._worker.status.connect(_status)
        self._worker.task_done.connect(_done)
        if show_progress:
            self._cancel_btn.setVisible(True)
            self._cancel_btn.setEnabled(True)
            self._cancel_btn.setText('取消')
            # 转换任务禁用标签页防止重复操作；
            # 元数据读取等快速任务不禁用（is_busy 已挡住并发）
            self._tabs.setEnabled(False)
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

    def _confirm_output_path(self, in_path: str, out_path: str,
                             chapter_mode: bool = False) -> bool:
        """输出路径保护（计划 Task 17 Step 2）。

        校验规则：
        1. 输出路径不能与输入文件相同（防止就地覆盖源文件）
        2. 输出目录必须已存在（不做隐式创建，避免手误建出目录）
        3. 输出路径本身是已存在的目录 → 拒绝（目录不能当输出文件，
           放进覆盖确认会在 Yes 后由 worker 抛 IsADirectoryError）
        4. 目标文件已存在时弹 Yes/No 覆盖确认

        章节模式（chapter_mode=True）：按章节导出实际写入的是
        {base}1.txt、{base}2.txt…（services.Epub2Txt.convert_chapter），
        从不写 out_path 本身——覆盖确认以第 1 章输出为探测对象，
        文案也点明是章节文件，避免误以为在覆盖 out_path。

        Args:
            in_path: 输入文件路径（调用方已校验存在）
            out_path: 输出文件路径（调用方已校验非空）
            chapter_mode: 是否按章节导出（仅影响覆盖确认的探测对象）

        Returns:
            True=允许继续转换；False=已提示并拒绝
        """
        if (os.path.normcase(os.path.abspath(out_path))
                == os.path.normcase(os.path.abspath(in_path))):
            QMessageBox.warning(self, '提示', '输出路径不能与输入文件相同')
            return False
        out_dir = os.path.dirname(out_path)
        if out_dir and not os.path.isdir(out_dir):
            if os.path.exists(out_dir):
                # 目录位置被同名文件占位，说"不存在"会误导
                QMessageBox.warning(
                    self, '提示',
                    f'输出目录不是有效目录:\n{out_dir}\n请改选已存在的目录')
            else:
                QMessageBox.warning(
                    self, '提示',
                    f'输出目录不存在:\n{out_dir}\n请先创建目录或改选已存在的目录')
            return False
        if os.path.isdir(out_path):
            QMessageBox.warning(
                self, '提示',
                f'输出路径是已存在的目录，请改选文件路径:\n{out_path}')
            return False

        probe = out_path
        label = '目标文件'
        if chapter_mode:
            base, ext = os.path.splitext(os.path.basename(out_path))
            probe = os.path.join(out_dir, f'{base}1{ext}')
            label = '第 1 章输出文件'
        if os.path.exists(probe):
            if QMessageBox.question(
                self, '确认覆盖',
                f'{label}已存在:\n{probe}\n是否覆盖？',
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            ) != QMessageBox.StandardButton.Yes:
                return False
        return True

    def _ask_open_dir(self, dirname: str):
        """
        转换完成后弹窗询问是否打开输出目录。

        只对存在的目录弹窗。
        使用 QMessageBox 的静态方法拼接风格（Builder 模式），
        可以自由组合图标、按钮、消息文本。
        """
        if not dirname or not os.path.isdir(dirname):
            return
        # 确认弹窗用 Yes|No（而非 OK/Cancel）：问题语义是"是否打开"
        reply = QMessageBox(
            QMessageBox.Icon.Information,
            '信息',
            '转换完成，是否打开存储目录？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ).exec()
        if reply == QMessageBox.StandardButton.Yes:
            self._open_dir(dirname)

    @staticmethod
    def _open_dir(dirname: str):
        """跨平台打开文件管理器（实现已迁移到 utils.open_dir）。"""
        return open_dir(dirname)

    def _save_config(self):
        """
        保存当前设置到 config.json。

        包括两个 Tab 的编码、分隔符、正则和繁简转换设置，
        以及窗口的几何尺寸（位置和大小）。
        下次启动时通过 _restore_config 恢复。

        注意：这里保存的是"输出编码"（tab2 的编码 ComboBox），
        tab1 的编码存的是下拉显示文本（语义值，如 '自动检测'/'gbk'），
        避免下拉选项增删后序号错位。
        """
        # 配置逻辑保留在 MainWindow（最小方案）；tab1 控件已迁到
        # TabTxt2Epub，通过实例直接读取（计划 Step 3.6 允许的形态）
        t1 = self._tab_txt2epub
        t2 = self._tab_epub2txt
        self._config = AppConfig(
            txt_encoding=t1._cb_encode.currentText(),
            out_encoding=t2._cb_out_code.currentText(),
            chapter_sep=t2._cb_sep.currentText(),
            chapter_regex=t1._te_reg.text().strip(),
            fanjian_enabled=t2._chb_fanjian.isChecked(),
            window_geometry=bytes(self.saveGeometry()),
            theme=self._theme_manager.get_current_theme().value,
            regex_preset=t1._cb_regex_preset.currentText(),
            epub_style=t1._cb_epub_style.currentText(),
            font_family=t1._cb_font.currentText(),
            toc_style=t1._cb_toc_style.currentText(),
        )
        self._config.save(CONFIG_PATH)

    def _restore_config(self):
        """
        从 config.json 恢复上次的设置。

        findText 匹配下拉框中的文本，匹配不上就保持默认。
        这样即使 config.json 被手动编辑成了非法值，也不会崩溃。
        txt_encoding 兼容旧版本存的 ComboBox 序号（int/数字串），
        按当前下拉项映射成显示文本后再恢复。
        """
        cfg = self._config
        t1 = self._tab_txt2epub
        t2 = self._tab_epub2txt
        # 编码（新格式存语义值/显示文本，旧格式存 ComboBox 序号）
        # 双格式共存期兼容：老版本序号配置不再产生后，本分支可连同
        # findText 回退一起简化
        raw = cfg.txt_encoding
        if (isinstance(raw, int) and not isinstance(raw, bool)) or (
                isinstance(raw, str) and raw.isdigit()):
            # 旧版本存的是 ComboBox 序号，转换成显示文本
            idx = int(raw)
            text = (t1._cb_encode.itemText(idx)
                    if 0 <= idx < t1._cb_encode.count() else '自动检测')
        elif isinstance(raw, str) and raw:
            text = raw
        else:
            text = '自动检测'
        # 非法值 findText 返回 -1，回退到默认第 0 项（自动检测）
        enc_idx = t1._cb_encode.findText(text)
        t1._cb_encode.setCurrentIndex(enc_idx if enc_idx >= 0 else 0)
        out_idx = t2._cb_out_code.findText(cfg.out_encoding)
        t2._cb_out_code.setCurrentIndex(out_idx if out_idx >= 0 else 0)
        # 分隔符
        idx = t2._cb_sep.findText(cfg.chapter_sep)
        if idx >= 0:
            t2._cb_sep.setCurrentIndex(idx)
        # 繁简
        t2._chb_fanjian.setChecked(cfg.fanjian_enabled)
        # 窗口几何尺寸
        if cfg.window_geometry:
            try:
                self.restoreGeometry(cfg.window_geometry)
            except Exception:
                pass  # 几何数据无效时使用默认值
        # 主题
        if hasattr(cfg, 'theme') and cfg.theme:
            theme = Theme.DARK if cfg.theme == 'dark' else Theme.LIGHT
            self._theme_manager.set_theme(theme)
            self._theme_btn.setIcon(self._create_theme_icon(cfg.theme))
        # 正则预设（setCurrentIndex 会经 _on_regex_preset_changed 连带
        # 覆写 _te_reg，所以 chapter_regex 必须在预设之后恢复）
        if hasattr(cfg, 'regex_preset') and cfg.regex_preset:
            idx = t1._cb_regex_preset.findText(cfg.regex_preset)
            if idx >= 0:
                t1._cb_regex_preset.setCurrentIndex(idx)
        # 正则（以配置值收尾）
        t1._te_reg.setText(
            cfg.chapter_regex or DEFAULT_CHAPTER_REGEX)
        # EPUB样式
        if hasattr(cfg, 'epub_style') and cfg.epub_style:
            idx = t1._cb_epub_style.findText(cfg.epub_style)
            if idx >= 0:
                t1._cb_epub_style.setCurrentIndex(idx)
        # 字体
        if hasattr(cfg, 'font_family') and cfg.font_family:
            idx = t1._cb_font.findText(cfg.font_family)
            if idx >= 0:
                t1._cb_font.setCurrentIndex(idx)
        # 目录样式
        if hasattr(cfg, 'toc_style') and cfg.toc_style:
            idx = t1._cb_toc_style.findText(cfg.toc_style)
            if idx >= 0:
                t1._cb_toc_style.setCurrentIndex(idx)

    def closeEvent(self, event):
        """窗口关闭时取消运行中的任务并保存配置。

        QMainWindow 内置了 closeEvent，重写它可以在窗口关闭前执行清理操作。
        注意一定要调用 super().closeEvent(event)，否则窗口关不掉。

        先 cancel 再 wait(3秒)：让 worker 尽快结束，
        避免 "QThread destroyed while running"。
        超时则放行（不阻塞用户退出）。

        先置 _closing：让 _done 早退，防止关窗期间弹窗阻塞退出。
        """
        self._closing = True
        if self._is_busy():
            self._worker.cancel()
            if not self._worker.wait(3000):
                logger.warning('后台任务未能在 3 秒内结束，强制退出')
        self._save_config()
        super().closeEvent(event)
