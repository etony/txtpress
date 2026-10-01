# -*- coding: utf-8 -*-
"""Tab 1：TXT → EPUB（生成电子书）。"""
from __future__ import annotations

import os

from loguru import logger
import chardet

from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from services import (
    Txt2Epub, Epub2Mobi, DEFAULT_CHAPTER_REGEX, validate_chapter_regex,
)
from models import ConvertOptions
from dialogs import ChapterDialog
from constants import DEFAULT_DESC, STYLES_DIR, REGEX_PRESETS, FONT_PRESETS, TOC_STYLES
from error_handler import show_error
from tab_base import BaseTab, _ClickableLabel, _DropLineEdit

_ENCODE_DETECT_SIZE = 4096  # 编码检测时读取的文件前 4096 字节
_MIN_REGEX_LEN = 5          # 自定义正则的最少字符数（太短可能是误输入）


class TabTxt2Epub(BaseTab):
    """TXT → EPUB 转换页。

    布局（从上到下）：
      源文件    → TXT 文件路径 + EPUB 保存路径
      书籍信息  → 书名 / 作者 / 贡献者 / 日期 / 描述
      封面      → 封面图片 + 选择按钮
      高级选项  → 文件编码 + 章节正则
      操作      → 开始转换 / →MOBI / 目录预览 / 重置
    """

    def __init__(
        self,
        run_worker,
        is_busy,
        save_config,
        show_status,
        confirm_output_path,
        parent=None,
    ):
        super().__init__(run_worker, is_busy, save_config, show_status,
                         confirm_output_path, parent)

        # ---- 状态变量 ----
        self._txt_cover = ''                       # tab1 封面路径（用户选择的）
        self._txt_dir = ''                         # 当前 TXT 文件所在目录（方便自动填充路径）
        self._ordered_chapters: list[tuple[int, str]] | None = None  # ChapterDialog 调整后的章节 [(原始索引, 新标题)]
        self._ordered_chapters_src: tuple[str, str, str] | None = None  # _ordered_chapters 的来源指纹 (txt路径, 正则, 编码)
        self._detected_encoding = 'utf-8'          # chardet 检测到的输入编码
        self._detected_path: str | None = None     # 检测值对应的文件路径（懒检测缓存键）

        self._setup_tab1()

    # ================================================================
    # UI 构建
    # ================================================================

    def _setup_tab1(self):
        """
        构建 Tab 1 的 UI 控件。

        布局（从上到下）：
          源文件    → TXT 文件路径 + EPUB 保存路径
          书籍信息  → 书名 / 作者 / 贡献者 / 日期 / 描述
          封面      → 封面图片 + 选择按钮
          高级选项  → 文件编码 + 章节正则
          操作      → 开始转换 / →MOBI / 目录预览 / 重置
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(10)

        self._le_txt = _DropLineEdit('.txt')
        self._le_txt.setPlaceholderText('选择 TXT 源文件…')
        self._le_txt.setAccessibleName('TXT 源文件路径')
        h = self._create_file_row('TXT 文件:', self._le_txt,
                                  self._on_browse_txt)
        gl.addLayout(h)

        self._le_epub = QLineEdit()
        self._le_epub.setPlaceholderText('自动生成或手动选择…')
        self._le_epub.setAccessibleName('EPUB 保存路径')
        h = self._create_file_row('EPUB 保存:', self._le_epub,
                                  self._on_browse_epub)
        gl.addLayout(h)
        layout.addWidget(grp)

        # ---- 书籍信息 ----
        self._cover_label = _ClickableLabel()
        self._cover_label.setObjectName('cover_label')
        self._le_title = QLineEdit()
        self._le_title.setAccessibleName('书名')
        self._le_author = QLineEdit()
        self._le_author.setAccessibleName('作者')
        self._le_txt_contrib = QLineEdit()
        self._le_txt_date = QLineEdit()
        self._le_txt_desc = QLineEdit()

        grp = self._create_book_info_group(
            cover_label=self._cover_label,
            cover_clicked=self._on_choose_cover,
            fields=[
                {'label': '书名:', 'widget': self._le_title, 'row': 0, 'col': 0,
                 'placeholder': '默认 = 文件名'},
                {'label': '作者:', 'widget': self._le_author, 'row': 0, 'col': 2,
                 'placeholder': '作者（可选，默认 etony.an@gmail.com）'},
                {'label': '贡献者:', 'widget': self._le_txt_contrib, 'row': 1, 'col': 0,
                 'placeholder': '默认 etony.an@gmail.com'},
                {'label': '日期:', 'widget': self._le_txt_date, 'row': 1, 'col': 2,
                 'placeholder': '默认当前时间 (yyyy-mm-dd)'},
                {'label': '描述:', 'widget': self._le_txt_desc, 'row': 2, 'col': 0,
                 'span': (1, 3), 'placeholder': '素材来源于网络, 版权归原作者. (dc:description，可选)'},
            ],
        )
        layout.addWidget(grp)

        # ---- 高级选项 ----
        # 栅格布局：标签/控件成对、两列并排。相比原来的单行横排，
        # 窄窗口（最小 780px）下下拉框不会被挤压截断，行高也统一。
        grp = QGroupBox('选项')
        grid = QGridLayout(grp)
        grid.setSpacing(10)

        self._cb_encode = QComboBox()
        self._cb_encode.addItems(
            ['自动检测', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'shift-jis'])
        grid.addWidget(QLabel('文件编码:'), 0, 0)
        grid.addWidget(self._cb_encode, 0, 1)
        # 编码检测提示：常驻显示 chardet 检测结果。
        # 原来只写进状态栏（易失消息，点别的按钮就没了），无法回头核对。
        self._enc_detect = QLabel()
        self._enc_detect.setObjectName('enc_detect')
        self._enc_detect.setToolTip('chardet 检测到的文件编码（仅供参考，可手动覆盖）')
        grid.addWidget(self._enc_detect, 0, 2)

        self._cb_epub_style = QComboBox()
        self._load_epub_styles()
        grid.addWidget(QLabel('EPUB样式:'), 0, 3)
        grid.addWidget(self._cb_epub_style, 0, 4)

        self._cb_regex_preset = QComboBox()
        self._cb_regex_preset.addItems(list(REGEX_PRESETS.keys()))
        self._cb_regex_preset.currentTextChanged.connect(self._on_regex_preset_changed)
        grid.addWidget(QLabel('正则预设:'), 1, 0)
        grid.addWidget(self._cb_regex_preset, 1, 1)

        self._te_reg = QLineEdit()
        self._te_reg.setPlaceholderText('自定义章节匹配正则…（留空使用默认正则）')
        # 初始为默认正则；随后 _restore_config 会用 config 值覆写
        self._te_reg.setText(DEFAULT_CHAPTER_REGEX)
        grid.addWidget(QLabel('章节正则:'), 1, 2)
        grid.addWidget(self._te_reg, 1, 3, 1, 2)

        self._cb_font = QComboBox()
        self._cb_font.addItems(list(FONT_PRESETS.keys()))
        grid.addWidget(QLabel('正文字体:'), 2, 0)
        grid.addWidget(self._cb_font, 2, 1)

        self._cb_toc_style = QComboBox()
        self._cb_toc_style.addItems(list(TOC_STYLES.keys()))
        grid.addWidget(QLabel('目录样式:'), 2, 2)
        grid.addWidget(self._cb_toc_style, 2, 3)

        # 控件列比标签列更宽
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)
        layout.addWidget(grp)

        # ---- 操作 ----
        grp = QGroupBox('操作')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        btn = QPushButton('开始转换')
        btn.setObjectName('btn_action')
        btn.setToolTip('将 TXT 转换为 EPUB（Ctrl+Enter）')
        btn.clicked.connect(self._on_convert_tab1)
        gl.addWidget(btn)

        btn = QPushButton('转为 MOBI')
        btn.setObjectName('btn_info')
        btn.setEnabled(False)  # 框架接口，需 Calibre 待实现，置灰避免误点
        btn.setToolTip('将 EPUB 转换为 MOBI（需 Calibre，待实现）')
        btn.clicked.connect(self._on_convert_mobi)
        gl.addWidget(btn)

        gl.addStretch()

        btn = QPushButton('目录预览')
        btn.setToolTip('预览 TXT 文件中的章节列表')
        btn.setObjectName('btn_secondary')
        btn.clicked.connect(self._on_preview_chapters)
        gl.addWidget(btn)

        btn = QPushButton('重置')
        btn.setObjectName('btn_reset')
        btn.setToolTip('清空所有输入 (Ctrl+R)')
        btn.clicked.connect(self._on_reset_tab1)
        gl.addWidget(btn)

        layout.addWidget(grp)
        layout.addStretch()

    # ================================================================
    # BaseTab 钩子
    # ================================================================

    def convert(self) -> None:
        """快捷键入口：开始转换。"""
        self._on_convert_tab1()

    def open_file(self) -> None:
        """快捷键入口：选择 TXT 文件。"""
        self._on_browse_txt()

    def reset(self) -> None:
        """快捷键入口：重置本页。"""
        self._on_reset_tab1()

    def load_file(self, path: str) -> None:
        """外部入口（拖放）：加载 TXT 文件。"""
        self._load_txt_file(path)

    # ================================================================
    # 槽函数
    # ================================================================

    def _on_browse_txt(self):
        """浏览按钮——打开文件选择对话框，选择 TXT 文件。"""
        path, _ = QFileDialog.getOpenFileName(
            self.window(), '选择 TXT 文件', '.', '*.txt;;All Files(*)')
        if path:
            self._load_txt_file(path)

    def _detect_encoding(self, path: str) -> tuple[str, str] | None:
        """读取文件前 _ENCODE_DETECT_SIZE 字节，用 chardet 检测编码。

        返回 (编码, 语言)；文件不存在或读取失败返回 None，
        由调用方决定是否缓存（失败不缓存，避免把错误结果钉死）。
        """
        try:
            with open(path, 'rb') as f:
                data = f.read(_ENCODE_DETECT_SIZE)
        except OSError:
            return None
        # chardet.detect 可能返回 None 或字段缺失，需要安全兜底
        info = chardet.detect(data) or {}
        return info.get('encoding') or 'utf-8', info.get('language') or '未知'

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
        - 描述 = DEFAULT_DESC（默认描述文字）

        编码检测：
        用 chardet 库读取文件前 4096 字节判断编码。
        检测结果仅供参考，用户可以在"高级选项"中手动选择合适的编码。
        """
        if self.is_busy():
            self.show_status('已有转换任务进行中，忽略拖放')
            return
        self._le_txt.setText(path)
        self._txt_dir, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)

        # 自动填充：书名用文件名，EPUB 输出路径与 TXT 同目录；
        # 作者从文件名推不出来，留空走转换器默认值
        self._le_epub.setText(os.path.join(self._txt_dir, base + '.epub'))
        self._le_title.setText(base.strip())
        self._le_txt_desc.setText(DEFAULT_DESC)

        # 编码检测——读取文件前 4096 字节自动判断编码
        # chardet.detect 返回 {"encoding": "utf-8", "confidence": 0.99, ...}
        enc, lang = self._detect_encoding(path) or ('utf-8', '未知')
        self._detected_encoding = enc
        self._detected_path = path
        # 检测结果写进常驻标签（状态栏是易失消息，点别的按钮就没了）
        self._enc_detect.setText(f'检测: {enc}')
        self._enc_detect.setToolTip(f'chardet 检测: {enc}（语言 {lang}）\n仅供参考，可在左侧手动指定编码')
        self.show_status(f'文件: {fname}  编码: {enc}')
        logger.info(f'文件检测: {fname} 编码={enc} 语言={lang}')

        logger.info(f'选择 TXT: {path}')

    def _current_txt_encoding(self) -> str:
        """返回 tab1 当前生效的输入编码。

        "自动检测"（index=0）时返回 chardet 结果，
        否则返回用户手动选择的编码。检测失败回退 utf-8。
        """
        if self._cb_encode.currentIndex() != 0:
            return self._cb_encode.currentText()
        # 手敲/粘贴路径不会经过 _load_txt_file，缓存的检测值可能属于
        # 上一个文件，因此路径变化时懒检测一次并缓存；同路径不重复读盘
        path = self._le_txt.text().strip()
        if path != self._detected_path:
            detected = self._detect_encoding(path)
            if detected is None:
                # 文件不存在/读取失败：不缓存，直接回退 utf-8，
                # 避免沿用上一个文件的检测值
                return 'utf-8'
            self._detected_encoding = detected[0]
            self._detected_path = path
        return self._detected_encoding or 'utf-8'

    def _on_browse_epub(self):
        """浏览——选择 EPUB 保存路径（必须是 .epub 扩展名）。"""
        if not self._le_txt.text():
            self.show_status('请先选择 TXT 文件')
            return
        path, _ = QFileDialog.getSaveFileName(
            self.window(), 'EPUB 保存位置',
            os.path.join(self._txt_dir, 'output'), '*.epub')
        if path:
            self._le_epub.setText(path)

    def _on_choose_cover(self):
        """选择封面图片（tab1）。"""
        self._on_choose_cover_impl('_txt_cover', self._cover_label)

    def _parse_key(self) -> tuple[str, str, str]:
        """当前解析输入的指纹：(txt路径, 生效正则, 生效编码)。

        _ordered_chapters 里的索引绑定某次解析结果，
        换文件/改正则/改编码后旧索引会错配到别的章节，
        因此预览时记录指纹，转换时比对，不一致就丢弃顺序。
        """
        txt = self._le_txt.text().strip()
        reg = self._te_reg.text().strip()
        if len(reg) < _MIN_REGEX_LEN:
            reg = DEFAULT_CHAPTER_REGEX
        # 生效编码：自动检测时用 chardet 结果，手动时用所选编码
        enc = self._current_txt_encoding()
        return (txt, reg, enc)

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
            QMessageBox.warning(self.window(), '提示', '请先选择有效的 TXT 文件')
            return

        try:
            conv = Txt2Epub(txt, self._le_epub.text() or txt + '.epub')
            conv.encoding = self._current_txt_encoding()
            reg = self._te_reg.text().strip()
            if len(reg) >= _MIN_REGEX_LEN:
                conv.regex = reg
            chapters = conv.get_chapters()
            dlg = ChapterDialog(chapters, self.window())
            # exec() 返回 QDialog.Accepted（确定）或 Rejected（关闭）
            if dlg.exec():
                items = dlg.get_ordered_items()
                # get_ordered_items 已 strip，原始标题也要 strip 才能正确判"未改动"
                original = [(i, t.strip()) for i, t in enumerate(chapters)]
                if items != original:
                    self._ordered_chapters = items
                    # 记录来源指纹，转换时校验，输入变化后旧索引作废
                    self._ordered_chapters_src = self._parse_key()
                    self.show_status(
                        f'章节顺序已调整（{len(items)} 章）')
                else:
                    self._ordered_chapters = None
                    self._ordered_chapters_src = None
        except ValueError as e:
            show_error(self.window(), '错误', 'regex_invalid', str(e))
            logger.exception('目录预览失败')
        except Exception as e:
            show_error(self.window(), '错误', 'conversion_failed', str(e))
            logger.exception('目录预览失败')

    def _on_reset_tab1(self):
        """重置 tab1 的所有输入（含选项组下拉，全部回到默认值）。"""
        for w in (self._le_txt, self._le_epub, self._le_title,
                  self._le_author, self._le_txt_contrib,
                  self._le_txt_date, self._le_txt_desc):
            w.clear()
        self._txt_cover = ''
        self._reset_cover(self._cover_label)
        self._cb_encode.setCurrentIndex(0)
        # 选项组补齐：正则预设/EPUB 样式/正文字体/目录样式回到默认项。
        # 预设必须先于 te_reg 重置（预设联动会写入 te_reg），
        # 最后统一把正则设为默认值，保证两者状态一致
        self._cb_regex_preset.setCurrentIndex(0)
        self._cb_epub_style.setCurrentIndex(0)
        self._cb_font.setCurrentIndex(0)
        self._cb_toc_style.setCurrentIndex(0)
        self._detected_encoding = 'utf-8'
        self._detected_path = None
        self._enc_detect.clear()
        self._enc_detect.setToolTip('chardet 检测到的文件编码（仅供参考，可手动覆盖）')
        self._te_reg.setText(DEFAULT_CHAPTER_REGEX)
        self._ordered_chapters = None
        self._ordered_chapters_src = None
        self._txt_dir = ''  # 源文件目录缓存（浏览保存路径的默认目录）
        self._reset_status('tab1')

    def _on_convert_tab1(self):
        """
        开始 TXT→EPUB 转换。

        1. 校验输入（文件存在、输出路径已填）
        2. 创建 Txt2Epub 实例，设置用户填写的属性
        3. 通过 run_worker 在后台线程执行

        注意：只有用户填写了值的字段才会传给转换器，
        空字段使用 Txt2Epub 的默认值。这样可以保持默认行为一致性。
        """
        txt = self._le_txt.text().strip()
        epub = self._le_epub.text().strip()
        if not txt or not os.path.exists(txt):
            QMessageBox.warning(self.window(), '提示', '请选择有效的 TXT 文件')
            return
        if not epub:
            QMessageBox.warning(self.window(), '提示', '请指定 EPUB 保存路径')
            return
        if not self.confirm_output_path(txt, epub):
            return

        # 先校验最终会生效的正则（短于阈值回退默认），
        # 非法正则不写入 config，也避免错误延迟到 worker 里才弹窗
        reg = self._te_reg.text().strip()
        effective_regex = (reg if len(reg) >= _MIN_REGEX_LEN
                           else DEFAULT_CHAPTER_REGEX)
        try:
            validate_chapter_regex(effective_regex)
        except ValueError as e:
            show_error(self.window(), '错误', 'regex_invalid', str(e))
            return

        self.save_config()

        conv = Txt2Epub(txt, epub)
        # 章节顺序与来源指纹绑定：换文件/改正则/改编码后旧索引会错配到
        # 别的章节（索引通常仍合法，补尾救不了），直接丢弃本次顺序
        order = self._ordered_chapters
        if order is not None and self._ordered_chapters_src != self._parse_key():
            order = None
            self.show_status('章节顺序因输入变化已失效，按原序转换')
            logger.info('章节顺序因输入变化已失效，按原序转换')
        # 空字段由 configure 跳过，保持转换器默认值
        conv.configure(ConvertOptions(
            title=self._le_title.text().strip(),
            author=self._le_author.text().strip(),
            description=self._le_txt_desc.text().strip(),
            cover_path=self._txt_cover,
            encoding=self._current_txt_encoding(),
            regex=reg if len(reg) >= _MIN_REGEX_LEN else '',
            chapter_order=order,
        ))
        # ConvertOptions 未覆盖的字段（贡献者/日期）仍直接赋值
        if self._le_txt_contrib.text().strip():
            conv.contributor = self._le_txt_contrib.text().strip()
        if self._le_txt_date.text().strip():
            conv.date = self._le_txt_date.text().strip()

        # 加载EPUB样式
        style_name = self._cb_epub_style.currentText()
        css_path = os.path.join(STYLES_DIR, f'{style_name}.css')
        if os.path.exists(css_path):
            conv.load_css_from_file(css_path)

        # 应用正文字体和目录样式（追加覆盖规则，对所有样式文件都生效）
        conv.apply_text_style(
            FONT_PRESETS.get(self._cb_font.currentText(), ''),
            TOC_STYLES.get(self._cb_toc_style.currentText(), ''),
        )

        self.run_worker(
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
            QMessageBox.warning(self.window(), '提示', '请先生成或指定 EPUB 文件')
            return
        mobi_path = epub_path.rsplit('.', 1)[0] + '.mobi'
        try:
            conv = Epub2Mobi(epub_path, mobi_path)
            conv.convert()
        except NotImplementedError as e:
            QMessageBox.information(self.window(), '提示', str(e))

    def _on_regex_preset_changed(self, preset_name: str):
        """正则预设变更处理"""
        regex = REGEX_PRESETS.get(preset_name, '')
        if regex:
            self._te_reg.setText(regex)
        # 如果是"自定义"，清空让用户输入
        if preset_name == '自定义（用户输入）':
            self._te_reg.clear()

    def _load_epub_styles(self):
        """加载可用的EPUB样式"""
        if os.path.exists(STYLES_DIR):
            for f in sorted(os.listdir(STYLES_DIR)):
                if f.endswith('.css'):
                    self._cb_epub_style.addItem(f.replace('.css', ''))
        if self._cb_epub_style.count() == 0:
            self._cb_epub_style.addItem('default')
