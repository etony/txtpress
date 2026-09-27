# -*- coding: utf-8 -*-
"""Tab 基类与共享控件。

Tab 通过构造参数拿到 MainWindow 的能力（启动后台任务、判断忙碌、
保存配置、状态栏输出、输出路径确认），从而不 import window，
避免循环依赖。
"""
from __future__ import annotations

from collections.abc import Callable

import os

from loguru import logger

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget,
)

from constants import RES_DIR


# =====================================================================
# 辅助控件：可点击标签
# =====================================================================
# QLabel 默认没有 clicked 信号，这个子类加了一个。
# 在 tab1 和 tab2 中，点击封面图片可以更换封面。
# 为什么不直接用 QPushButton？因为 QPushButton 不能显示图片缩放效果，
# 而 QLabel 设置 setScaledContents(True) 可以自动缩放图片到合适大小。

class _ClickableLabel(QWidget):
    """支持 clicked 信号的 QWidget，用 paintEvent 自绘制封面。"""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._pixmap = QPixmap()

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def pixmap(self):
        return self._pixmap

    def paintEvent(self, event):
        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            # 保持宽高比缩放图片，居中显示
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

    def mousePressEvent(self, event):
        self.clicked.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)


# =====================================================================
# 辅助控件：支持拖放的单行输入框
# =====================================================================

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

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖入事件：检查文件扩展名是否符合要求。"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(self._ext):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """放下事件：将文件路径填入文本框。"""
        urls = event.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


# =====================================================================
# Tab 基类
# =====================================================================

class BaseTab(QWidget):
    """三个转换 Tab 的公共基类。

    跨层依赖全部用构造参数注入（run_worker / is_busy / save_config /
    show_status / confirm_output_path），Tab 不 import MainWindow，
    避免循环依赖；注入的是晚绑定 lambda，MainWindow 上的同名方法
    被替换（如测试打桩）后 Tab 调用会路由到替换后的方法。
    """

    def __init__(
        self,
        run_worker: Callable,
        is_busy: Callable[[], bool],
        save_config: Callable,
        show_status: Callable[[str], None],
        confirm_output_path: Callable[..., bool],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.run_worker = run_worker      # MainWindow._run_worker
        self.is_busy = is_busy            # MainWindow._is_busy
        self.save_config = save_config    # MainWindow._save_config
        self.show_status = show_status    # MainWindow.statusBar().showMessage
        self.confirm_output_path = confirm_output_path  # MainWindow._confirm_output_path

    # ---- 子类重写：生命周期/行为钩子 ----

    def get_config(self) -> dict:
        """子类重写：返回本 Tab 需要持久化的配置。"""
        return {}

    def apply_config(self, cfg: dict) -> None:
        """子类重写：从配置恢复 UI 状态。"""
        pass

    def reset(self) -> None:
        """子类重写：重置本 Tab 全部输入控件。"""
        pass

    def convert(self) -> None:
        """子类重写：启动转换（快捷键 Ctrl+Enter 调用）。"""
        pass

    def open_file(self) -> None:
        """子类重写：打开文件对话框。"""
        pass

    def load_file(self, path: str) -> None:
        """子类重写：从外部（拖放/快捷键）加载文件。"""
        pass

    # ---- 共享 UI 辅助（从 window.py 原样迁移） ----

    def _create_book_info_group(
        self,
        cover_label: _ClickableLabel,
        cover_clicked,
        fields: list[dict],
        buttons: list[dict] | None = None,
        btn_label: str = '选择封面',
        btn_tooltip: str = '选择 EPUB 封面图片',
    ) -> QGroupBox:
        """
        创建书籍信息组（封面 + 元数据字段）。

        Args:
            cover_label: 封面图片控件（需预先创建并 setObjectName）
            cover_clicked: 封面点击信号槽
            fields: 字段配置列表，每项 {'label', 'widget', 'row', 'col', 'span', 'placeholder'}
            buttons: 额外按钮列表（Tab2 用），每项 {'text', 'style', 'tooltip', 'handler'}
            btn_label: 默认按钮文本（无 buttons 时使用）
            btn_tooltip: 默认按钮提示（无 buttons 时使用）

        Returns:
            QGroupBox
        """
        grp = QGroupBox('书籍信息')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)

        # 封面图片（左侧）
        cover_label.setFixedSize(120, 168)
        pixmap = QPixmap(os.path.join(RES_DIR, 'cover.jpeg'))
        cover_label.setPixmap(pixmap)
        cover_label.clicked.connect(cover_clicked)
        gl.addWidget(cover_label)

        # 信息字段（右侧）
        info_layout = QGridLayout()
        info_layout.setSpacing(8)

        for f in fields:
            info_layout.addWidget(QLabel(f['label']), f['row'], f['col'])
            w = f['widget']
            if 'placeholder' in f:
                w.setPlaceholderText(f['placeholder'])
            span = f.get('span', (1, 1))
            info_layout.addWidget(w, f['row'], f['col'] + 1, span[0], span[1])

        # 按钮行
        if buttons:
            btn_layout = QHBoxLayout()
            for b in buttons:
                btn = QPushButton(b['text'])
                btn.setObjectName(b.get('style', 'btn_info'))
                btn.setToolTip(b.get('tooltip', ''))
                btn.clicked.connect(b['handler'])
                btn_layout.addWidget(btn)
            btn_layout.addStretch()
            info_layout.addLayout(btn_layout, 3, 0, 1, 4)
        else:
            btn = QPushButton(btn_label)
            btn.setObjectName('btn_info')
            btn.setToolTip(btn_tooltip)
            btn.clicked.connect(cover_clicked)
            info_layout.addWidget(btn, 3, 0, 1, 4)

        gl.addLayout(info_layout)
        return grp

    def _on_choose_cover_impl(self, cover_attr: str, cover_label: QLabel,
                              title: str = '选择封面') -> None:
        """选择封面图片的通用实现。"""
        path = self._pick_image(title)
        if path:
            setattr(self, cover_attr, path)
            cover_label.setPixmap(QPixmap(path))
            logger.info(f'封面: {path}')

    def _reset_cover(self, cover_label: QLabel) -> None:
        """重置封面图片到默认值。"""
        pixmap = QPixmap(os.path.join(RES_DIR, 'cover.jpeg'))
        cover_label.setPixmap(pixmap)

    def _reset_status(self, tab_name: str) -> None:
        """统一的重置后状态更新。"""
        self.show_status('已重置')
        logger.info(f'{tab_name} 重置')

    def _pick_image(self, title='选择封面') -> str:
        """打开图片选择对话框，返回选中路径或空字符串。

        在 tab1 和 tab2 中被 _on_choose_cover 和 _on_choose_cover2 调用。
        提取为独立方法避免重复代码。
        """
        path, _ = QFileDialog.getOpenFileName(
            self.window(), title, '.', 'Images (*.jpg *.png *.jpeg);;All Files(*)')
        return path or ''

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
