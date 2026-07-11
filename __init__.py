"""
TxtPress — 电子书格式转换工具。

包结构：
  __init__.py   包入口（空，仅标识这是一个包）
  main.py       程序入口，初始化和启动 Qt 应用
  models.py     BookInfo / AppConfig 数据模型（类型安全 dataclass）
  services.py   核心业务：TXT↔EPUB↔MOBI 转换逻辑
  window.py     PyQt 主窗口，Tab 布局，所有用户交互
  dialogs.py    自定义对话框（章节预览排序 / 关于）
  worker.py     后台线程封装（ProgressWorker），避免 UI 卡死
  resources/    样式表（theme.qss）和图片资源
"""
