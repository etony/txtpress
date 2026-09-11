# TxtPress — 电子书格式转换工具

基于 PyQt6 的图形界面工具，支持 **TXT ↔ EPUB** 互转、**MOBI → TXT** 转换。

## 功能

| 功能 | 说明 |
|---|---|
| TXT → EPUB | 按正则拆分章节，自动生成封面、目录、CSS 样式 |
| EPUB → TXT | 合并导出为单个 TXT，或按章节导出多个文件 |
| EPUB 元信息编辑 | 读取/修改书名、作者、贡献者、日期、描述、封面 |
| EPUB 图片提取 | 提取 EPUB 中的所有内嵌图片到目录 |
| MOBI → TXT | 基于 mobi 库 + BeautifulSoup 提取文本 |
| 章节排序 | 目录预览对话框中拖拽调整章节顺序 |
| 繁→简转换 | 导出 TXT 时自动转换繁体中文 |
| 拖放支持 | 从文件管理器拖入 .txt / .epub 文件自动加载 |
| 快捷键 | Ctrl+Enter 转换、Ctrl+O 打开、Ctrl+R 重置、F1 关于 |
| 主题切换 | 深色/浅色主题切换，状态栏太阳/月亮图标 |
| 章节正则预设 | 4 种常用正则预设 + 自定义输入 |
| EPUB 样式选择 | 3 种内置样式（default/minimal/modern） |

## 环境要求

- Python 3.10+
- PyQt6
- ebooklib
- beautifulsoup4
- chardet
- opencc-python-reimplemented
- loguru
- mobi

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
cd txtpress/
python main.py      # 标准启动（带控制台）
python main.pyw     # Windows 无控制台启动
```

## 项目结构

```
txtpress/
├── main.py                      # 程序入口
├── main.pyw                     # Windows 无控制台启动
├── window.py                    # 主窗口 UI（~1580 行）
├── services.py                  # 核心转换逻辑
├── models.py                    # 数据模型
├── worker.py                    # 后台线程
├── dialogs.py                   # 自定义对话框
├── constants.py                 # 全局常量（路径、正则预设等）
├── error_handler.py             # 用户友好错误提示映射
├── theme_manager.py             # 深色/浅色主题切换管理
├── requirements.txt             # Python 依赖
├── README.md                    # 本文件
├── config.json                  # 用户偏好配置（自动生成）
├── resources/
│   ├── theme.qss                # 浅色主题 QSS 样式表
│   └── images/
│       ├── cover.jpeg           # 默认封面
│       ├── book2.png            # 章节预览对话框图标
│       └── bookinfo.ico         # 程序图标
└── styles/
    ├── default.css              # 默认 EPUB 样式
    ├── minimal.css              # 简约 EPUB 样式
    └── modern.css               # 现代 EPUB 样式
```

## 各文件功能与用途

### main.py — 程序入口

创建 QApplication，加载 QSS 样式表，设置高 DPI 适配和默认字体（微软雅黑），实例化并显示 MainWindow。设置应用程序图标用于任务栏显示。

### window.py — 主窗口 UI

整个程序的"骨架"。包含三个 Tab 的布局构建、所有控件创建和事件绑定。关键方法：

- `_setup_tab1()` — TXT → EPUB 页面（源文件 → 书籍信息 → 高级选项 → 操作）
- `_setup_tab2()` — EPUB → TXT 页面（合并/按章节导出/提取图片/编辑元信息）
- `_setup_tab3()` — MOBI → TXT 页面
- `_run_worker()` — 启动后台线程，连接进度/状态/完成信号到 UI
- 快捷键、窗口级和行级拖放支持
- `_save_config()` / `_restore_config()` — 配置持久化
- `_toggle_theme()` — 主题切换
- `_create_theme_icon()` — 绘制太阳/月亮图标
- `_on_regex_preset_changed()` — 正则预设变更处理
- `_load_epub_styles()` — 加载 EPUB 样式列表

### services.py — 核心转换逻辑

程序的"大脑"，不依赖 PyQt，可直接被命令行调用。

| 类/函数 | 用途 |
|---|---|
| `Txt2Epub` | TXT → EPUB 转换，含正则章节拆分、封面嵌入、CSS 样式、自定义章节排序 |
| `Epub2Txt` | EPUB → TXT 转换，含合并导出、按章节导出、元信息读取/修改、封面提取、图片提取 |
| `Epub2Mobi` | EPUB → MOBI 框架接口（待外部工具实现） |
| `convert_mobi_to_txt()` | MOBI → TXT 独立函数，基于 mobi 库解压 + BeautifulSoup 解析 HTML |

所有转换方法接受可选 `progress(current, total)` 和 `status(message)` 回调，通过 `worker.py` 实现实时进度报告。

`Txt2Epub` 支持 `load_css_from_file()` 方法加载自定义 EPUB 样式。

### models.py — 数据模型

使用 Python `dataclass` 定义类型安全的数据结构。

| 类 | 用途 |
|---|---|
| `BookInfo` | EPUB 书籍元数据（title / creator / contributor / date / description / cover） |
| `AppConfig` | 用户偏好配置，通过 config.json 序列化（编码、分隔符、正则、繁简开关、主题、正则预设、EPUB 样式） |

`AppConfig.load()` 自动忽略 JSON 中的多余字段，`save()` 以中文友好的格式写入。`window_geometry` 使用 hex 字符串序列化 bytes 类型。

### worker.py — 后台线程

`ProgressWorker(QThread)` 是连接 UI 和业务层的桥梁：

- 三个信号：`progress(int, int)` / `status(str)` / `finished(bool, str)`
- 自动注入 `progress` / `status` 回调到业务函数
- 支持取消操作（通过 `cancel()` 设置标志位）
- 异常自动捕获并通过 `finished` 信号传回主线程

### dialogs.py — 自定义对话框

| 类 | 用途 |
|---|---|
| `ChapterDialog` | 章节目录预览，QListWidget 支持拖拽排序和双击重命名，`get_ordered_chapters()` 返回排序结果 |
| `AboutDialog` | 关于弹窗，显示版本号、技术栈和作者信息 |

### constants.py — 全局常量

集中管理资源路径和默认值常量：

| 常量 | 用途 |
|---|---|
| `BASE_DIR` | 项目根目录 |
| `RES_DIR` | 资源图片目录 |
| `CONFIG_PATH` | 配置文件路径 |
| `STYLES_DIR` | EPUB 样式目录 |
| `REGEX_PRESETS` | 章节正则预设（4 种 + 自定义） |

### error_handler.py — 错误处理

用户友好的错误提示映射，提供 `show_error()`、`show_warning()`、`show_info()` 函数。

### theme_manager.py — 主题管理

`ThemeManager` 类管理深色/浅色主题切换：

- 浅色主题从 `resources/theme.qss` 加载
- 深色主题内嵌在 `theme_manager.py` 中
- `toggle_theme()` 切换主题
- `get_theme_icon()` 返回当前主题对应的图标

### resources/theme.qss — 浅色主题样式表

Material Design Light 风格，覆盖全局颜色、字体、间距、按钮状态和进度条样式。所有控件通过 `objectName` 精准选择。

### styles/ — EPUB 导出样式

| 文件 | 说明 |
|---|---|
| `default.css` | 默认样式，适合一般阅读 |
| `minimal.css` | 简约样式，适合 Kindle 等设备 |
| `modern.css` | 现代样式，适合手机/平板阅读 |

## 设计要点

- **MVC 风格**：window.py（视图） ↔ worker.py（控制器） ↔ services.py（模型）
- **业务层无 UI 依赖**：services.py 不 import PyQt，方便测试和命令行复用
- **Lazy 初始化**：OpenCC（繁简转换）只在首次使用时创建，避免不必要的资源消耗
- **三重封面策略**：通过 ID / 类型 / 文件名三种方式查找 EPUB 封面，兼容不同制作工具
- **实时进度**：progress/status 回调 + QThread 信号，转换时 UI 不卡死
- **主题切换**：QPainter 绘制太阳/月亮图标，深色/浅色主题无缝切换
- **配置持久化**：所有用户设置自动保存到 config.json，下次启动自动恢复
