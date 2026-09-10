import sys, os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)

from window import MainWindow
w = MainWindow()
w.show()
app.processEvents()

# 切换到 Tab2
w._tabs.setCurrentIndex(1)
app.processEvents()

screen = w.grab()
screen.save('screenshot_tab2.png')
print('Tab2 screenshot saved')
w.close()
