# AGENTS.md

## 运行

```bash
python main.py      # 标准启动（带控制台）
python main.pyw     # Windows 无控制台启动
```

无构建步骤，纯 Python 脚本项目。Python 3.10+（`ruff` lint 目标版本 py312）。

## 依赖

```bash
pip install -r requirements.txt         # 运行依赖
pip install -r requirements-dev.txt     # 开发依赖（pytest、ruff）
```

## 测试与 Lint

```bash
python -m pytest tests/ -v              # 全部单元测试
python -m pytest tests/test_x.py -k 关键字   # 跑单个测试
python -m ruff check .                  # 静态检查（E4/E7/E9/F，只查不格式化）
```

- **没有 CI/CD，也没有 pre-commit**，提交前在本地跑上面两条命令即可。
- **ruff 只配置了 lint，没有 `ruff format`**（`ruff.toml` 未启用 formatter），不要运行格式化。
- **测试的 import 用项目根目录层级**：`from services import Txt2Epub`、`from models import AppConfig`，而不是 `from txtpress.services import ...`。原因是 `conftest.py` 把项目根目录 `insert(0, ...)` 进 `sys.path`。新写测试时照抄现有 `tests/` 的 import 风格。
- 共享 fixture 在 `conftest.py`：`sample_txt`（序言+两章的 UTF-8 TXT）、`make_epub`（用 ebooklib 生成最小 EPUB，注意其封面必须在 Ncx/Nav 之前注册的注释）。

## 架构

MVC 分层：`window.py`（视图）→ `worker.py`（`QThread` 控制器）→ `services.py`（业务模型）。

- **`services.py` 不 import PyQt**，是核心业务，可独立/命令行复用与测试。改动转换逻辑只碰这里。
- **三个 Tab 页面**（`tab_txt2epub.py` / `tab_epub2txt.py` / `tab_mobi2txt.py`）继承 `tab_base.BaseTab`。`BaseTab.__init__` 通过构造参数注入 `run_worker / is_busy / save_config / show_status / confirm_output_path` 这五个 MainWindow 能力，**Tab 绝不反向 import `window`**（避免循环依赖，且测试可打桩替换这些回调）。
- **`worker.py`** 的 `ProgressWorker` 自动把 `progress` / `status` 回调注入业务函数，异常经 `task_done` 信号回主线程，支持 `cancel()`。
- 配置自动持久化到 `config.json`（见下注意事项）。

## 代码约定

- 每个模块开头 `# -*- coding: utf-8 -*-` 与 `from __future__ import annotations`。
- 4 空格缩进，snake_case 变量 / PascalCase 类名，**注释与文档字符串用中文**。
- `ruff.toml`：`line-length = 100`，`tests/*` 忽略 `E402`。

## 注意事项

- **Windows 为主平台**：`.pyw` 入口、默认字体 Microsoft YaHei、`utils.open_dir()` 走 `os.startfile`。
- **`config.json` 中 `window_geometry` 存为 hex 字符串**（bytes↔hex 序列化，见 `models.AppConfig`）；`AppConfig.load()` 会忽略 JSON 里的多余字段。
- **EPUB → MOBI 是占位框架接口**（`services.Epub2Mobi.convert()` 抛 `NotImplementedError`，需外部 Calibre/KindleGen），MOBI 按钮在 UI 已禁用，不要误以为已实现。
- **`config.json` 与 `docs/` 都被 gitignore**：`config.json` 是运行时生成，`docs/` 放 superpowers 的 plans/specs。提交前 `git status` 确认别把它们带进去。
- 根目录 `cover.jpeg` 是 `resources/images/cover.jpeg` 的重复副本（遗留待清理），引用默认封面请用 `resources/images/cover.jpeg`。

## Workflow

- 每次代码改动完成后自动 `git add -A && git commit`，**提交信息用英文**简述改动（代码注释仍是中文，二者不冲突），然后自动 `git push` 到 GitHub（remote: `etony/txtpress`，分支 `main`）。
