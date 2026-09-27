"""
TxtPress — 电子书格式转换工具。

包结构：
  __init__.py       包入口（空，仅标识这是一个包）
  main.py           程序入口，初始化和启动 Qt 应用
  models.py         BookInfo / AppConfig / ConvertOptions 数据模型（dataclass）
  services.py       核心业务：TXT↔EPUB↔MOBI 转换逻辑（无 UI 依赖）
  window.py         PyQt 主窗口宿主：Tab 挂载、worker 管理、快捷键、拖放、主题、配置
  tab_base.py       Tab 基类 BaseTab（回调注入）+ 共享控件
  tab_txt2epub.py   TXT → EPUB 页面
  tab_epub2txt.py   EPUB → TXT 页面
  tab_mobi2txt.py   MOBI → TXT 页面
  utils.py          通用工具（跨平台打开目录）
  dialogs.py        自定义对话框（章节预览排序 / 关于）
  worker.py         后台线程封装（ProgressWorker），避免 UI 卡死
  constants.py      全局常量（路径、正则预设等）
  error_handler.py  用户友好错误提示映射
  theme_manager.py  深色/浅色主题切换管理
  resources/        样式表（theme.qss）和图片资源
  styles/           EPUB 导出样式（default / minimal / modern）
  tests/            pytest 单元测试
"""

