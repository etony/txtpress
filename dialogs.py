# -*- coding: utf-8 -*-
"""
TxtPress — 自定义对话框：章节目录预览 & 关于信息。

两个对话框：
1. ChapterDialog — 展示 TXT 文件的章节列表，支持拖拽排序和双击重命名
2. AboutDialog   — 显示程序版本、作者等基本信息
"""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel,
    QHBoxLayout, QAbstractItemView,
)
from PyQt6.QtGui import QIcon


# 图片资源路径，相对于当前文件的 resources/images/ 目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RES_DIR = os.path.join(_BASE_DIR, 'resources', 'images')


class ChapterDialog(QDialog):
    """
    章节目录预览弹窗（模态）。

    使用 QListWidget 展示章节列表，支持：
    - 拖拽调整顺序：长按并拖动某一行到新的位置
    - 双击重命名：直接修改章节标题

    点击"确定"后，通过 get_ordered_chapters() 获取排序后的列表。
    如果点击"关闭"，对话框关闭且不保存排序结果。
    """

    def __init__(self, chapters: list[str], parent=None):
        """
        Args:
            chapters: 章节标题列表，按原始文件中的顺序排列
            parent:   父窗口，用于居中显示
        """
        super().__init__(parent)
        self.setWindowTitle('章节目录预览')
        # 给对话框设置图标，美观
        self.setWindowIcon(QIcon(os.path.join(_RES_DIR, 'book2.png')))
        self.setMinimumSize(480, 400)
        self.resize(520, 450)

        # ---- 布局结构 ----
        # 标题 → 可拖拽列表 → 按钮行（确定 / 关闭）
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 标题：显示章节总数 + 操作提示
        title = QLabel(f'共 {len(chapters)} 章  （拖拽调整顺序，双击重命名）')
        title.setStyleSheet(
            'font-size: 14px; font-weight: 600; color: #1976D2;'
        )
        layout.addWidget(title)

        # ---- 可排序的章节列表 ----
        # InternalMove 模式：允许在列表内部拖拽移动行，不允许拖入外部文件
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        for ch in chapters:
            item = QListWidgetItem(ch)
            # ItemIsEditable 让用户可以双击编辑标题
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)
        layout.addWidget(self._list)

        # ---- 按钮区域 ----
        h = QHBoxLayout()
        btn = QPushButton('确定')
        btn.setObjectName('btn_action')
        btn.clicked.connect(self.accept)  # accept 关闭对话框并返回 QDialog.Accepted
        h.addWidget(btn)
        btn = QPushButton('关闭')
        btn.clicked.connect(self.reject)  # reject 关闭对话框并返回 QDialog.Rejected
        h.addWidget(btn)
        h.addStretch()
        layout.addLayout(h)

    def get_ordered_chapters(self) -> list[str]:
        """
        获取排序后的章节列表。

        如果用户拖拽调整了顺序，这个列表会反映新的顺序。
        如果用户双击修改了标题，也返回修改后的标题。

        Returns:
            按当前列表顺序排列的章节标题（strip 去除首尾空白）
        """
        return [self._list.item(i).text().strip() for i in range(self._list.count())]


class AboutDialog(QDialog):
    """关于弹窗 — 显示版本、技术栈、作者信息。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('关于 TxtPress')
        self.setWindowIcon(QIcon(os.path.join(_RES_DIR, 'bookinfo.ico')))
        self.setFixedSize(360, 200)  # 固定大小，不让用户拉伸

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 程序名称标题
        title = QLabel('TxtPress')
        title.setStyleSheet(
            'font-size: 16px; font-weight: 600; color: #1976D2;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 版本与技术信息
        info = QLabel(
            '版本 2.0\n'
            '基于 PyQt6 + ebooklib + BeautifulSoup\n'
            '支持 TXT↔EPUB↔MOBI\n'
            '作者: etony.an@gmail.com'
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet('color: #757575; font-size: 12px;')
        layout.addWidget(info)

        # 确定按钮
        btn = QPushButton('确定')
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
