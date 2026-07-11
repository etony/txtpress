# -*- coding: utf-8 -*-
"""
TxtPress — 自定义对话框：章节目录预览 & 关于信息。

两个对话框：
1. ChapterDialog — 展示 TXT 文件的章节列表，支持拖拽排序和双击重命名
2. AboutDialog   — 显示程序版本、技术栈、作者信息

对话框 vs 窗口：
- 对话框（QDialog）是模态的：打开后用户不能操作主窗口，除非关闭对话框
- 主窗口（QMainWindow）是非模态的：用户可以自由切换

这两个对话框都是模态的，因为它们需要用户做出选择（确定/关闭）才能继续。
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
# 每个文件独立计算 _BASE_DIR，确保无论入口在哪里都能正确找到资源。
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RES_DIR = os.path.join(_BASE_DIR, 'resources', 'images')


class ChapterDialog(QDialog):
    """
    章节目录预览弹窗（模态）。

    使用 QListWidget 展示章节列表，支持：
    - 拖拽调整顺序：长按并拖动某一行到新的位置
      （通过 DragDropMode.InternalMove 实现，一行代码搞定）
    - 双击重命名：直接修改章节标题
      （通过 ItemIsEditable flag 实现）

    与 Txt2Epub 的交互：
    1. 主窗口解析 TXT 得到章节列表
    2. 打开此对话框让用户调整
    3. 用户点"确定"后，主窗口通过 get_ordered_chapters() 获取新顺序
    4. 主窗口调用 conv.set_chapter_order() 传入新顺序
    5. 转换时按这个新顺序生成 EPUB 章节

    用户场景：
    假设某 TXT 文件章节顺序是：第一章、第二章、第三章
    但用户想按：第三章、第二章、第一章 的顺序生成 EPUB。
    在对话框里拖拽调整后，转换时会按新顺序排列。
    """

    def __init__(self, chapters: list[str], parent=None):
        """
        Args:
            chapters: 章节标题列表，按原始文件中的顺序排列
            parent:   父窗口，用于居中显示
        """
        super().__init__(parent)
        self.setWindowTitle('章节目录预览')
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
        # QAbstractItemView.DragDropMode.InternalMove 是 Qt 内置的拖拽排序模式
        # 它会自动处理拖拽的视觉反馈（线条指示插入位置）。
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        for ch in chapters:
            item = QListWidgetItem(ch)
            # ItemIsEditable 让用户可以双击编辑标题
            # flags 是 bitmask，用 | 组合多个 flag
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)
        layout.addWidget(self._list)

        # ---- 按钮区域 ----
        # accept() / reject() 是 QDialog 内置的方法：
        #   accept()  → 关闭对话框 + 返回 QDialog.Accepted（值为 1）
        #   reject()  → 关闭对话框 + 返回 QDialog.Rejected（值为 0）
        # 调用者通过 dlg.exec() == QDialog.Accepted 来判断用户点的是哪个按钮。
        h = QHBoxLayout()
        btn = QPushButton('确定')
        btn.setObjectName('btn_action')
        btn.clicked.connect(self.accept)
        h.addWidget(btn)
        btn = QPushButton('关闭')
        btn.clicked.connect(self.reject)
        h.addWidget(btn)
        h.addStretch()
        layout.addLayout(h)

    def get_ordered_chapters(self) -> list[str]:
        """
        获取排序后的章节列表。

        如果用户拖拽调整了顺序，这个列表会反映新的顺序。
        如果用户双击修改了标题，也返回修改后的标题。

        在调用之前确保对话框已关闭且用户点击了"确定"。

        Returns:
            按当前列表顺序排列的章节标题（strip 去除首尾空白）
        """
        return [self._list.item(i).text().strip() for i in range(self._list.count())]


class AboutDialog(QDialog):
    """关于弹窗 — 显示版本、技术栈、作者信息。

    setFixedSize(360, 200) 让对话框不可缩放。
    内容简单固定，不需要用户交互或调整大小。
    """

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
