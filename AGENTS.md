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
| `window.py` | 主窗口 UI（最大文件，~1750 行） |
| `services.py` | 核心转换逻辑，不依赖 PyQt |
| `worker.py` | QThread 后台线程，连接 UI 与 services |
| `models.py` | `BookInfo`/`AppConfig` dataclass |
| `dialogs.py` | 章节目录预览 & 关于弹窗 |
| `constants.py` | 全局常量（路径、正则预设等） |
| `error_handler.py` | 用户友好错误提示映射 |
| `theme_manager.py` | 深色/浅色主题切换管理 |
| `resources/theme.qss` | 浅色主题 QSS 样式表 |
| `styles/*.css` | EPUB 导出样式（default/minimal/modern） |

## 架构要点

- MVC 风格分层：`window.py`(视图) → `worker.py`(控制器) → `services.py`(模型)
- `services.py` 无 UI 依赖，可独立测试
- 配置通过 `AppConfig.load()`/`save()` 自动持久化到 `config.json`
- 封面图片三重策略：用户指定 → 程序默认 → 无封面
- 主题切换：`theme_manager.py` 管理，浅色从 `resources/theme.qss` 加载，深色内嵌在 `theme_manager.py`

## 代码约定

- `# -*- coding: utf-8 -*-` 编码声明
- `from __future__ import annotations` 前向引用
- 4 空格缩进，snake_case 变量，PascalCase 类名
- 中文注释

## 注意事项

- 无测试、无 linting、无 CI/CD 配置
- Windows 平台为主（`.pyw` 入口、Microsoft YaHei 字体）
- EPUB 转 MOBI 功能为框架接口，未完全实现
- `config.json` 中 `window_geometry` 存储为 hex 字符串（bytes→hex 序列化）

## Workflow

- 每次代码改动完成后自动 `git add -A && git commit`，提交信息用英文简述改动内容。

## 重构记录

- `_create_book_info_group()`：统一书籍信息组布局（封面 + 字段 + 按钮）
- `_on_choose_cover_impl()`：封面选择通用实现
- `_reset_cover()` / `_reset_status()`：重置辅助方法
