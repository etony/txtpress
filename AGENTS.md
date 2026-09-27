# AGENTS.md

## 运行

```bash
python main.py      # 标准启动（带控制台）
python main.pyw     # Windows 无控制台启动
```

无构建步骤，纯 Python 脚本项目。

## 依赖安装

```bash
pip install -r requirements.txt
```

## 项目结构

| 文件 | 职责 |
|------|------|
| `window.py` | 主窗口宿主：Tab 挂载、worker 管理、快捷键、拖放、主题、配置持久化 |
| `tab_base.py` | Tab 基类 `BaseTab`（回调注入）+ 共享控件（`_ClickableLabel`/`_DropLineEdit`） |
| `tab_txt2epub.py` | TXT → EPUB 页面（`TabTxt2Epub`，含编码检测、正则预设、章节目录预览） |
| `tab_epub2txt.py` | EPUB → TXT 页面（`TabEpub2Txt`，合并/按章节导出/提取图片/编辑元信息） |
| `tab_mobi2txt.py` | MOBI → TXT 页面（`TabMobi2Txt`） |
| `utils.py` | 通用工具（`open_dir()` 跨平台打开目录） |
| `services.py` | 核心转换逻辑，不依赖 PyQt |
| `worker.py` | QThread 后台线程，连接 UI 与 services |
| `models.py` | `BookInfo`/`ConvertOptions`/`AppConfig` dataclass |
| `dialogs.py` | 章节目录预览 & 关于弹窗 |
| `constants.py` | 全局常量（路径、正则预设等） |
| `error_handler.py` | 用户友好错误提示映射（`show_error()` 等，window/Tab 已接入） |
| `theme_manager.py` | 深色/浅色主题切换管理 |
| `resources/theme.qss` | 浅色主题 QSS 样式表 |
| `styles/*.css` | EPUB 导出样式（default/minimal/modern） |
| `tests/` | pytest 单元测试（11 个测试文件） |
| `conftest.py` | pytest 全局配置与共享 fixture（`sample_txt`/`make_epub`） |
| `ruff.toml` | ruff 静态检查配置（E4/E7/E9/F） |
| `requirements-dev.txt` | 开发依赖（pytest、ruff） |

## 架构要点

- MVC 风格分层：`window.py`(视图) → `worker.py`(控制器) → `services.py`(模型)
- Tab 子类通过 `BaseTab(run_worker, is_busy, save_config, show_status, confirm_output_path)` 注入 MainWindow 能力，不反向 import window
- `services.py` 无 UI 依赖，可独立测试
- 配置通过 `AppConfig.load()`/`save()` 自动持久化到 `config.json`
- 封面图片三重策略：用户指定 → 程序默认 → 无封面
- 主题切换：`theme_manager.py` 管理，浅色从 `resources/theme.qss` 加载，深色内嵌在 `theme_manager.py`

## 代码约定

- `# -*- coding: utf-8 -*-` 编码声明
- `from __future__ import annotations` 前向引用
- 4 空格缩进，snake_case 变量，PascalCase 类名
- 中文注释

## 测试与 Lint

```bash
python -m pytest tests/ -v    # 单元测试
python -m ruff check .        # 静态检查
pip install -r requirements-dev.txt   # 开发依赖
```

无 CI/CD，提交前在本地跑这两项。

## 注意事项

- Windows 平台为主（`.pyw` 入口、Microsoft YaHei 字体）
- EPUB 转 MOBI 功能为框架接口，未完全实现
- `config.json` 中 `window_geometry` 存储为 hex 字符串（bytes→hex 序列化）

## Workflow

- 每次代码改动完成后自动 `git add -A && git commit`，提交信息用英文简述改动内容。

## 重构记录

- `_create_book_info_group()`：统一书籍信息组布局（封面 + 字段 + 按钮）
- `_on_choose_cover_impl()`：封面选择通用实现
- `_reset_cover()` / `_reset_status()`：重置辅助方法
- window.py 拆分：三个 Tab 的 UI 迁至 `tab_txt2epub.py` / `tab_epub2txt.py` / `tab_mobi2txt.py`，公共 UI 与回调注入收进 `tab_base.BaseTab`，`window.py` 只保留 worker 管理、快捷键、拖放、主题、配置持久化
- TXT → EPUB 参数改为 `models.ConvertOptions` + `Txt2Epub.configure(opts)` 批量设置，替代逐字段赋值
