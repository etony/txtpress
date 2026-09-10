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
| `window.py` | 主窗口 UI（最大文件，~1400 行） |
| `services.py` | 核心转换逻辑，不依赖 PyQt |
| `worker.py` | QThread 后台线程，连接 UI 与 services |
| `models.py` | `BookInfo`/`AppConfig` dataclass |
| `dialogs.py` | 章节目录预览 & 关于弹窗 |
| `resources/theme.qss` | Material Design 样式表 |

## 架构要点

- MVC 风格分层：`window.py`(视图) → `worker.py`(控制器) → `services.py`(模型)
- `services.py` 无 UI 依赖，可独立测试
- 配置通过 `AppConfig.load()`/`save()` 自动持久化到 `config.json`
- 封面图片三重策略：用户指定 → 程序默认 → 无封面

## 代码约定

- `# -*- coding: utf-8 -*-` 编码声明
- `from __future__ import annotations` 前向引用
- 4 空格缩进，snake_case 变量，PascalCase 类名
- 中文注释

## 注意事项

- 无测试、无 linting、无 CI/CD 配置
- Windows 平台为主（`.pyw` 入口、Microsoft YaHei 字体）
- EPUB 转 MOBI 功能为框架接口，未完全实现

## Workflow

- 每次代码改动完成后自动 `git add -A && git commit`，提交信息用英文简述改动内容。
