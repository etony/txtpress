# -*- coding: utf-8 -*-
"""Tab 3：MOBI → TXT（额外的格式支持）。"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout,
)

from services import convert_mobi_to_txt
from constants import RES_DIR, COVER_SIZE
from tab_base import BaseTab


class TabMobi2Txt(BaseTab):
    """MOBI → TXT 转换页。

    最简单的 Tab：选择 MOBI 文件 + 输出 TXT 路径 + 转换按钮。
    没有复杂的设置项，因为 MOBI→TXT 不需要什么配置。
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
        self._setup_tab3()

    # ================================================================
    # UI 构建
    # ================================================================

    def _setup_tab3(self):
        """
        构建 Tab 3 的 UI 控件。

        最简单的 Tab：选择 MOBI 文件 + 输出 TXT 路径 + 转换按钮。
        没有复杂的设置项，因为 MOBI→TXT 不需要什么配置。
        """
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(6, 6, 6, 6)

        # ---- 源文件 ----
        grp = QGroupBox('源文件')
        gl = QVBoxLayout(grp)
        gl.setSpacing(10)

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

        # ---- 书籍信息 ----
        grp = QGroupBox('书籍信息')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        # 封面图片
        self._mobi_lbl_cover = QLabel()
        self._mobi_lbl_cover.setObjectName('cover_label')  # 复用 QSS 封面样式（含深色主题）
        self._mobi_lbl_cover.setFixedSize(*COVER_SIZE)
        self._set_mobi_cover(QPixmap(os.path.join(RES_DIR, 'cover.jpeg')))
        self._mobi_lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gl.addWidget(self._mobi_lbl_cover)

        # 信息字段
        info_layout = QGridLayout()
        info_layout.setSpacing(8)

        self._mobi_book_title = QLineEdit()
        self._mobi_book_title.setReadOnly(True)
        info_layout.addWidget(QLabel('标题:'), 0, 0)
        info_layout.addWidget(self._mobi_book_title, 0, 1)

        self._mobi_book_author = QLineEdit()
        self._mobi_book_author.setReadOnly(True)
        info_layout.addWidget(QLabel('作者:'), 0, 2)
        info_layout.addWidget(self._mobi_book_author, 0, 3)

        self._mobi_book_publisher = QLineEdit()
        self._mobi_book_publisher.setReadOnly(True)
        info_layout.addWidget(QLabel('出版商:'), 1, 0)
        info_layout.addWidget(self._mobi_book_publisher, 1, 1)

        self._mobi_book_isbn = QLineEdit()
        self._mobi_book_isbn.setReadOnly(True)
        info_layout.addWidget(QLabel('ISBN:'), 1, 2)
        info_layout.addWidget(self._mobi_book_isbn, 1, 3)

        self._mobi_book_language = QLineEdit()
        self._mobi_book_language.setReadOnly(True)
        info_layout.addWidget(QLabel('语言:'), 2, 0)
        info_layout.addWidget(self._mobi_book_language, 2, 1)

        self._mobi_book_published = QLineEdit()
        self._mobi_book_published.setReadOnly(True)
        info_layout.addWidget(QLabel('出版日期:'), 2, 2)
        info_layout.addWidget(self._mobi_book_published, 2, 3)

        # 刷新按钮
        btn_refresh = QPushButton('刷新信息')
        btn_refresh.setToolTip('重新提取 MOBI 文件的书籍信息')
        btn_refresh.clicked.connect(self._on_refresh_mobi_info)
        info_layout.addWidget(btn_refresh, 3, 0, 1, 4)

        gl.addLayout(info_layout)
        layout.addWidget(grp)

        # ---- 操作 ----
        grp = QGroupBox('操作')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        btn = QPushButton('转换为 TXT')
        btn.setObjectName('btn_action')
        btn.setToolTip('将 MOBI 文件转换为 TXT（Ctrl+Enter）')
        btn.clicked.connect(self._on_convert_mobi_to_txt)
        gl.addWidget(btn)

        gl.addStretch()

        btn = QPushButton('重置')
        btn.setObjectName('btn_reset')
        btn.setToolTip('(Ctrl+R)')
        btn.clicked.connect(self._on_reset_tab3)
        gl.addWidget(btn)
        layout.addWidget(grp)
        layout.addStretch()

    # ================================================================
    # BaseTab 钩子
    # ================================================================

    def convert(self) -> None:
        """快捷键入口：转换为 TXT。"""
        self._on_convert_mobi_to_txt()

    def open_file(self) -> None:
        """快捷键入口：选择 MOBI 文件。"""
        self._on_browse_mobi()

    def reset(self) -> None:
        """快捷键入口：重置本页。"""
        self._on_reset_tab3()

    def load_file(self, path: str) -> None:
        """外部入口（拖放）：加载 MOBI 文件。"""
        self._load_mobi_file(path)

    # ================================================================
    # 槽函数
    # ================================================================

    def _load_mobi_file(self, path: str):
        """加载 MOBI 文件到 Tab 3 界面。

        与 _on_browse_mobi 的逻辑相同，但不弹出文件对话框。
        用于窗口拖放加载 .mobi 文件。
        """
        if self.is_busy():
            self.show_status('已有转换任务进行中，忽略拖放')
            return
        self._le_mobi.setText(path)
        d, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)
        self._le_mobi_txt.setText(os.path.join(d, base + '.txt'))

        # 自动提取书籍信息
        self._load_mobi_metadata(path)

        self.show_status(f'已加载: {fname}')

    def _on_browse_mobi(self):
        """浏览——选择 MOBI 文件，并自动生成 TXT 保存路径。"""
        path, _ = QFileDialog.getOpenFileName(
            self.window(), '选择 MOBI 文件', '.', '*.mobi;;All Files(*)')
        if path:
            self._le_mobi.setText(path)
            d, fname = os.path.split(path)
            base, _ = os.path.splitext(fname)
            self._le_mobi_txt.setText(os.path.join(d, base + '.txt'))

            # 自动提取书籍信息
            self._load_mobi_metadata(path)

    def _load_mobi_metadata(self, mobi_path: str):
        """加载 MOBI 书籍信息（元数据与封面提取在后台线程执行）。"""
        if self.is_busy():
            return
        from services import extract_mobi_metadata, extract_mobi_cover

        box: dict = {}

        def _read(progress, status):
            status('正在读取 MOBI 信息…')
            md = extract_mobi_metadata(Path(mobi_path))
            box['md'] = md
            offset = md.get('cover_offset')
            box['cover'] = (
                extract_mobi_cover(Path(mobi_path), offset)
                if offset is not None else None
            )

        def _fill():
            metadata = box['md']
            self._mobi_book_title.setText(metadata.get('title', ''))
            self._mobi_book_author.setText(metadata.get('creator', ''))
            self._mobi_book_publisher.setText(metadata.get('publisher', ''))
            self._mobi_book_isbn.setText(metadata.get('isbn', ''))
            self._mobi_book_language.setText(metadata.get('language', ''))
            self._mobi_book_published.setText(metadata.get('published', ''))

            cover_data = box['cover']
            if cover_data:
                pixmap = QPixmap()
                if pixmap.loadFromData(cover_data):
                    self._set_mobi_cover(pixmap)
                else:
                    self._mobi_lbl_cover.setText('封面加载失败')
            else:
                self._mobi_lbl_cover.setText('无封面')

        self.run_worker(target=_read, on_success=_fill,
                        fail_msg='读取 MOBI 失败', show_progress=False,
                        error_code='mobi_read_failed')

    def _set_mobi_cover(self, pixmap: QPixmap) -> None:
        """等比例缩放封面到 COVER_SIZE 并显示（避免 setScaledContents 拉伸变形）。"""
        self._mobi_lbl_cover.setPixmap(pixmap.scaled(
            *COVER_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _on_refresh_mobi_info(self):
        """手动刷新 MOBI 文件的书籍信息"""
        mobi_path = self._le_mobi.text().strip()
        if not mobi_path or not os.path.exists(mobi_path):
            QMessageBox.warning(self.window(), '提示', '请先选择有效的 MOBI 文件')
            return
        self._load_mobi_metadata(mobi_path)

    def _on_browse_mobi_txt(self):
        """浏览——选择 TXT 保存路径。"""
        path, _ = QFileDialog.getSaveFileName(
            self.window(), 'TXT 保存位置', '.', '*.txt')
        if path:
            self._le_mobi_txt.setText(path)

    def _on_convert_mobi_to_txt(self):
        """MOBI→TXT 转换——在后台线程中执行。"""
        mobi_path = self._le_mobi.text().strip()
        if not mobi_path or not os.path.exists(mobi_path):
            QMessageBox.warning(self.window(), '提示', '请选择有效的 MOBI 文件')
            return
        txt_path = self._le_mobi_txt.text().strip()
        if not txt_path:
            QMessageBox.warning(self.window(), '提示', '请指定 TXT 保存路径')
            return
        if not self.confirm_output_path(mobi_path, txt_path):
            return

        def _do(progress, status):
            """后台执行 MOBI 转换的入口函数。"""
            convert_mobi_to_txt(
                Path(mobi_path), Path(txt_path),
                progress=progress, status=status
            )

        self.run_worker(
            target=_do,
            success_msg='MOBI→TXT 转换完成',
            dir_to_open=os.path.dirname(txt_path),
        )

    def _on_reset_tab3(self):
        """重置 tab3 的所有输入。"""
        for w in (self._le_mobi, self._le_mobi_txt, self._mobi_book_title,
                  self._mobi_book_author, self._mobi_book_publisher,
                  self._mobi_book_isbn, self._mobi_book_language,
                  self._mobi_book_published):
            w.clear()
        # 恢复默认封面图（等比例缩放，与初始状态一致，setPixmap 会清掉"无封面"等文字）
        self._set_mobi_cover(QPixmap(os.path.join(RES_DIR, 'cover.jpeg')))
        self._reset_status('tab3')
