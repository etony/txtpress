# -*- coding: utf-8 -*-
"""Tab 2：EPUB → TXT（提取文本）。"""
from __future__ import annotations

import os
import datetime

from loguru import logger
from opencc import OpenCC

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from services import Epub2Txt
from models import BookInfo
from utils import open_dir
from tab_base import BaseTab, _ClickableLabel, _DropLineEdit


class TabEpub2Txt(BaseTab):
    """EPUB → TXT 转换页。

    相比 Tab 1，增加了"繁简转换"选项和多种输出模式。
    布局结构与 Tab 1 类似：源文件 → 书籍信息 → 封面 → 选项 → 操作。

    两个 Tab 的"书籍信息"区域的 UI 几乎相同但数据不共享：
    - tab1 的书籍信息用于创建新的 EPUB
    - tab2 的书籍信息从已有 EPUB 读取，并可写回
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
        self._epub_cover_path = ''   # tab2 封面路径（用于修改 EPUB 元信息）
        self._epub_dir = ''          # 当前 EPUB 文件所在目录
        self._cc_t2s = None          # 繁→简转换器（lazy初始化）

        self._setup_tab2()

    # ================================================================
    # UI 构建
    # ================================================================

    def _setup_tab2(self):
        """
        构建 Tab 2 的 UI 控件。

        相比 Tab 1，增加了"繁简转换"选项和多种输出模式。
        布局结构与 Tab 1 类似：源文件 → 书籍信息 → 封面 → 选项 → 操作。

        两个 Tab 的"书籍信息"区域的 UI 几乎相同但数据不共享：
        - tab1 的书籍信息用于创建新的 EPUB
        - tab2 的书籍信息从已有 EPUB 读取，并可写回
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(10)

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
        self._cover_label2 = _ClickableLabel()
        self._cover_label2.setObjectName('cover_label')
        self._le_book_title = QLineEdit()
        self._le_book_creator = QLineEdit()
        self._le_book_contrib = QLineEdit()
        self._le_book_date = QLineEdit()
        self._le_book_desc = QLineEdit()

        grp = self._create_book_info_group(
            cover_label=self._cover_label2,
            cover_clicked=self._on_choose_cover2,
            fields=[
                {'label': '书名:', 'widget': self._le_book_title, 'row': 0, 'col': 0},
                {'label': '作者:', 'widget': self._le_book_creator, 'row': 0, 'col': 2},
                {'label': '贡献者:', 'widget': self._le_book_contrib, 'row': 1, 'col': 0},
                {'label': '日期:', 'widget': self._le_book_date, 'row': 1, 'col': 2},
                {'label': '描述:', 'widget': self._le_book_desc, 'row': 2, 'col': 0,
                 'span': (1, 3), 'placeholder': 'EPUB 描述信息 (dc:description)'},
            ],
            buttons=[
                {'text': '更换封面', 'style': 'btn_info', 'tooltip': '选择新封面图片',
                 'handler': self._on_choose_cover2},
                {'text': '保存元信息', 'style': 'btn_secondary',
                 'tooltip': '将当前编辑的元信息写回 EPUB 文件',
                 'handler': self._on_save_metadata},
            ],
        )
        layout.addWidget(grp)

        # ---- 选项 ----
        grp = QGroupBox('选项')
        gl = QVBoxLayout(grp)
        gl.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel('输出编码:'))
        self._cb_out_code = QComboBox()
        self._cb_out_code.addItems(['utf-8', 'gbk', 'gb2312', 'big5'])
        row.addWidget(self._cb_out_code)
        row.addSpacing(12)
        row.addWidget(QLabel('章节分隔:'))
        self._cb_sep = QComboBox()
        self._cb_sep.addItems(['（无）', '\\n', '\\n\\n', '\\n---\\n'])
        row.addWidget(self._cb_sep)
        row.addSpacing(12)
        self._chb_fanjian = QCheckBox('繁→简转换')
        self._chb_fanjian.setToolTip('将繁体中文转换为简体中文（同时将输出文件名转为简体）')
        self._chb_fanjian.stateChanged.connect(self._on_fanjian_toggled)
        row.addWidget(self._chb_fanjian)
        row.addStretch()
        gl.addLayout(row)

        layout.addWidget(grp)

        # ---- 操作 ----
        grp = QGroupBox('操作')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        btn = QPushButton('合并转换')
        btn.setObjectName('btn_action')
        btn.setToolTip('将 EPUB 所有章节合并为一个 TXT 文件')
        btn.clicked.connect(self._on_convert_tab2)
        gl.addWidget(btn)

        btn = QPushButton('按章节导出')
        btn.setToolTip('每章导出为一个独立的 TXT 文件')
        btn.setObjectName('btn_secondary')
        btn.clicked.connect(self._on_convert_chapter)
        gl.addWidget(btn)

        btn = QPushButton('提取图片')
        btn.setToolTip('将 EPUB 中所有图片提取到其同目录 images/ 子目录')
        btn.setObjectName('btn_info')
        btn.clicked.connect(self._on_extract_images)
        gl.addWidget(btn)

        gl.addStretch()

        btn = QPushButton('重置')
        btn.setObjectName('btn_reset')
        btn.setToolTip('(Ctrl+R)')
        btn.clicked.connect(self._on_reset_tab2)
        gl.addWidget(btn)

        layout.addWidget(grp)
        layout.addStretch()

    # ================================================================
    # BaseTab 钩子
    # ================================================================

    def convert(self) -> None:
        """快捷键入口：合并转换。"""
        self._on_convert_tab2()

    def open_file(self) -> None:
        """快捷键入口：选择 EPUB 文件。"""
        self._on_browse_in_epub()

    def reset(self) -> None:
        """快捷键入口：重置本页。"""
        self._on_reset_tab2()

    def load_file(self, path: str) -> None:
        """外部入口（拖放）：加载 EPUB 文件。"""
        self._load_epub_file(path)

    # ================================================================
    # 槽函数
    # ================================================================

    def _on_browse_in_epub(self):
        """浏览——选择 EPUB 文件。"""
        path, _ = QFileDialog.getOpenFileName(
            self.window(), '选择 EPUB 文件', '.', '*.epub;;All Files(*)')
        if path:
            self._load_epub_file(path)

    def _load_epub_file(self, path: str):
        """加载 EPUB 文件到界面（元数据读取在后台线程执行）。

        流程：预采集 UI 值 → worker 读取元数据/封面 →
        on_success 在主线程回填输入框与封面。

        Args:
            path: EPUB 文件路径
        """
        if self.is_busy():
            self.show_status('已有转换任务进行中，忽略拖放')
            return
        self._le_in_epub.setText(path)
        self._epub_dir, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)

        # 自动填充 TXT 输出路径（与 EPUB 同目录同名）
        txt_path = os.path.join(self._epub_dir, base + '.txt')
        self._le_out_txt.setText(txt_path)

        self.show_status(f'正在读取: {fname}…')
        box: dict = {}

        def _read(progress, status):
            status(f'正在读取: {fname}…')
            reader = Epub2Txt(path, txt_path)
            box['info'] = reader.get_info()
            box['cover'] = reader.get_cover()

        def _fill():
            info = box['info']
            self._le_book_title.setText(info.title)
            self._le_book_creator.setText(info.creator)
            self._le_book_contrib.setText(info.contributor)
            if info.date:
                try:
                    # ISO 格式转成更友好的显示格式
                    dt = datetime.datetime.fromisoformat(info.date)
                    self._le_book_date.setText(
                        dt.strftime('%Y-%m-%d %H:%M:%S'))
                except (ValueError, OverflowError) as e:
                    logger.debug(f'日期解析失败: {info.date} -> {e}')
                    self._le_book_date.setText(info.date)
            self._le_book_desc.setText(info.description)
            cover_data = box['cover']
            if cover_data:
                img = QImage.fromData(cover_data)
                self._cover_label2.setPixmap(QPixmap.fromImage(img))
            logger.info(f'EPUB 信息: {info}')
            self.show_status(f'已加载: {fname}')

        self.run_worker(target=_read, on_success=_fill,
                        fail_msg='读取失败', show_progress=False,
                        error_code='epub_read_failed')

    def _on_browse_out_txt(self):
        """浏览——选择 TXT 保存路径。"""
        path, _ = QFileDialog.getSaveFileName(
            self.window(), 'TXT 保存位置',
            os.path.join(self._epub_dir, 'output'), '*.txt')
        if path:
            self._le_out_txt.setText(path)

    def _on_choose_cover2(self):
        """选择封面图片（tab2，用于修改 EPUB 元信息）。"""
        self._on_choose_cover_impl('_epub_cover_path', self._cover_label2)

    def _on_save_metadata(self):
        """
        保存元信息到 EPUB。

        把用户在 tab2 书籍信息区填写的内容写回 EPUB 文件。
        包括：标题、作者、贡献者、日期、描述、封面。

        流程：
        1. 验证 EPUB 文件存在
        2. 主线程创建 BookInfo 填入当前 UI 数据
        3. worker 里读取新封面图片并调用 Epub2Txt.modi() 写回文件
        """
        epub_path = self._le_in_epub.text().strip()
        if not epub_path or not os.path.exists(epub_path):
            QMessageBox.warning(self.window(), '提示', '请先选择 EPUB 文件')
            return

        # 主线程构建数据；文件 IO 放 worker
        info = BookInfo(
            title=self._le_book_title.text(),
            creator=self._le_book_creator.text(),
            contributor=self._le_book_contrib.text(),
            date=self._le_book_date.text(),
            description=self._le_book_desc.text(),
        )
        cover_path = self._epub_cover_path
        out_txt = self._le_out_txt.text() or ''

        def _write(progress, status):
            status('正在写入 EPUB 元信息…')
            if cover_path:
                with open(cover_path, 'rb') as f:
                    info.cover = f.read()
            reader = Epub2Txt(epub_path, out_txt)
            reader.modi(info)

        def _after():
            self.show_status('元信息保存完成')
            logger.info(f'元信息已更新: {epub_path}')

        self.run_worker(target=_write, on_success=_after,
                        fail_msg='保存失败', show_progress=False,
                        error_code='epub_write_failed')

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
            QMessageBox.warning(self.window(), '提示', '请选择有效的 EPUB 文件')
            return
        if not txt_path:
            QMessageBox.warning(self.window(), '提示', '请指定 TXT 保存路径')
            return
        if not self.confirm_output_path(epub_path, txt_path,
                                        chapter_mode=chapter_mode):
            return

        self.save_config()

        # 主线程预采集 UI 值（worker 里不允许读控件）
        encoding = self._cb_out_code.currentText()
        sep = self._cb_sep.currentText()
        sep = sep.replace('\\n', '\n') if sep and sep != '（无）' else ''
        fanjian = self._chb_fanjian.isChecked()

        def _target(progress, status):
            # EPUB 读取放后台线程，大文件不冻结界面
            reader = Epub2Txt(epub_path, txt_path)
            reader.encoding = encoding
            reader.sep = sep
            convert = reader.convert_chapter if chapter_mode else reader.convert
            convert(fanjian=fanjian, progress=progress, status=status)

        msg = '按章节导出完成' if chapter_mode else 'EPUB→TXT 转换完成'
        self.run_worker(
            target=_target,
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
            QMessageBox.warning(self.window(), '提示', '请先选择 EPUB 文件')
            return

        out_dir = os.path.join(os.path.dirname(epub_path), 'images')

        box: dict = {}

        def _extract(progress, status):
            status('正在提取图片…')
            reader = Epub2Txt(epub_path, '')
            box['files'] = reader.extract_images(out_dir)

        def _after():
            files = box['files']
            if files:
                msg = f'成功提取 {len(files)} 张图片到:\n{out_dir}'
                logger.info(msg)
                if QMessageBox.question(
                    self.window(), '提取完成', msg + '\n打开目录？',
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                ) == QMessageBox.StandardButton.Yes:
                    open_dir(out_dir)
            else:
                QMessageBox.information(self.window(), '提取完成', '未找到图片')
                logger.info('提取图片: 未找到图片')

        self.run_worker(target=_extract, on_success=_after,
                        fail_msg='提取失败', show_progress=False,
                        error_code='epub_read_failed')

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
            # lazy初始化OpenCC转换器
            if self._cc_t2s is None:
                self._cc_t2s = OpenCC('t2s')
            new_base = self._cc_t2s.convert(base)
            self._le_out_txt.setText(os.path.join(d, new_base + '.txt'))
        else:
            self._le_out_txt.setText(os.path.join(d, base + '.txt'))

    def _on_reset_tab2(self):
        """重置 tab2 的所有输入（含输出选项下拉与目录缓存）。"""
        for w in (self._le_in_epub, self._le_out_txt, self._le_book_title,
                  self._le_book_creator, self._le_book_contrib,
                  self._le_book_date, self._le_book_desc):
            w.clear()
        self._epub_cover_path = ''
        self._reset_cover(self._cover_label2)
        self._cb_out_code.setCurrentIndex(0)
        self._cb_sep.setCurrentIndex(0)
        self._chb_fanjian.setChecked(False)
        self._epub_dir = ''  # 源文件目录缓存（浏览保存路径的默认目录）
        self._reset_status('tab2')
