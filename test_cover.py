import sys
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt

app = QApplication(sys.argv)

w = QWidget()
layout = QVBoxLayout(w)

label = QLabel()
label.setObjectName('cover_label')
label.setFixedSize(100, 140)
label.setScaledContents(True)
pixmap = QPixmap('resources/images/cover.jpeg')
label.setPixmap(pixmap)
layout.addWidget(label)

w.setStyleSheet('QLabel#cover_label { border: none; background: #F5F5F5; border-radius: 4px; }')

w.setWindowTitle('Test')
w.resize(400, 400)
w.show()
app.processEvents()

print(f'pixmap size: {pixmap.width()}x{pixmap.height()}')
print(f'label size: {label.width()}x{label.height()}')
print(f'label contentsRect: {label.contentsRect().width()}x{label.contentsRect().height()}')
print(f'label geometry: {label.geometry().width()}x{label.geometry().height()}')
print(f'pixmap shown: {label.pixmap().width()}x{label.pixmap().height()}')

w.close()
