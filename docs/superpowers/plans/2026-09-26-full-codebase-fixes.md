# TxtPress 全量修复（P0–P3）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复代码分析报告中 P0–P3 全部 23 项问题：功能缺陷、线程稳定性、死代码清理、配置语义化，并拆分 `window.py`、补 `services.py` 单元测试、接入 `error_handler`、引入 ruff。

**Architecture:** 保持现有 MVC 分层（window → worker → services）。先用 pytest 建立测试安全网，再按 P0（功能）→ P1（稳定性）→ P2（清理）→ P3（结构）顺序修复；每项修复先写失败测试再改实现；每个任务独立提交。

**Tech Stack:** Python 3.12 / PyQt6 / ebooklib / pytest / ruff

**约定:** 4 空格缩进、snake_case、中文注释；每任务结束执行 `git add -A && git commit`，提交信息用英文；不确定时停下来问，不猜。

---

## 任务总览

| # | 阶段 | 任务 |
|---|------|------|
| 1 | 基座 | pytest 测试基座 + Txt2Epub 基础测试 |
| 2 | P0 | 章节分隔符失效修复 |
| 3 | P0 | HTML 转义与段落分段 |
| 4 | P0 | spine 合法性 + 序章入目录 + 进度到 100% |
| 5 | P0 | 章节按索引排序/重命名（不再丢章） |
| 6 | P0 | 章节正则捕获组校验 |
| 7 | P0 | 输出目录创建顺序 + convert_chapter 空目录 |
| 8 | P0 | 字体/目录样式覆盖失效修复 |
| 9 | P0 | "自动检测"编码真正参与转换 |
| 10 | P1 | 转换重入保护 + 关闭窗口取消线程 |
| 11 | P1 | 取消语义区分 + `finished` 信号改名 |
| 12 | P1 | EPUB/MOBI 文件 IO 移出主线程 |
| 13 | P1 | services 防御性修复批（解码/重名/id None/原子写回） |
| 14 | P2 | 接入 error_handler 友好错误提示 |
| 15 | P2 | 死代码清理 + 重复常量合并 |
| 16 | P2 | QSS 选择器修复（封面控件/深色拖放） |
| 17 | P2 | 重置补齐/输出路径保护/Yes-No 按钮 |
| 18 | P2 | 配置存语义编码值（替代 ComboBox 序号） |
| 19 | P3 | 拆分 window.py 为三个 Tab 模块 |
| 20 | P3 | ConvertOptions 参数对象 |
| 21 | P3 | ruff 配置与 lint 清零 |
| 22 | P3 | 文档同步（AGENTS.md / README） |
| 23 | 收尾 | 全量验证 |

---

### Task 1: pytest 测试基座 + Txt2Epub 基础测试

**Files:**
- Create: `conftest.py`（项目根，sys.path + fixture）
- Create: `tests/test_txt2epub.py`
- Create: `requirements-dev.txt`

- [ ] **Step 1: 创建根目录 conftest.py（sys.path + 共享 fixture）**

```python
# -*- coding: utf-8 -*-
"""pytest 全局配置：把项目根目录加入 sys.path，提供共享 fixture。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402


@pytest.fixture
def sample_txt(tmp_path):
    """生成一个含序言 + 两章的 UTF-8 TXT 文件。"""
    p = tmp_path / 'book.txt'
    p.write_text(
        '这是序言文字。\n'
        '第一章 开始\n内容甲。\n'
        '第二章 继续\n内容乙。\n',
        encoding='utf-8',
    )
    return str(p)


@pytest.fixture
def make_epub(tmp_path):
    """用 ebooklib 生成最小 EPUB，返回路径。

    Args:
        name: 输出文件名
        with_cover: 是否注册封面
        chapters: [(标题, 正文), ...]，默认两章
        images: 图片文件名列表（可含子目录路径，如 'img/a.png'）
    """
    from ebooklib import epub

    def _make(name='in.epub', with_cover=False, chapters=None, images=None):
        book = epub.EpubBook()
        book.set_identifier('test-id')
        book.set_title('测试书')
        book.set_language('zh')
        items = []
        for i, (t, body) in enumerate(chapters or [('第一章', '甲'), ('第二章', '乙')], 1):
            ch = epub.EpubHtml(title=t, file_name=f'ch{i}.xhtml', lang='zh')
            ch.content = f'<h2>{t}</h2><p>{body}</p>'
            book.add_item(ch)
            items.append(ch)
        for j, img_name in enumerate(images or [], 1):
            book.add_item(epub.EpubItem(
                uid=f'img{j}', file_name=img_name,
                media_type='image/png', content=f'PNG{j}'.encode(),
            ))
        # 注意：set_cover 必须在 add_item(Ncx/Nav) 之前，
        # 否则 cover.xhtml 排在 nav.xhtml 之后，ebooklib 生成 nav
        # 时会 parse 空的 cover 文档抛 ParserError: Document is empty
        if with_cover:
            book.set_cover('cover.jpeg', b'\xff\xd8\xff\xe0fake')
        book.toc = tuple(items)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        if with_cover:
            book.spine = ['cover'] + items
        else:
            book.spine = list(items)
        path = str(tmp_path / name)
        epub.write_epub(path, book, {})
        return path

    return _make
```

- [ ] **Step 2: 创建 requirements-dev.txt**

```
pytest
ruff
```

- [ ] **Step 3: 写基础测试 tests/test_txt2epub.py**

```python
# -*- coding: utf-8 -*-
"""Txt2Epub 基础行为测试。"""
import os
import zipfile


def test_get_chapters(sample_txt):
    from services import Txt2Epub
    conv = Txt2Epub(sample_txt, 'unused.epub')
    assert conv.get_chapters() == ['第一章 开始', '第二章 继续']


def test_convert_creates_epub(sample_txt, tmp_path):
    from services import Txt2Epub
    out = str(tmp_path / 'out.epub')
    conv = Txt2Epub(sample_txt, out)
    conv.title = '测试书'
    conv.convert()
    assert os.path.exists(out)
    assert zipfile.ZipFile(out).testzip() is None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 2 passed（现有代码已满足这两个行为）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "test: add pytest harness and basic Txt2Epub tests"
```

---

### Task 2: 章节分隔符失效修复（P0-1）

**背景:** 下拉三项经 `sep.replace('\\n', '\n')` 后都以 `\n` 开头，而 `services.py` 判断 `not sep.startswith('\n')` → 永不追加，四个选项输出完全相同（已实测 DISTINCT=1）。

**Files:**
- Create: `tests/test_epub2txt.py`
- Modify: `services.py`（`Epub2Txt._process_document`）

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""Epub2Txt 转换行为测试。"""
from pathlib import Path

from services import Epub2Txt


def test_sep_variants_differ(make_epub, tmp_path):
    """四个分隔符选项应产生四种不同输出。"""
    texts = []
    for i, sep in enumerate(['', '\n', '\n\n', '\n---\n']):
        out = str(tmp_path / f'out{i}.txt')
        conv = Epub2Txt(make_epub(), out)
        conv.sep = sep
        conv.convert()
        texts.append(Path(out).read_text(encoding='utf-8'))

    assert len(set(texts)) == 4
    assert texts[0].count('\n') < texts[1].count('\n') < texts[2].count('\n')
    assert '---' in texts[3]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_epub2txt.py -v`
Expected: FAIL（`len(set(texts)) == 4` 实际为 1）

- [ ] **Step 3: 修复 `_process_document` 分隔符判断**

将 `services.py` 中：

```python
        text = text.rstrip('\n') + '\n'
        # 分隔符处理：如果用户选了分隔符且不是纯换行，追加到文本末尾
        if self.sep and not self.sep.startswith('\n'):
            text += self.sep
        return text
```

改为：

```python
        text = text.rstrip('\n') + '\n'
        # 分隔符追加到每章文本末尾（'（无）'时 window 传入空串，不追加）
        if self.sep:
            text += self.sep
        return text
```

说明：window 侧（`window.py` `_run_epub_to_txt`）`if sep and sep != '（无）': reader.sep = sep.replace('\\n', '\n')` 已正确，无需改动。语义：基线每章以单个 `\n` 结尾，选项在基线之上追加额外分隔（`'\n'`→空行、`'\n\n'`→两个空行、`'\n---\n'`→分割线）。

**评审补丁（已执行）:** `_process_document` 为 `convert()`/`convert_chapter()` 共用路径，按章节导出每文件只有一章，"章节间分隔符"不适用。`convert_chapter()` 内暂存 `self.sep` 置空、`try/finally` 恢复，忽略分隔符；`convert()` 行为不变。新增测试 `test_convert_chapter_ignores_sep`。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed（含既有 2 个）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "fix: apply chapter separator in EPUB to TXT conversion"
```

### Task 3: HTML 转义与段落分段（P0-4）

**背景:** `services.py` convert() 把原始 TXT 文本直接嵌入 `<p>`/`<h2>`，正文含 `<`、`&` 会被当标签解析导致内容丢失。

**Files:**
- Modify: `services.py`（新增 `_text_to_html`；改 `convert()` 序章与正文两处）
- Modify: `tests/test_txt2epub.py`（追加测试）

- [ ] **Step 1: 写失败测试（追加到 tests/test_txt2epub.py）**

```python
def test_html_escaping(tmp_path):
    """正文中的 <、>、& 必须被转义，不能当成标签。"""
    from services import Txt2Epub
    txt = tmp_path / 'x.txt'
    txt.write_text(
        '第1章 前<后\n正文<b>加粗</b>与&符号\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'x.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()

    z = zipfile.ZipFile(out)
    joined = b''.join(
        z.read(n) for n in z.namelist() if n.endswith('.xhtml')
    ).decode('utf-8')
    assert '<b>加粗</b>' not in joined
    assert '&lt;' in joined


def test_paragraph_split(tmp_path):
    """空行应拆分成独立 <p> 段落。"""
    from services import Txt2Epub
    txt = tmp_path / 'p.txt'
    txt.write_text(
        '第一章 标题\n第一段。\n\n第二段。\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'p.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()

    z = zipfile.ZipFile(out)
    joined = b''.join(
        z.read(n) for n in z.namelist() if n.endswith('.xhtml')
    ).decode('utf-8')
    assert '<p>第一段。</p>' in joined
    assert '<p>第二段。</p>' in joined
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_txt2epub.py -v`
Expected: 两个新测试 FAIL（原文未转义、未分段）

- [ ] **Step 3: services.py 顶部加 `import html`**

在 `import os` 之前加：

```python
import html
```

- [ ] **Step 4: 新增 `_text_to_html` 模块函数（放在 CSS_STYLE 定义之后、Txt2Epub 类之前）**

```python
def _text_to_html(text: str) -> str:
    """把纯文本转成安全 HTML。

    1. html.escape 转义 <、>、&，防止正文字符被当成标签解析
    2. 按空行（连续换行）拆分成多个 <p> 段落，段内换行转 <br>
    """
    text = html.escape(text.replace(chr(160), ' '), quote=False)
    paragraphs = re.split(r'\n\s*\n+', text)
    return ''.join(
        f'<p>{p.strip().replace(chr(10), "<br>")}</p>'
        for p in paragraphs
        if p.strip()
    )
```

- [ ] **Step 5: 改写 convert() 序章块**

将：

```python
        # ---- 序章 ----
        # splits[0] 是第一个标题之前的所有文本（没有标题的部分）
        # 如果长度 > 5 个字符，就生成一个独立的序章章节
        preamble = splits[0].replace('\n', '<br>').replace(chr(160), '')
        total = len(chapters) + 1  # 章节数 + 序章

        if len(preamble) > _MIN_PREAMBLE_LEN:
            if status:
                status('正在生成序章…')
            ch = epub.EpubHtml(title='xu', file_name='xu.xhtml', lang='zh')
            ch.content = f'<p>{preamble}</p>'
            ch.add_item(nav_css)
            book.add_item(ch)
            book.spine.append(ch)
```

改为：

```python
        # ---- 序章 ----
        # splits[0] 是第一个标题之前的所有文本（没有标题的部分）
        # 长度按原始文本判断（转义后长度会变化，不能用于判断）
        raw_preamble = splits[0]
        has_preamble = len(raw_preamble.strip()) > _MIN_PREAMBLE_LEN
        total = len(chapters) + (1 if has_preamble else 0)

        if has_preamble:
            if status:
                status('正在生成序章…')
            ch = epub.EpubHtml(title='xu', file_name='xu.xhtml', lang='zh')
            ch.content = _text_to_html(raw_preamble)
            ch.add_item(nav_css)
            book.add_item(ch)
            book.spine.append(ch)
```

- [ ] **Step 6: 改写逐章生成的正文两处**

循环开头（原 `body = body.replace('\n', '<br>').replace(chr(160), '')`）改为：

```python
            body_html = _text_to_html(body)
```

章节 content 行改为：

```python
            ch.content = (
                f'<h2>{html.escape(title.strip(), quote=False)}</h2>{body_html}'
            )
```

- [ ] **Step 7: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "escape HTML and split paragraphs in EPUB output"
```

---

### Task 4: spine 合法性 + 序章入目录 + 进度到 100%（P0-5）

**背景:** (a) 封面缺失时仍写 `spine=['cover']` → opf 含 `idref="cover"` 指向不存在的 item（已实测）；(b) 序章不进 `book.toc` → 阅读器目录看不到（已实测 XU_IN_NAV=False）；(c) `total=len(chapters)+1` 但序章不报进度 → 永远到不了 100%。

**Files:**
- Modify: `services.py`（`Txt2Epub.convert()` 封面/spine/序章/进度四处）
- Modify: `tests/test_txt2epub.py`（追加 4 个测试）

- [ ] **Step 1: 写失败测试（追加到 tests/test_txt2epub.py）**

```python
def test_spine_without_cover(sample_txt, tmp_path):
    """封面缺失时 spine 不能引用 cover。"""
    from services import Txt2Epub
    out = tmp_path / 'no_cover.epub'
    conv = Txt2Epub(sample_txt, str(out))
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()
    opf = zipfile.ZipFile(str(out)).read('EPUB/content.opf').decode('utf-8')
    assert 'idref="cover"' not in opf


def test_spine_with_cover(sample_txt, tmp_path):
    """封面存在时 spine 应包含 cover（回归保护）。"""
    from services import Txt2Epub
    out = tmp_path / 'with_cover.epub'
    conv = Txt2Epub(sample_txt, str(out))
    conv.convert()  # 默认封面 resources/images/cover.jpeg 存在
    opf = zipfile.ZipFile(str(out)).read('EPUB/content.opf').decode('utf-8')
    assert 'idref="cover"' in opf


def test_preamble_in_toc(sample_txt, tmp_path):
    """序章必须出现在导航目录中。"""
    from services import Txt2Epub
    out = tmp_path / 'toc.epub'
    conv = Txt2Epub(sample_txt, str(out))
    conv.convert()
    nav = zipfile.ZipFile(str(out)).read('EPUB/nav.xhtml').decode('utf-8')
    assert '序章' in nav


def test_progress_completes(sample_txt, tmp_path):
    """最后一次进度上报应达到 total/total。"""
    from services import Txt2Epub
    conv = Txt2Epub(sample_txt, str(tmp_path / 'prog.epub'))
    calls = []
    conv.convert(progress=lambda c, t: calls.append((c, t)))
    assert calls
    assert calls[-1][0] == calls[-1][1]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_txt2epub.py -v`
Expected: `test_spine_without_cover`、`test_preamble_in_toc`、`test_progress_completes` FAIL；`test_spine_with_cover` PASS

- [ ] **Step 3: 封面注册加 has_cover 标记**

将：

```python
        # ---- 封面 ----
        if os.path.exists(self.cover_path):
            with open(self.cover_path, 'rb') as f:
                book.set_cover('cover.jpeg', f.read())
```

改为：

```python
        # ---- 封面 ----
        # 只有封面真实存在时才注册封面并写入 spine，
        # 否则 spine 会引用不存在的 item，产出结构非法的 EPUB
        has_cover = os.path.exists(self.cover_path)
        if has_cover:
            with open(self.cover_path, 'rb') as f:
                book.set_cover('cover.jpeg', f.read())
```

- [ ] **Step 4: spine 按 has_cover 赋值**

将 `book.spine = ['cover']` 一行（及其上方注释行）改为：

```python
        # spine 定义了 EPUB 的阅读顺序；'cover' 是封面页占位符
        book.spine = ['cover'] if has_cover else []
```

- [ ] **Step 5: 序章加入 toc 并上报进度**

在 Task 3 改过的序章块中，`book.spine.append(ch)` 之后追加：

```python
            # 加入目录，阅读器里才能看到序章
            book.toc.append(epub.Link('xu.xhtml', '序章', 'intro'))
            if progress and total > 0:
                progress(1, total)
```

- [ ] **Step 6: 逐章进度计入序章偏移**

**（status 分母 `{idx}/{total-1}` → `{idx}/{len(chapters)}` 已在 Task 3 评审修复中提前完成，跳过该部分。）**

将循环开头（如仍存在旧 status 行）：

```python
        for idx, (title, body) in enumerate(chapters, start=1):
            if status:
                status(f'正在处理第 {idx}/{total-1} 章: {title.strip()[:_STATUS_TITLE_LEN]}…')
            if progress:
                progress(idx, total)
```

改为：

```python
        done = 1 if has_preamble else 0
        for idx, (title, body) in enumerate(chapters, start=1):
            if status:
                status(f'正在处理第 {idx}/{len(chapters)} 章: {title.strip()[:_STATUS_TITLE_LEN]}…')
            if progress and total > 0:
                progress(done + idx, total)
```

- [ ] **Step 7: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "fix EPUB spine validity, preamble TOC entry and progress"
```

---

### Task 5: 章节按索引排序与重命名（P0-6）

**背景:** `ChapterDialog` 允许重命名，但转换用"重命名后标题"去 dict 查原章节 → 改过名的章被静默丢弃；重复标题互相覆盖。改为传 `(原始索引, 新标题)`。

**Files:**
- Modify: `dialogs.py`（item 存 UserRole 索引；新增 `get_ordered_items()`）
- Modify: `services.py`（`set_chapter_order` 改签名为索引元组；convert() 重排逻辑）
- Modify: `window.py`（`_ordered_chapters` 类型与 `_on_preview_chapters`）
- Create: `tests/test_chapter_order.py`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""章节排序 / 重命名行为测试。"""
import zipfile

from services import Txt2Epub


def test_rename_by_index(tmp_path):
    """重命名 + 调序：新标题生效、顺序正确、正文不串章。"""
    txt = tmp_path / 'r.txt'
    txt.write_text(
        '第一章 啊\n正文一。\n第一章 啊\n正文二。\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'r.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.set_chapter_order([(1, '改B'), (0, '改A')])
    conv.convert()

    z = zipfile.ZipFile(out)
    nav = z.read('EPUB/nav.xhtml').decode('utf-8')
    assert '改B' in nav and '改A' in nav
    assert nav.index('改B') < nav.index('改A')
    ca = z.read('EPUB/改A.xhtml').decode('utf-8')
    cb = z.read('EPUB/改B.xhtml').decode('utf-8')
    assert '正文一' in ca and '正文二' in cb


def test_duplicate_titles_not_dropped(tmp_path):
    """重复章节标题默认顺序下两章都要生成。"""
    txt = tmp_path / 'd.txt'
    txt.write_text(
        '第一章 啊\n正文一。\n第一章 啊\n正文二。\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'd.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()
    names = [n for n in zipfile.ZipFile(out).namelist() if n.endswith('.xhtml')]
    assert len([n for n in names if 'nav' not in n and 'xu' not in n]) == 2


def test_original_order_when_none(tmp_path):
    """传 None 时保持原序（回归保护）。"""
    txt = tmp_path / 'o.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    conv = Txt2Epub(str(txt), str(tmp_path / 'o.epub'))
    assert conv.get_chapters() == ['第1章 甲', '第1章 乙']
    conv.set_chapter_order(None)
    assert conv.get_chapters() == ['第1章 甲', '第1章 乙']
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_chapter_order.py -v`
Expected: `test_rename_by_index` FAIL（重命名被忽略）；其余两个 PASS（回归保护）

- [ ] **Step 3: dialogs.py — item 存原始索引**

`__init__` 中列表填充循环改为：

```python
        for i, ch in enumerate(chapters):
            item = QListWidgetItem(ch)
            # 存原始索引：拖拽/重命名都不会丢失"这是第几章"的信息
            item.setData(Qt.ItemDataRole.UserRole, i)
            # ItemIsEditable 让用户可以双击编辑标题
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            self._list.addItem(item)
```

- [ ] **Step 4: dialogs.py — 用 get_ordered_items 替换 get_ordered_chapters**

将 `get_ordered_chapters` 整个方法替换为：

```python
    def get_ordered_items(self) -> list[tuple[int, str]]:
        """
        获取排序后的章节列表：[(原始索引, 新标题), ...]。

        InternalMove 拖拽会连同 UserRole 数据一起移动，
        双击重命名只改显示文本，原始索引保持不变。
        调用前确保对话框已关闭且用户点了"确定"。
        """
        return [
            (self._list.item(i).data(Qt.ItemDataRole.UserRole),
             self._list.item(i).text().strip())
            for i in range(self._list.count())
        ]
```

- [ ] **Step 5: services.py — set_chapter_order 新签名**

将：

```python
    def set_chapter_order(self, ordered: list[str] | None) -> None:
        """设置自定义章节顺序（由 ChapterDialog 拖拽调整后传入）。

        如果传 None，则按原始文件顺序。"""
        self._chapter_order = ordered
```

改为：

```python
    def set_chapter_order(self, ordered: list[tuple[int, str]] | None) -> None:
        """设置自定义章节顺序：[(原始索引, 新标题), ...]。

        用索引而不是标题匹配：重命名后的标题查不到原章，
        重复标题也会互相覆盖。传 None 表示按原始文件顺序。"""
        self._chapter_order = ordered
```

同步改 `__init__` 中字段注释行：

```python
        self._chapter_order: Optional[list[tuple[int, str]]] = None  # 自定义章节顺序 [(索引, 新标题)]
```

- [ ] **Step 6: services.py — convert() 重排逻辑改为索引**

将：

```python
        # ---- 应用自定义章节顺序 ----
        # 如果用户在 ChapterDialog 中拖拽调整了顺序，这里起作用
        if self._chapter_order:
            # 用标题作为唯一标识，从原章节列表中查找匹配
            # 先用字典建立标题→(标题,正文)的映射
            lookup = {t.strip(): (t, b) for t, b in chapters}
            ordered = []
            for t in self._chapter_order:
                tt = t.strip()
                if tt in lookup:
                    ordered.append(lookup[tt])
            if ordered:
                chapters = ordered
```

改为：

```python
        # ---- 应用自定义章节顺序 ----
        # 按 (原始索引, 新标题) 重排：索引避免重命名查不到、重复标题覆盖
        if self._chapter_order:
            reordered = []
            used: set[int] = set()
            for idx, new_title in self._chapter_order:
                if 0 <= idx < len(chapters) and idx not in used:
                    _, body = chapters[idx]
                    reordered.append((new_title, body))
                    used.add(idx)
            # 未出现在列表中的章节按原序补到末尾（防止丢章）
            for i, pair in enumerate(chapters):
                if i not in used:
                    reordered.append(pair)
            if reordered:
                chapters = reordered
```

- [ ] **Step 7: window.py — 状态类型与预览回传**

`__init__` 中类型注释改为：

```python
        self._ordered_chapters: list[tuple[int, str]] | None = None  # ChapterDialog 调整后的章节 [(索引, 新标题)]
```

`_on_preview_chapters` 中 `if dlg.exec():` 分支改为：

```python
            if dlg.exec():
                items = dlg.get_ordered_items()
                original = [(i, t) for i, t in enumerate(chapters)]
                if items != original:
                    self._ordered_chapters = items
                    self.statusBar().showMessage(
                        f'章节顺序已调整（{len(items)} 章）')
                else:
                    self._ordered_chapters = None
```

- [ ] **Step 8: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 9: 提交**

```bash
git add -A && git commit -m "order and rename chapters by original index"
```

---

### Task 6: 章节正则捕获组校验（P0-7）

**背景:** 代码假设正则恰好 1 个捕获组；用户自定义 0 或 2 个组时 `re.split` 结果错位、生成乱章节且无提示。

**Files:**
- Modify: `services.py`（新增 `validate_chapter_regex()`；`_parse()` 使用）
- Modify: `window.py`（`_on_convert_tab1` 启动前校验）
- Create: `tests/test_regex_validation.py`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""章节正则校验测试。"""
import pytest

from services import Txt2Epub, validate_chapter_regex, DEFAULT_CHAPTER_REGEX


def test_default_regex_ok():
    validate_chapter_regex(DEFAULT_CHAPTER_REGEX)  # 不抛异常


def test_regex_without_capture_group(sample_txt):
    conv = Txt2Epub(sample_txt, 'out.epub')
    conv.regex = r'^第.*章.*$'
    with pytest.raises(ValueError, match='捕获组'):
        conv.get_chapters()


def test_regex_with_two_capture_groups(sample_txt):
    conv = Txt2Epub(sample_txt, 'out.epub')
    conv.regex = r'(第)(\d+)章.*'
    with pytest.raises(ValueError, match='捕获组'):
        conv.get_chapters()


def test_invalid_regex_syntax(sample_txt):
    conv = Txt2Epub(sample_txt, 'out.epub')
    conv.regex = '(未闭合'
    with pytest.raises(ValueError, match='无效的正则'):
        conv.get_chapters()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_regex_validation.py -v`
Expected: FAIL（`validate_chapter_regex` 不存在 → ImportError/收集失败）

- [ ] **Step 3: services.py 新增 validate_chapter_regex**

放在 `_text_to_html` 之后：

```python
def validate_chapter_regex(pattern: str) -> re.Pattern:
    """校验章节正则：必须能编译，且恰好含 1 个捕获组。

    re.split 靠捕获组把标题带回结果列表（[前言, 标题, 正文, ...] 交替），
    0 个组会把正文当标题，2 个组会元素错位，必须在入口拦住。

    Returns:
        编译好的正则对象（调用方可复用）

    Raises:
        ValueError: 语法错误或捕获组数量不为 1
    """
    try:
        compiled = re.compile(pattern, re.M)
    except re.error as e:
        raise ValueError(f'无效的正则表达式: {pattern}\n{e}') from e
    if compiled.groups != 1:
        raise ValueError(
            f'章节正则必须包含且仅包含 1 个捕获组（括号），'
            f'当前有 {compiled.groups} 个: {pattern}'
        )
    return compiled
```

- [ ] **Step 4: `_parse()` 使用校验**

将 `_parse()` 中：

```python
            # re.M（MULTILINE）让 ^ 匹配每行开头，而不只是字符串开头。
            try:
                self._splits = re.split(self.regex, content, flags=re.M)
            except re.error as e:
                raise ValueError(f'无效的正则表达式: {self.regex}\n{e}')
```

改为：

```python
            # re.M（MULTILINE）让 ^ 匹配每行开头，而不只是字符串开头。
            compiled = validate_chapter_regex(self.regex)
            self._splits = compiled.split(content)
```

- [ ] **Step 5: window.py 转换前预校验**

`_on_convert_tab1` 中 `conv.set_chapter_order(...)` 之前插入：

```python
        # 启动后台线程前先校验正则，避免错误延迟到 worker 里才弹窗
        try:
            validate_chapter_regex(conv.regex)
        except ValueError as e:
            QMessageBox.warning(self, '提示', str(e))
            return
```

`window.py` 第 60 行 import 改为：

```python
from services import (
    Txt2Epub, Epub2Txt, Epub2Mobi, convert_mobi_to_txt,
    DEFAULT_CHAPTER_REGEX, validate_chapter_regex,
)
```

- [ ] **Step 6: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "validate chapter regex has exactly one capture group"
```

### Task 7: 输出目录创建顺序 + convert_chapter 空目录（P0-8/9）

**背景:** (a) `convert()` 先 `_save_cover_if_exists()` 再 `os.makedirs` → 输出目录不存在时含封面的 EPUB 直接 `FileNotFoundError`；(b) `convert_chapter()` 对空 `out_dir` 无保护 → `os.makedirs('')` 抛异常，且与 `convert()` 同段逻辑不一致。

**Files:**
- Modify: `services.py`（`Epub2Txt.convert()` 与 `convert_chapter()`）
- Modify: `tests/test_epub2txt.py`（追加 2 个测试）

- [ ] **Step 1: 写失败测试（追加到 tests/test_epub2txt.py）**

```python
def test_convert_creates_missing_outdir_with_cover(make_epub, tmp_path):
    """输出目录不存在 + 有封面时也应成功（先建目录再存封面）。"""
    out = str(tmp_path / 'newdir' / 'o.txt')
    conv = Epub2Txt(make_epub(with_cover=True), out)
    conv.convert()
    assert Path(out).exists()
    assert (tmp_path / 'newdir' / 'cover.jpeg').exists()


def test_convert_chapter_outdir_empty(make_epub, tmp_path, monkeypatch):
    """txt_path 无目录部分（如 out.txt）时不能因 makedirs('') 崩溃。"""
    monkeypatch.chdir(tmp_path)
    conv = Epub2Txt(make_epub(), 'base.txt')
    conv.convert_chapter()
    assert (tmp_path / 'base1.txt').exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_epub2txt.py -v`
Expected: `test_convert_creates_missing_outdir_with_cover` FAIL（FileNotFoundError）

- [ ] **Step 3: convert() 调整顺序**

将：

```python
        self._save_cover_if_exists()

        docs = self._get_content_items()
        total = len(docs)

        # 确保输出目录存在
        out_dir = os.path.dirname(self.txt_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
```

改为：

```python
        # 先确保输出目录存在，再提取封面（顺序反了目录不存在会 FileNotFoundError）
        out_dir = os.path.dirname(self.txt_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self._save_cover_if_exists()

        docs = self._get_content_items()
        total = len(docs)
```

- [ ] **Step 4: convert_chapter() 加空目录保护**

将：

```python
        out_dir = os.path.dirname(self.txt_path)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)

        self._save_cover_if_exists()
```

改为：

```python
        out_dir = os.path.dirname(self.txt_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self._save_cover_if_exists()
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "create output directory before saving cover"
```

---

### Task 8: 字体/目录样式覆盖失效修复（P0-3）

**背景:** `window.py` 用定向字符串 `replace()` 替换 `font-family: Cambria...` 和 `list-style-type: square;`，但 `minimal.css`/`modern.css` 不含这两个子串 → 静默跳过。改为在 CSS 末尾追加覆盖规则（层叠规则：同优先级后写生效），对所有样式文件都有效。

**Files:**
- Modify: `services.py`（`Txt2Epub` 新增 `apply_text_style()`）
- Modify: `window.py`（`_on_convert_tab1` 替换两段 replace）
- Modify: `tests/test_txt2epub.py`（追加测试）

- [ ] **Step 1: 写失败测试（追加到 tests/test_txt2epub.py）**

```python
def test_apply_text_style(sample_txt, tmp_path):
    """追加覆盖规则必须生效，且不破坏原 CSS。"""
    from services import Txt2Epub
    conv = Txt2Epub(sample_txt, str(tmp_path / 's.epub'))
    before = conv.css_style
    conv.apply_text_style('SimHei, "Hei Ti", sans-serif', 'disc')
    assert conv.css_style.startswith(before.rstrip('\n'))
    assert 'font-family: SimHei, "Hei Ti", sans-serif;' in conv.css_style
    assert 'list-style-type: disc;' in conv.css_style


def test_apply_text_style_on_minimal_css(sample_txt, tmp_path):
    """minimal.css 不含 Cambria/square 子串，追加方式仍应生效。"""
    from services import Txt2Epub
    styles = os.path.join(os.path.dirname(__file__), '..', 'styles')
    conv = Txt2Epub(sample_txt, str(tmp_path / 'm.epub'))
    conv.load_css_from_file(os.path.join(styles, 'minimal.css'))
    conv.apply_text_style('KaiTi, serif', 'decimal')
    assert 'font-family: KaiTi, serif;' in conv.css_style
    assert 'list-style-type: decimal;' in conv.css_style
```

（`os` 已在文件顶部 import。）

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_txt2epub.py -v`
Expected: 两个新测试 FAIL（方法不存在 → AttributeError）

- [ ] **Step 3: services.py 新增 apply_text_style**

在 `Txt2Epub.load_css_from_file` 方法之后添加：

```python
    def apply_text_style(self, font_family: str, toc_marker: str) -> None:
        """在 CSS 末尾追加正文字体与目录样式的覆盖规则。

        为什么用追加而不是字符串替换？
        default/minimal/modern 三个样式文件的 font-family 和
        list-style-type 写法各不相同，定向 replace 会静默失效。
        CSS 层叠规则：同优先级下后写的规则生效，追加即可全局覆盖。
        """
        overrides = []
        if font_family:
            overrides.append(f'body {{ font-family: {font_family}; }}')
        if toc_marker:
            overrides.append(
                "nav[epub|type~='toc'] > ol > li > ol { "
                f'list-style-type: {toc_marker}; }}'
            )
        if overrides:
            self.css_style = (
                self.css_style.rstrip() + '\n' + '\n'.join(overrides) + '\n'
            )
```

- [ ] **Step 4: window.py 替换两段 replace**

将 `_on_convert_tab1` 中从注释 `# 应用字体设置` 开始、到目录样式 replace 结束的整段（即下面这段旧代码）：

```python
        # 应用字体设置
        font_name = self._cb_font.currentText()
        if font_name in FONT_PRESETS:
            font_css = FONT_PRESETS[font_name]
            conv.css_style = conv.css_style.replace(
                'font-family: Cambria, "Liberation Serif", Georgia, "Times New Roman", serif;',
                f'font-family: {font_css};'
            )
        
        # 应用目录样式
        toc_style_name = self._cb_toc_style.currentText()
        if toc_style_name in TOC_STYLES:
            toc_marker = TOC_STYLES[toc_style_name]
            conv.css_style = conv.css_style.replace(
                'list-style-type: square;',
                f'list-style-type: {toc_marker};'
            )
```

替换为：

```python
        # 应用正文字体和目录样式（追加覆盖规则，对所有样式文件都生效）
        conv.apply_text_style(
            FONT_PRESETS.get(self._cb_font.currentText(), ''),
            TOC_STYLES.get(self._cb_toc_style.currentText(), ''),
        )
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "override font and toc styles via appended CSS rules"
```

---

### Task 9: "自动检测"编码真正参与转换（P0-2）

**背景:** `chardet.detect` 结果只显示在状态栏；转换时 index=0（自动检测）保持默认 utf-8 + `errors='replace'` → GBK 文件静默变乱码且无报错。

**Files:**
- Modify: `window.py`（`__init__`、`_load_txt_file`、`_on_convert_tab1`、`_on_preview_chapters`、`_on_reset_tab1`）

- [ ] **Step 1: `__init__` 状态变量区（`self._cc_t2s = None` 行之后）新增**

```python
        self._detected_encoding = 'utf-8'          # chardet 检测到的输入编码
```

- [ ] **Step 2: `_load_txt_file` 保存检测结果**

将：

```python
        with open(path, 'rb') as f:
            data = f.read(_ENCODE_DETECT_SIZE)
            info = chardet.detect(data) or {}
            enc = info.get('encoding') or 'utf-8'
            lang = info.get('language', '未知')
            self.statusBar().showMessage(f'文件: {fname}  编码: {enc}')
            logger.info(f'文件检测: {fname} 编码={enc} 语言={lang}')
```

改为：

```python
        with open(path, 'rb') as f:
            data = f.read(_ENCODE_DETECT_SIZE)
            info = chardet.detect(data) or {}
            enc = info.get('encoding') or 'utf-8'
            lang = info.get('language', '未知')
            self._detected_encoding = enc
            self.statusBar().showMessage(f'文件: {fname}  编码: {enc}')
            logger.info(f'文件检测: {fname} 编码={enc} 语言={lang}')
```

- [ ] **Step 3: 新增统一取编码的方法（放在 `_load_txt_file` 之后）**

```python
    def _current_txt_encoding(self) -> str:
        """返回 tab1 当前生效的输入编码。

        "自动检测"（index=0）时返回 chardet 结果，
        否则返回用户手动选择的编码。检测失败回退 utf-8。
        """
        if self._cb_encode.currentIndex() == 0:
            return self._detected_encoding or 'utf-8'
        return self._cb_encode.currentText()
```

- [ ] **Step 4: `_on_convert_tab1` 使用该方法**

将：

```python
        if self._cb_encode.currentIndex() != 0:
            conv.encoding = self._cb_encode.currentText()
```

改为：

```python
        conv.encoding = self._current_txt_encoding()
```

- [ ] **Step 5: `_on_preview_chapters` 同样使用**

将：

```python
            if self._cb_encode.currentIndex() != 0:
                conv.encoding = self._cb_encode.currentText()
```

改为：

```python
            conv.encoding = self._current_txt_encoding()
```

- [ ] **Step 6: `_on_reset_tab1` 重置检测值**

在 `self._cb_encode.setCurrentIndex(0)` 之后加：

```python
        self._detected_encoding = 'utf-8'
```

- [ ] **Step 7: 验证（手动）**

Run: `python main.py`
Expected: 选择一个 GBK 编码的 TXT，状态栏显示"编码: GBK"，下拉保持"自动检测"，生成的 EPUB 中文正常不乱码。

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "use detected encoding for auto-detect mode"
```

---

### Task 10: 转换重入保护 + 关闭窗口取消线程（P1）

**背景:** 快捷键挂在 MainWindow 上不受 tabs 禁用影响，转换中按 Ctrl+Enter 会覆盖 `_worker` → 取消按钮失效；`closeEvent` 不 cancel/wait 可能触发 "QThread destroyed while running"。

**Files:**
- Modify: `window.py`（`_run_worker`、新增 `_is_busy`、三个快捷键、`closeEvent`）

- [ ] **Step 1: 新增 `_is_busy`（放在 `_run_worker` 方法之前）**

```python
    def _is_busy(self) -> bool:
        """是否有后台任务正在运行。"""
        return self._worker is not None and self._worker.isRunning()
```

- [ ] **Step 2: `_run_worker` 入口加重入保护**

在 `_run_worker` 函数体最开头（`def _progress` 闭包定义之前）加：

```python
        if self._is_busy():
            self.statusBar().showMessage('已有转换任务进行中，请等待完成或取消')
            logger.warning('忽略重复启动的后台任务')
            return
```

- [ ] **Step 3: 三个快捷键处理器加保护**

`_on_shortcut_convert` 开头加：

```python
        if self._is_busy():
            self.statusBar().showMessage('已有转换任务进行中…')
            return
```

`_on_shortcut_open`、`_on_shortcut_reset` 开头各加：

```python
        if self._is_busy():
            return
```

- [ ] **Step 4: closeEvent 取消并等待**

将：

```python
    def closeEvent(self, event):
        """窗口关闭时自动保存配置。

        QMainWindow 内置了 closeEvent，重写它可以在窗口关闭前执行清理操作。
        注意一定要调用 super().closeEvent(event)，否则窗口关不掉。
        """
        self._save_config()
        super().closeEvent(event)
```

改为：

```python
    def closeEvent(self, event):
        """窗口关闭时取消运行中的任务并保存配置。

        先 cancel 再 wait(3秒)：让 worker 尽快结束，
        避免 "QThread destroyed while running"。
        超时则放行（不阻塞用户退出）。
        """
        if self._is_busy():
            self._worker.cancel()
            if not self._worker.wait(3000):
                logger.warning('后台任务未能在 3 秒内结束，强制退出')
        self._save_config()
        super().closeEvent(event)
```

- [ ] **Step 5: 验证**

Run: `python -m pytest tests/ -v`（回归）
Run: `python main.py`（手动：转换中反复按 Ctrl+Enter 只弹一次状态提示；转换中关窗口程序正常退出）

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "guard against reentrant worker launches and cancel on close"
```

---

### Task 11: 取消语义区分 + finished 信号改名（P1）

**背景:** (a) `finished` 遮蔽了 `QThread.finished`，任何按 Qt 惯例使用它的后续维护者都会踩坑；(b) 取消后 `finished.emit(True, '')` → UI 显示"转换完成"并弹窗问打开目录，但产物根本没写盘。

**Files:**
- Modify: `worker.py`（信号改名 `task_done`，三态结果）
- Modify: `window.py`（`_run_worker` 连接与 `_done` 分支）

- [ ] **Step 1: worker.py 信号定义改为**

```python
    # 定义信号。pyqtSignal 在类级别定义，PyQt 元类自动处理。
    # 注意：不能叫 finished——那会遮蔽 QThread 内置的 finished() 信号。
    progress = pyqtSignal(int, int)          # (completed, total) 进度
    status = pyqtSignal(str)                 # 状态栏文本
    task_done = pyqtSignal(bool, str, bool)  # (成功, 错误消息, 是否被取消)
```

- [ ] **Step 2: run() 三个 emit 改为**

成功分支：

```python
            # 没有抛异常 => 成功
            self.task_done.emit(True, '', False)
```

取消分支：

```python
        except CancelledError:
            # 用户取消：既不是成功也不是错误，单独一种结果
            self.task_done.emit(False, '', True)
```

错误分支：

```python
        except Exception as e:
            # 任务抛异常了（比如文件不存在、编码错误等），
            # 通过 task_done 信号把异常信息传回主线程。
            logger.exception('后台任务执行失败')
            self.task_done.emit(False, str(e), False)
```

- [ ] **Step 3: 更新 worker.py 文档**

模块 docstring 用法示例中 `worker.finished.connect(on_done)` 改为：

```python
    worker.task_done.connect(on_done)
```

类 docstring 中 `- finished: 任务结束通知（成功/失败，错误信息）` 改为：

```python
    - task_done: 任务结束通知（成功, 错误消息, 是否被取消）
```

类 docstring 中 "worker 通过信号通知 UI：进度更新、状态更新、任务完成" 段落里的 finished 描述同步改为 task_done。

- [ ] **Step 4: window.py `_done` 改为三态**

将 `_run_worker` 中的 `_done` 替换为：

```python
        def _done(ok, err, cancelled):
            """任务结束（成功 / 失败 / 取消）。"""
            self._progress_bar.setVisible(False)
            self._cancel_btn.setVisible(False)
            self._tabs.setEnabled(True)
            self._worker = None

            if cancelled:
                logger.info('任务已取消')
                self.statusBar().showMessage('已取消')
            elif ok:
                logger.info(success_msg)
                self.statusBar().showMessage(success_msg)
                self._ask_open_dir(dir_to_open)
            else:
                QMessageBox.critical(self, '错误', f'转换失败:\n{err}')
                self.statusBar().showMessage('转换失败')
```

连接行改为：

```python
        self._worker.task_done.connect(_done)
```

- [ ] **Step 5: 验证**

Run: `python -m pytest tests/ -v`
Run: `python main.py`（手动：转换中点"取消"→ 状态栏显示"已取消"，不弹"完成"窗口）

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "distinguish cancelled results and rename finished signal"
```

### Task 12: EPUB/MOBI 文件 IO 移出主线程（P1）

**背景:** `_load_epub_file`、`_on_save_metadata`、`_on_extract_images`、`_load_mobi_metadata`、`_run_epub_to_txt` 都在主线程 `epub.read_epub()`/解压 MOBI，大文件冻结 UI 数秒。

**设计:** `_run_worker` 增加 `on_success`（成功后回主线程执行的回调）、`fail_msg`（失败提示前缀）、`show_progress`（元数据读取不显示进度条/取消按钮）。UI 控件的读取全部在主线程预采集，worker 里只做文件 IO。

**Files:**
- Modify: `window.py`（`_run_worker` + 5 个调用点）

- [ ] **Step 1: `_run_worker` 扩展签名与逻辑**

新签名：

```python
    def _run_worker(self, target, success_msg: str = '', dir_to_open: str = '',
                    on_success=None, fail_msg: str = '转换失败',
                    show_progress: bool = True):
        """启动后台线程执行耗时操作。

        Args:
            target: 业务函数，签名 target(progress, status)
            success_msg: 成功后的状态栏消息（空则不显示）
            dir_to_open: 成功后询问是否打开的目录（空则不询问）
            on_success: 成功后在主线程执行的回调（用于回填 UI）
            fail_msg: 失败时的提示前缀
            show_progress: 是否显示进度条与取消按钮（元数据读取为 False）
        """
```

（Task 10 加的重入保护保留在函数体开头。）

`_done` 成功分支改为：

```python
            elif ok:
                if on_success is not None:
                    on_success()
                if success_msg:
                    logger.info(success_msg)
                    self.statusBar().showMessage(success_msg)
                if dir_to_open:
                    self._ask_open_dir(dir_to_open)
```

失败分支中 `f'转换失败:\n{err}'` 改为 `f'{fail_msg}:\n{err}'`，`showMessage('转换失败')` 改为 `showMessage(fail_msg)`。

启动段改为：

```python
        # ---- 启动线程 ----
        self._worker = ProgressWorker(target)
        self._worker.progress.connect(_progress)
        self._worker.status.connect(_status)
        self._worker.task_done.connect(_done)
        if show_progress:
            self._cancel_btn.setVisible(True)
            self._cancel_btn.setEnabled(True)
            self._cancel_btn.setText('取消')
        self._tabs.setEnabled(False)  # 禁用标签页，防止用户重复点击
        self._worker.start()
```

`_progress` 闭包不变（元数据任务不发 progress，进度条自然不显示）。

- [ ] **Step 2: `_run_epub_to_txt` — UI 预采集 + worker 内建 reader**

将（从 `reader = Epub2Txt(epub_path, txt_path)` 到该方法末尾的 `self._run_worker(...)`）：

```python
        reader = Epub2Txt(epub_path, txt_path)
        if self._cb_out_code.currentIndex() != 0:
            reader.encoding = self._cb_out_code.currentText()
        sep = self._cb_sep.currentText()
        if sep and sep != '（无）':
            reader.sep = sep.replace('\\n', '\n')
        fanjian = self._chb_fanjian.isChecked()

        target = reader.convert_chapter if chapter_mode else reader.convert
        msg = '按章节导出完成' if chapter_mode else 'EPUB→TXT 转换完成'
        self._run_worker(
            target=lambda progress, status: target(
                fanjian=fanjian, progress=progress, status=status),
            success_msg=msg,
            dir_to_open=os.path.dirname(txt_path),
        )
```

改为：

```python
        # 主线程预采集 UI 值（worker 里不允许读控件）
        encoding = self._cb_out_code.currentText()
        sep = self._cb_sep.currentText()
        sep = sep.replace('\\n', '\n') if sep and sep != '（无）' else ''
        fanjian = self._chb_fanjian.isChecked()

        def _target(progress, status):
            # EPUB 读取放后台线程，大文件不冻结界面
            reader = Epub2Txt(epub_path, txt_path)
            reader.encoding = encoding
            reader.sep = sep
            convert = reader.convert_chapter if chapter_mode else reader.convert
            convert(fanjian=fanjian, progress=progress, status=status)

        msg = '按章节导出完成' if chapter_mode else 'EPUB→TXT 转换完成'
        self._run_worker(
            target=_target,
            success_msg=msg,
            dir_to_open=os.path.dirname(txt_path),
        )
```

- [ ] **Step 3: `_load_epub_file` 改为 worker 读取 + on_success 回填**

将整个 `_load_epub_file` 方法替换为：

```python
    def _load_epub_file(self, path: str):
        """加载 EPUB 文件到界面（元数据读取在后台线程执行）。

        流程：预采集 UI 值 → worker 读取元数据/封面 →
        on_success 在主线程回填输入框与封面。
        """
        if self._is_busy():
            return
        self._le_in_epub.setText(path)
        self._epub_dir, fname = os.path.split(path)
        base, _ = os.path.splitext(fname)

        # 自动填充 TXT 输出路径（与 EPUB 同目录同名）
        txt_path = os.path.join(self._epub_dir, base + '.txt')
        self._le_out_txt.setText(txt_path)

        self.statusBar().showMessage(f'正在读取: {fname}…')
        box: dict = {}

        def _read(progress, status):
            status(f'正在读取: {fname}…')
            reader = Epub2Txt(path, txt_path)
            box['info'] = reader.get_info()
            box['cover'] = reader.get_cover()

        def _fill():
            info = box['info']
            self._le_book_title.setText(info.title)
            self._le_book_creator.setText(info.creator)
            self._le_book_contrib.setText(info.contributor)
            if info.date:
                try:
                    # ISO 格式转成更友好的显示格式
                    dt = datetime.datetime.fromisoformat(info.date)
                    self._le_book_date.setText(
                        dt.strftime('%Y-%m-%d %H:%M:%S'))
                except (ValueError, OverflowError) as e:
                    logger.debug(f'日期解析失败: {info.date} -> {e}')
                    self._le_book_date.setText(info.date)
            self._le_book_desc.setText(info.description)
            cover_data = box['cover']
            if cover_data:
                img = QImage.fromData(cover_data)
                self._cover_label2.setPixmap(QPixmap.fromImage(img))
            logger.info(f'EPUB 信息: {info}')
            self.statusBar().showMessage(f'已加载: {fname}')

        self._run_worker(target=_read, on_success=_fill,
                         fail_msg='读取失败', show_progress=False)
```

- [ ] **Step 4: `_on_save_metadata` 改为 worker 写回**

将方法体中（EPUB 存在性校验之后的）`try:` 整块替换为：

```python
        # 主线程构建数据；文件 IO 放 worker
        info = BookInfo(
            title=self._le_book_title.text(),
            creator=self._le_book_creator.text(),
            contributor=self._le_book_contrib.text(),
            date=self._le_book_date.text(),
            description=self._le_book_desc.text(),
        )
        cover_path = self._epub_cover_path
        out_txt = self._le_out_txt.text() or ''

        def _write(progress, status):
            status('正在写入 EPUB 元信息…')
            if cover_path:
                with open(cover_path, 'rb') as f:
                    info.cover = f.read()
            reader = Epub2Txt(epub_path, out_txt)
            reader.modi(info)

        def _after():
            self.statusBar().showMessage('元信息保存完成')
            logger.info(f'元信息已更新: {epub_path}')

        self._run_worker(target=_write, on_success=_after,
                         fail_msg='保存失败', show_progress=False)
```

- [ ] **Step 5: `_on_extract_images` 改为 worker 提取**

方法体（EPUB 存在性校验、`out_dir` 计算之后）替换为：

```python
        box: dict = {}

        def _extract(progress, status):
            status('正在提取图片…')
            reader = Epub2Txt(epub_path, '')
            box['files'] = reader.extract_images(out_dir)

        def _after():
            files = box['files']
            if files:
                msg = f'成功提取 {len(files)} 张图片到:\n{out_dir}'
                logger.info(msg)
                if QMessageBox.question(
                    self, '提取完成', msg + '\n打开目录？',
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                ) == QMessageBox.StandardButton.Yes:
                    self._open_dir(out_dir)
            else:
                QMessageBox.information(self, '提取完成', '未找到图片')
                logger.info('提取图片: 未找到图片')

        self._run_worker(target=_extract, on_success=_after,
                         fail_msg='提取失败', show_progress=False)
```

- [ ] **Step 6: `_load_mobi_metadata` 改为 worker 读取**

将整个方法替换为：

```python
    def _load_mobi_metadata(self, mobi_path: str):
        """加载 MOBI 书籍信息（元数据与封面提取在后台线程执行）。"""
        if self._is_busy():
            return
        from services import extract_mobi_metadata, extract_mobi_cover

        box: dict = {}

        def _read(progress, status):
            status('正在读取 MOBI 信息…')
            md = extract_mobi_metadata(Path(mobi_path))
            box['md'] = md
            offset = md.get('cover_offset')
            box['cover'] = (
                extract_mobi_cover(Path(mobi_path), offset)
                if offset is not None else None
            )

        def _fill():
            metadata = box['md']
            self._mobi_book_title.setText(metadata.get('title', ''))
            self._mobi_book_author.setText(metadata.get('creator', ''))
            self._mobi_book_publisher.setText(metadata.get('publisher', ''))
            self._mobi_book_isbn.setText(metadata.get('isbn', ''))
            self._mobi_book_language.setText(metadata.get('language', ''))
            self._mobi_book_published.setText(metadata.get('published', ''))

            cover_data = box['cover']
            if cover_data:
                pixmap = QPixmap()
                if pixmap.loadFromData(cover_data):
                    self._mobi_lbl_cover.setPixmap(pixmap.scaled(
                        120, 160, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
                else:
                    self._mobi_lbl_cover.setText('封面加载失败')
            else:
                self._mobi_lbl_cover.setText('无封面')

        self._run_worker(target=_read, on_success=_fill,
                         fail_msg='读取 MOBI 失败', show_progress=False)
```

- [ ] **Step 7: 验证**

Run: `python -m pytest tests/ -v`（回归）
Run: `python main.py`（手动：浏览大 EPUB 时界面不再冻结；三个 Tab 各转换一次成功；MOBI 加载失败时弹"读取 MOBI 失败: …"）

- [ ] **Step 8: 提交**

```bash
git add -A && git commit -m "move EPUB and MOBI file IO off the main thread"
```

---

### Task 13: services 防御性修复批（P1）

**背景:** (a) `_process_document` 严格 utf-8 解码，非 UTF-8 片段整个转换崩溃；(b) `extract_images` 同名图片相互覆盖、计数虚高；(c) `_save_cover_if_exists` 中 `item.id` 为 None 抛 TypeError；(d) MOBI 的 .htm 全排在 .html 之后章节错乱；(e) `extract_mobi_metadata` 吞错导致 UI 静默空字段；(f) `modi()` 原地覆盖无备份，中途失败损坏唯一副本。

**Files:**
- Modify: `services.py`（6 处）
- Create: `tests/test_services_hardening.py`

- [ ] **Step 1: 写失败测试**

```python
# -*- coding: utf-8 -*-
"""services 防御性行为测试。"""
import os

from services import Epub2Txt


def test_process_document_tolerates_invalid_utf8(make_epub, tmp_path):
    """非 UTF-8 字节不应导致 UnicodeDecodeError。"""
    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))

    class StubItem:
        def get_content(self):
            return b'<p>caf\xe9</p>'

    text = conv._process_document(StubItem(), False)
    assert 'caf' in text


def test_extract_images_dedupes_names(make_epub, tmp_path):
    """不同子目录的同名图片不能互相覆盖。"""
    epub_path = make_epub(images=['images/a.png', 'pics/a.png'])
    conv = Epub2Txt(epub_path, str(tmp_path / 'o.txt'))
    files = conv.extract_images(str(tmp_path / 'imgs'))
    assert sorted(files) == ['a.png', 'a_2.png']
    assert (tmp_path / 'imgs' / 'a.png').exists()
    assert (tmp_path / 'imgs' / 'a_2.png').exists()


def test_modi_writes_atomically(make_epub, tmp_path):
    """modi 写新文件成功且不残留 .tmp。"""
    from models import BookInfo
    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))
    target = str(tmp_path / 'new.epub')
    conv.modi(BookInfo(title='新标题'), filepath=target)
    assert os.path.exists(target)
    assert not os.path.exists(target + '.tmp')
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_services_hardening.py -v`
Expected: `test_process_document_tolerates_invalid_utf8` FAIL（UnicodeDecodeError）；其余两个 PASS（回归保护）

- [ ] **Step 3: 容错解码**

将：

```python
        soup = BeautifulSoup(item.get_content().decode('utf-8'), 'html.parser')
```

改为：

```python
        # EPUB 规范要求 XHTML 为 UTF-8，但存在不规范文件；
        # 解码失败用替换字符兜底，不让单个文档毁掉整次转换
        soup = BeautifulSoup(
            item.get_content().decode('utf-8', errors='replace'),
            'html.parser',
        )
```

- [ ] **Step 4: extract_images 同名去重**

将：

```python
        os.makedirs(output_dir, exist_ok=True)
        extracted = []
        for item in self._book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                name = os.path.basename(item.get_name())
                out = os.path.join(output_dir, name)
                with open(out, 'wb') as f:
                    f.write(item.get_content())
                extracted.append(name)
        return extracted
```

改为：

```python
        os.makedirs(output_dir, exist_ok=True)
        extracted = []
        used: set[str] = set()
        for item in self._book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                name = os.path.basename(item.get_name())
                stem, ext = os.path.splitext(name)
                candidate = name
                n = 2
                # 不同子目录可能有同名图片，加序号防止相互覆盖
                while candidate in used:
                    candidate = f'{stem}_{n}{ext}'
                    n += 1
                used.add(candidate)
                out = os.path.join(output_dir, candidate)
                with open(out, 'wb') as f:
                    f.write(item.get_content())
                extracted.append(candidate)
        return extracted
```

- [ ] **Step 5: `_save_cover_if_exists` 的 id None 保护**

将：

```python
            is_cover_name = ('cover' in item.get_name() or 'cover' in item.id)
```

改为：

```python
            is_cover_name = (
                'cover' in item.get_name()
                or 'cover' in str(item.id or '')
            )
```

- [ ] **Step 6: MOBI html/htm 混合排序**

将：

```python
        html_files = sorted(tmpdir.rglob('*.html')) + sorted(tmpdir.rglob('*.htm'))
```

改为：

```python
        # .html 与 .htm 合并后按文件名排序，避免 .htm 全部排到最后
        html_files = sorted(
            list(tmpdir.rglob('*.html')) + list(tmpdir.rglob('*.htm')),
            key=lambda p: p.name,
        )
```

- [ ] **Step 7: extract_mobi_metadata 失败时抛错（不再静默空字段）**

将：

```python
    except Exception as e:
        logger.error(f'提取 MOBI 元数据失败: {e}')
    
    return metadata
```

改为：

```python
    except Exception as e:
        logger.error(f'提取 MOBI 元数据失败: {e}')
        # 不再静默吞错：让 UI 层弹出可读的错误提示
        raise RuntimeError(f'无法读取 MOBI 元数据: {e}') from e

    return metadata
```

- [ ] **Step 8: modi() 原子写回**

将：

```python
        epub.write_epub(filepath or self.epub_path, self._book, {})
```

改为：

```python
        # 先写临时文件再原子替换：
        # write_epub 会先 truncate 目标文件，中途失败（磁盘满/断电）
        # 会留下损坏文件，而这通常是用户的唯一副本
        target = filepath or self.epub_path
        tmp_path = target + '.tmp'
        try:
            epub.write_epub(tmp_path, self._book, {})
            os.replace(tmp_path, target)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise
```

- [ ] **Step 9: 运行确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 10: 提交**

```bash
git add -A && git commit -m "harden services: tolerant decode, image dedupe, atomic modi"
```

---

### Task 14: 接入 error_handler 友好错误提示（P2）

**Files:**
- Modify: `window.py`（import；`_run_worker` 加 `error_code`；`_done` 失败分支；`_on_preview_chapters`；各调用点补错误码）

- [ ] **Step 1: import**

`window.py` 头部 import 区新增：

```python
from error_handler import show_error
```

- [ ] **Step 2: `_run_worker` 签名加 error_code**

```python
    def _run_worker(self, target, success_msg: str = '', dir_to_open: str = '',
                    on_success=None, fail_msg: str = '转换失败',
                    error_code: str = 'conversion_failed',
                    show_progress: bool = True):
```

docstring 的 Args 加一行：

```python
            error_code: error_handler.ERROR_MESSAGES 中的错误码
```

- [ ] **Step 3: `_done` 失败分支换用 show_error**

将：

```python
            else:
                QMessageBox.critical(self, '错误', f'{fail_msg}:\n{err}')
                self.statusBar().showMessage(fail_msg)
```

改为：

```python
            else:
                show_error(self, '错误', error_code, err)
                self.statusBar().showMessage(fail_msg)
```

- [ ] **Step 4: 各调用点补错误码**

- `_load_epub_file`：`self._run_worker(...)` 调用加 `error_code='epub_read_failed'`
- `_on_save_metadata`：加 `error_code='epub_write_failed'`
- `_on_extract_images`：加 `error_code='epub_read_failed'`
- `_load_mobi_metadata`：加 `error_code='mobi_read_failed'`
- 其余转换调用点（tab1/tab2/tab3 转换）用默认 `'conversion_failed'`，不改

- [ ] **Step 5: `_on_preview_chapters` 异常分支换用 show_error**

将：

```python
        except Exception as e:
            QMessageBox.critical(self, '错误', f'解析目录失败:\n{e}')
            logger.exception('目录预览失败')
```

改为：

```python
        except ValueError as e:
            show_error(self, '错误', 'regex_invalid', str(e))
            logger.exception('目录预览失败')
        except Exception as e:
            show_error(self, '错误', 'conversion_failed', str(e))
            logger.exception('目录预览失败')
```

- [ ] **Step 6: 验证**

Run: `python -m pytest tests/ -v`
Run: `python -c "import window"`（import 正常）
Run: `python main.py`（手动：构造一个错误触发弹窗，文案为 error_handler 友好提示 + 详细信息）

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "use error_handler friendly messages for error dialogs"
```

### Task 15: 死代码清理 + 重复常量合并（P2）

**Files:**
- Modify: `constants.py`（新增 `DEFAULT_CHAPTER_REGEX`、`STYLES_DIR`）
- Modify: `services.py`（`CSS_STYLE` 读文件；删除重复 `import shutil`）
- Modify: `theme_manager.py`（删 `get_theme_icon`）
- Modify: `window.py`（合并重复 `Theme` 导入；`_run_epub_to_txt` 样式选择改用 STYLES_DIR）

- [ ] **Step 1: constants.py 新增**

```python
# ---------------------------------------------------------------------------
# 章节解析默认正则
# ---------------------------------------------------------------------------
DEFAULT_CHAPTER_REGEX = REGEX_PRESETS['中文标准（第X章）']

# ---------------------------------------------------------------------------
# 样式目录
# ---------------------------------------------------------------------------
STYLES_DIR = os.path.join(BASE_DIR, 'styles')
```

（`os` 已 import。）

- [ ] **Step 2: services.py CSS_STYLE 从文件读取 + 删除重复 import**

将文件头部 `import shutil` 的重复行删除（只保留一处）。将模块级：

```python
CSS_STYLE = """...（约 60 行）..."""
```

整个字符串替换为（CSS_STYLE 定义处，需先确认 constants.py 已 import 进 services）：

```python
def _load_default_css() -> str:
    """读取内置默认 EPUB 样式（styles/default.css）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'styles', 'default.css')
    with open(path, encoding='utf-8') as f:
        return f.read()


CSS_STYLE = _load_default_css()
```

注意：`services.py` 目前是否 import constants 需先查看；若未 import，可直接用 `os.path.dirname(__file__)` 方案（如上），避免改动其它引用。**修改前先 `read services.py` 确认 CSS_STYLE 无其它字面量引用（grep `CSS_STYLE`）。**

- [ ] **Step 3: theme_manager.py 删除未使用的 get_theme_icon**

grep 确认 `get_theme_icon` 全库无调用后，删除该方法及其上方注释。

- [ ] **Step 4: window.py 合并重复 Theme 导入**

grep `from theme_manager import` 确认重复行后，合并为一行：

```python
from theme_manager import theme_manager, Theme
```

（以实际内容为准，保留被使用的符号。）

- [ ] **Step 5: 运行验证**

Run: `python -m pytest tests/ -v`
Run: `python -c "import services, window, theme_manager"`
Run: `python main.py`（确认默认样式与主题切换正常）

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "remove dead code and consolidate duplicated constants"
```

---

### Task 16: QSS 选择器修复（P2）

**背景:** `resources/theme.qss` 与 `theme_manager.py` 深色主题里 4 处 `QLabel#cover_label` —— 合法的 id 选择器不需要类型前缀，但当前控件若 objectName 匹配则生效；实际问题是样式写了却未命中（需先 grep 确认控件 objectName 与选择器对应关系）。另有深色主题缺少 `QMainWindow[dragging="true"]` 拖放高亮。

**Files:**
- Modify: `resources/theme.qss`（2 处）
- Modify: `theme_manager.py`（DARK_THEME 2 处 + 补拖放样式）
- Modify: `window.py`（确认 `_cover_label`/`lblCover` 等 objectName 设置正确）

- [ ] **Step 1: grep 现状**

```
grep -n "cover_label" resources/theme.qss theme_manager.py window.py
grep -n "dragging" resources/theme.qss theme_manager.py window.py
grep -n "setObjectName" window.py | grep -i cover
```

按实际结果对齐：选择器与 objectName 必须一致（`#cover_label` 匹配 `setObjectName("cover_label")`）。**先读再改，不猜。**

- [ ] **Step 2: 修正选择器**

`resources/theme.qss` 两处、`theme_manager.py` DARK_THEME 两处：`QLabel#cover_label` → `#cover_label`（或对齐实际 objectName）。

- [ ] **Step 3: DARK_THEME 补拖放高亮**

DARK_THEME 字符串中追加：

```css
QMainWindow[dragging="true"] { background:#1E3A5F; border:2px dashed #4A9EFF; }
```

确认 `window.py` 拖放逻辑确实 setProperty("dragging", ...)（grep `dragging`）；若属性名不同，用实际属性名。

- [ ] **Step 4: 验证**

Run: `python main.py`（深/浅主题切换，封面占位样式与拖放高亮可见）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "fix cover label QSS selectors and dark theme drag highlight"
```

---

### Task 17: 重置补齐 / 输出路径保护 / Yes-No 按钮（P2）

**Files:**
- Modify: `window.py`

- [ ] **Step 1: grep 检查 `_reset_*` 方法字段覆盖**

`grep -n "_reset" window.py`，对照各 Tab 的输入控件清单，找出 reset 时遗漏的控件（如 EPUB 页的元数据输入框、MOBI 页字段、输出编码下拉等）。每个遗漏控件补一行重置代码。

- [ ] **Step 2: 输出路径保护**

`_on_convert_tab1` 中：目标文件已存在时（且非临时测试场景），QMessageBox 覆盖确认；输出路径为空/目录不存在时报错返回。同理检查 tab2/tab3 的输出路径校验。**先读三个 convert 方法再改。**

- [ ] **Step 3: Yes-No 按钮**

grep `QMessageBox.question` 与 `QMessageBox.StandardButton.Yes`：确认所有确认弹窗用 `Yes | No`（而非默认 OK/Cancel 语义错配）。特别注意 `_ask_open_dir` 与 `_on_extract_images`。

- [ ] **Step 4: 验证**

Run: `python -m pytest tests/ -v`
Run: `python main.py`（手动走 reset / 覆盖确认路径）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "complete field resets, protect output paths, fix dialog buttons"
```

---

### Task 18: 配置存语义编码值（P2）

**背景:** `AppConfig.txt_encoding` 存 ComboBox 序号（0/1/2…），下拉增删选项时序号错位 → 恢复出错误编码。

**Files:**
- Modify: `models.py`（`txt_encoding: str = '自动检测'`；load 兼容旧 int）
- Modify: `window.py`（`_save_config` 存 currentText；`_restore_config` 兼容 int）

- [ ] **Step 1: models.py**

`txt_encoding` 默认值改 `str = '自动检测'`；`AppConfig.load()` 中删除 `str(int(x)) → int` 的旧迁移逻辑（grep `txt_encoding` 确认），改为：

```python
# 兼容旧版本存的序号：转换成当前下拉的显示文本由 window 层处理
```

（若 load 中有 `txt_encoding = str(...)` 保留字符串化即可。）

- [ ] **Step 2: window.py `_save_config`**

```python
cfg.txt_encoding = self._cb_encode.currentText()
```

- [ ] **Step 3: window.py `_restore_config` 兼容旧序号**

```python
raw = cfg.txt_encoding
if isinstance(raw, int) or (isinstance(raw, str) and raw.isdigit()):
    # 旧版本存的是 ComboBox 序号，转换成显示文本
    idx = int(raw)
    text = self._cb_encode.itemText(idx) if 0 <= idx < self._cb_encode.count() else '自动检测'
else:
    text = raw or '自动检测'
self._cb_encode.setCurrentIndex(max(self._cb_encode.findText(text), 0))
```

- [ ] **Step 4: 验证**

Run: `python -m pytest tests/ -v`
Run: `python main.py`（改编码 → 重启 → 编码仍是所选项；用旧 config.json 启动一次确认兼容）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "store semantic encoding value instead of combo index"
```

### Task 19: 拆分 window.py 为 Tab 模块（P3）

**背景:** `window.py` 约 1750 行，单文件混杂三个 Tab 的 UI 构建 + MainWindow 宿主逻辑。拆分为 5 个新文件，MainWindow 保留 worker 管理、快捷键、拖放、主题、配置持久化。

**Files:**
- Create: `utils.py`、`tab_base.py`、`tab_txt2epub.py`、`tab_epub2txt.py`、`tab_mobi2txt.py`
- Modify: `window.py`（删除迁出代码，改用组合）
- Modify: `AGENTS.md`（项目结构表，Task 22 统一做，此处先记）

**拆分原则:**
1. 每个 Tab 一个 `QWidget` 子类，`MainWindow` 通过 `self._tab_txt2epub = TabTxt2Epub(...)` 挂载到 `QTabWidget`。
2. 跨层依赖用**注入**：`BaseTab` 构造时接收 `run_worker`、`is_busy`、`save_config`、`parent`，Tab 不 import MainWindow，避免循环依赖。
3. **先跑通再删**：先新建文件并让 window.py import 它们、行为完全一致（测试全绿 + 手动冒烟），确认无回归后才从 window.py 删除原代码。
4. 迁移顺序：utils → tab_base → 三个 Tab（逐个迁，每迁一个跑一次测试 + 提交）。

- [ ] **Step 1: 先建 utils.py（零风险迁移）**

```python
# -*- coding: utf-8 -*-
"""通用工具函数。"""
import os
import subprocess
import sys


def open_dir(path: str) -> bool:
    """在系统文件管理器中打开目录。

    Returns:
        是否成功发起打开
    """
    if not path or not os.path.isdir(path):
        return False
    try:
        if sys.platform == 'win32':
            os.startfile(path)  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return True
    except OSError:
        return False
```

（`open_dir` 的现有实现从 window.py 原样迁移，以实际代码为准。）

- [ ] **Step 2: 建 tab_base.py**

```python
# -*- coding: utf-8 -*-
"""Tab 基类与共享控件。

Tab 通过构造参数拿到 MainWindow 的能力（启动后台任务、
判断忙碌、保存配置），从而不 import window，避免循环依赖。
"""
from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)


class BaseTab(QWidget):
    """三个转换 Tab 的公共基类。"""

    def __init__(
        self,
        run_worker: Callable,
        is_busy: Callable[[], bool],
        save_config: Callable,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.run_worker = run_worker      # MainWindow._run_worker
        self.is_busy = is_busy            # MainWindow._is_busy
        self.save_config = save_config    # MainWindow._save_config

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


class _ClickableLabel(QLabel):
    """可点击的标签（封面占位/预览区）。"""

    def __init__(self, on_click: Callable, text: str = '', parent=None):
        super().__init__(text, parent)
        self._on_click = on_click

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()


class _DropLineEdit(QLineEdit):
    """支持拖放文件的单行输入框。"""

    def __init__(self, on_drop: Callable[[str], None], parent=None):
        super().__init__(parent)
        self._on_drop = on_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):  # noqa: N802
        urls = event.mimeData().urls()
        if urls:
            self._on_drop(urls[0].toLocalFile())
            event.acceptProposedAction()


def _create_file_row(label_text: str, edit: QLineEdit, btn_text: str,
                     on_btn: Callable, on_drop: Callable) -> QWidget:
    """创建 [标签 + 输入框 + 按钮] 一行控件（输入框支持拖放）。"""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(QLabel(label_text))
    drop_edit = _DropLineEdit(on_drop, parent=edit.parent())
    # 保留原 edit 的 objectName 等属性由调用方处理；此函数为可选辅助
    lay.addWidget(edit, 1)
    btn = QPushButton(btn_text)
    btn.clicked.connect(on_btn)
    lay.addWidget(btn)
    return row


def _create_book_info_group(...) -> QFrame:
    """书籍信息组（封面 + 字段 + 按钮）——迁移 window.py 现有实现。"""
    # TODO: 从 window.py `_create_book_info_group` 原样迁移
    raise NotImplementedError


def _status(text: str) -> str:
    """状态栏文本截断辅助（迁移现有实现）。"""
    raise NotImplementedError
```

**注意：** `_create_file_row`/`_create_book_info_group`/`_status` 必须以 `window.py` 中现成实现为准原样迁移（先读 window.py 对应方法），上面只是签名示意。若现有布局代码与控件状态强耦合、无法干净迁出，允许保留私有辅助在各自 Tab 内 —— 以"行为不变"为最高约束。

- [ ] **Step 3: 迁移 TabTxt2Epup（示例流程，其余两个 Tab 同法）**

1. 从 `window.py` 把 `_create_tab_txt2epub`（或等价构建方法）+ 相关私有方法（`_on_convert_tab1`、`_on_reset_tab1`、`_on_choose_cover`、`_load_txt_file` 等）剪切到 `tab_txt2epub.py` 的 `class TabTxt2Epub(BaseTab)`。
2. 控件成员从 `self._le_txt_path`（MainWindow）变成 Tab 自己的 `self._le_txt_path`。
3. 原来直接调 `self._run_worker(...)` 的地方改为 `self.run_worker(...)`；`self._is_busy()` → `self.is_busy()`；`self._save_config()` → `self.save_config()`。
4. 原来访问其它 Tab/状态栏的地方（`self.statusBar()`）：状态栏通过 `self.window().statusBar()` 获取（QWidget.window() 返回顶层窗口），或注入 `show_status` 回调 —— 二选一，以现有调用点数量为准，优先注入回调更干净。
5. `window.py` 中 `_on_shortcut_convert` 改为 `self._tab_txt2epub.convert()`；`_on_shortcut_open`/`_on_shortcut_reset` 同理转发到当前 Tab。
6. MainWindow 的配置持久化 `_save_config`/`_restore_config` 改为遍历三个 Tab 的 `get_config()`/`apply_config()`（或保留 MainWindow 内字段、只迁移 UI 构建 —— 若配置字段过多，**迁移 UI 构建、保留配置逻辑在 MainWindow** 是更安全的最小方案，按实际耦合度决定，不确定时选最小方案并记录）。
7. Run: `python -m pytest tests/ -v` + `python main.py` 手动冒烟（三 Tab 转换、拖放、快捷键、封面选择、重置）。
8. Commit: `git add -A && git commit -m "extract TabTxt2Epub into its own module"`

- [ ] **Step 4: 迁移 TabEpub2Txt（同 Step 3 流程）**

Commit: `git add -A && git commit -m "extract TabEpub2Txt into its own module"`

- [ ] **Step 5: 迁移 TabMobi2Txt（同 Step 3 流程）**

Commit: `git add -A && git commit -m "extract TabMobi2Txt into its own module"`

- [ ] **Step 6: window.py 收尾**

- 删除已迁出的私有方法，MainWindow 只留：`_init_ui`（组装三 Tab）、worker 相关（`_run_worker`/`_is_busy`/`_progress`/`_status`/`_cancel`/`_done`/`_ask_open_dir`）、快捷键、拖放、主题、配置、`closeEvent`。
- grep `window.py` 确认无残留对已删方法的引用。
- Run: `python -m pytest tests/ -v`；`python -c "import window"`；手动全功能冒烟。
- 行数预期：`window.py` 降到 ~900 行以内（记录 `wc -l window.py tab_*.py` 到提交信息）。

- [ ] **Step 7: 提交**

```bash
git add -A && git commit -m "slim down window.py after tab extraction"
```

---

### Task 20: ConvertOptions 参数对象（P3）

**背景:** `Txt2Epub.convert()` 接受 13 个位置/关键字参数，调用方（worker 包装 lambda）逐个透传出错。

**Files:**
- Modify: `models.py`（新增 `ConvertOptions` dataclass）
- Modify: `services.py`（`Txt2Epub.configure(opts)`）
- Modify: `window.py`（构造 dataclass + `configure()`）
- Create: `tests/test_convert_options.py`

- [ ] **Step 1: models.py 新增**

```python
from dataclasses import dataclass, field, asdict


@dataclass
class ConvertOptions:
    """Txt2Epub.convert() 的参数集合。字段名与 dataclass 对齐。"""
    text_path: str = ''
    out_path: str = ''
    title: str = ''
    author: str = ''
    language: str = 'zh'
    publisher: str = ''
    description: str = ''
    cover_path: str = ''
    css_style: str = ''
    encoding: str = 'utf-8'
    separator: str = ''
    regex: str = ''
    fanjian: bool = False
    chapter_order: list | None = None
```

- [ ] **Step 2: services.py 新增 configure**

```python
    def configure(self, opts) -> None:
        """按 ConvertOptions 批量设置属性。

        空字符串/None 视为"未指定"，跳过不覆盖现有值；
        chapter_order 为 None 同样跳过（保持当前顺序）。
        """
        for key, value in asdict(opts).items():
            if key == 'chapter_order':
                if value is not None:
                    self._chapter_order = value
                continue
            if value == '' or value is None:
                continue
            if not hasattr(self, key):
                raise AttributeError(f'Txt2Epub 没有属性 {key}')
            setattr(self, key, value)
```

（`from dataclasses import asdict` 加入 services.py import；注意映射 `opts.text_path → self.text_path` 等字段名必须与 Txt2Epub.__init__ 实际属性一一对应 —— **先读 __init__ 确认字段名**，不一致的用显式映射 dict `{...}` 替代 asdict 直写。）

- [ ] **Step 3: 写测试**

```python
# -*- coding: utf-8 -*-
"""ConvertOptions 配置测试。"""
from models import ConvertOptions
from services import Txt2Epub


def test_configure_sets_fields(sample_txt):
    conv = Txt2Epub(sample_txt, 'out.epub')
    opts = ConvertOptions(title='新标题', author='张三', encoding='gbk')
    conv.configure(opts)
    assert conv.title == '新标题'
    assert conv.author == '张三'
    assert conv.encoding == 'gbk'


def test_configure_skips_empty(sample_txt):
    conv = Txt2Epub(sample_txt, 'out.epub')
    conv.title = '原标题'
    conv.configure(ConvertOptions())   # 全默认 → 不覆盖
    assert conv.title == '原标题'


def test_configure_unknown_field_raises(sample_txt):
    import pytest
    conv = Txt2Epub(sample_txt, 'out.epub')
    with pytest.raises(AttributeError):
        conv.configure(NotSet := type('O', (), {'__dict__': {'no_such': 1}})())
```

（第三个测试按 configure 实际实现调整触发方式，核心是"未知字段要响亮报错"。）

- [ ] **Step 4: window.py `_on_convert_tab1` 改用 configure**

把逐行 `conv.title = ...` 赋值替换为构造 `ConvertOptions(...)` + `conv.configure(opts)`；`conv.set_chapter_order(...)` 若已并入 opts.chapter_order 则删除单独调用（否则保留）。

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/ -v`

- [ ] **Step 6: 提交**

```bash
git add -A && git commit -m "add ConvertOptions for Txt2Epub configuration"
```

### Task 21: ruff 配置与 lint 清零（P3）

**Files:**
- Create: `ruff.toml`
- Modify: 需要的源文件（只修真实问题，不为凑数改代码）

- [ ] **Step 1: 创建 ruff.toml**

```toml
# 保守配置：只开 pycodestyle 错误级 + pyflakes，
# 不启用格式化/风格规则，避免与现有代码风格冲突
line-length = 100
target-version = "py312"

[lint]
select = ["E4", "E7", "E9", "F"]
ignore = []

[lint.per-file-ignores]
"tests/*" = ["E402"]
```

- [ ] **Step 2: 首次运行并记录**

Run: `python -m ruff check .`
Expected: 输出未使用 import（F401）、未使用变量（F841）等真实问题清单。

- [ ] **Step 3: 逐个修复（或确认误报后加行内 noqa）**

原则：
- 未使用 import → 删（确认无副作用）。
- 未使用变量 → 删或改 `_` 占位。
- 不为过 lint 引入行为变更；拿不准的保留代码加 `# noqa: Fxxx` 并在提交信息注明。

- [ ] **Step 4: 清零确认**

Run: `python -m ruff check .` → `All checks passed!`
Run: `python -m pytest tests/ -v` → 全绿

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "add ruff config and fix lint findings"
```

---

### Task 22: 文档同步（P3）

**Files:**
- Modify: `AGENTS.md`（项目结构表 + 运行方式 + 代码约定）
- Modify: `README.md`（如有"无测试"表述）
- Modify: `requirements.txt`（如需运行时依赖确认；dev 依赖已在 requirements-dev.txt）

- [ ] **Step 1: AGENTS.md 更新**

- 项目结构表：新增 `tab_base.py` / `tab_txt2epub.py` / `tab_epub2txt.py` / `tab_mobi2txt.py` / `utils.py` / `tests/` / `ruff.toml` / `requirements-dev.txt` 行。
- 删除"无测试、无 linting"注意事项，改为：

```
## 测试与 Lint

```bash
python -m pytest tests/ -v    # 单元测试
python -m ruff check .        # 静态检查
pip install -r requirements-dev.txt   # 开发依赖
```
```

- 架构要点补一行："Tab 子类通过 `BaseTab(run_worker, is_busy, save_config)` 注入 MainWindow 能力，不反向 import window"。

- [ ] **Step 2: README.md 同步**

grep `无测试|无 lint|无 CI`，按实际表述修正；补"开发"小节（pytest/ruff）。

- [ ] **Step 3: 提交**

```bash
git add -A && git commit -m "update docs for new module layout and tooling"
```

---

### Task 23: 全量验证

- [ ] **Step 1: 单元测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **Step 2: 静态检查**

Run: `python -m ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: import 完整性**

Run: `python -c "import window, services, worker, models, dialogs, constants, error_handler, theme_manager, utils, tab_base, tab_txt2epub, tab_epub2txt, tab_mobi2txt"`
Expected: 无异常

- [ ] **Step 4: 手动冒烟清单（python main.py）**

| # | 操作 | 预期 |
|---|------|------|
| 1 | TXT→EPUB（自动检测编码，GBK 文件） | 中文不乱码，进度到 100% |
| 2 | 四种章节分隔符各导出一次 EPUB→TXT | 四个文件内容互不相同 |
| 3 | 无封面 TXT 转 EPUB 后检查 | 可被阅读器打开（spine 合法） |
| 4 | 目录预览里重命名 + 拖拽排序 → 转换 | 新标题生效、顺序正确、不丢章 |
| 5 | 自定义正则写成 0 个捕获组 | 启动转换前弹"捕获组"提示 |
| 6 | 转换中按 Ctrl+Enter | 状态栏提示"进行中"，不重复启动 |
| 7 | 转换中点取消 | 状态栏"已取消"，不弹完成窗 |
| 8 | 转换中关窗口 | 正常退出，无 "QThread destroyed" |
| 9 | 浏览大 EPUB 元数据 | 界面不冻结 |
| 10 | 字体/目录样式选非默认样式文件 | EPUB 样式中字体与列表标记生效 |
| 11 | 改配置（编码/主题）→ 重启 | 配置保持 |
| 12 | 深/浅主题切换 + 拖放文件 | 封面样式/拖放高亮正常 |

- [ ] **Step 5: 提交收尾**

```bash
git add -A && git commit -m "chore: final verification pass"
```

---

## 设计决策记录

| 决策 | 选择 | 备选 | 理由 |
|------|------|------|------|
| 分隔符语义 | services 端 `if self.sep: text += self.sep` | window 端去掉 `\n` 前缀 | 最小改动；window 已做替换，服务端信任传入值 |
| 样式覆盖 | CSS 末尾追加覆盖规则 | 解析/替换具体声明 | 层叠规则天然支持，对 3 个样式文件通用 |
| 章节排序标识 | 原始索引 (UserRole) | 唯一 UUID 标记 | 零存储成本，排序/重命名天然稳定 |
| 取消信号 | `task_done(ok, err, cancelled)` 三态 | 独立 `cancelled` 信号 | 一处连接处理全部终态，UI 逻辑集中 |
| IO 移线程 | 预采集 UI 值 + worker 内建 reader | reader 缓存跨线程 | 消除跨线程访问 QWidget 风险 |
| modi 写回 | `.tmp` + `os.replace` 原子替换 | 备份副本 | 无残留、Windows 下 os.replace 原子 |
| Tab 解耦 | 构造参数注入 4 个回调 | Tab 信号 → MainWindow | 无新增信号样板，循环 import 天然避免 |
| 配置字段迁移 | **视耦合度取最小方案**（优先只迁 UI 构建，配置留 MainWindow） | 全部随 Tab 迁移 | 行为不变优先，避免一次性大爆炸 |
| ruff 规则 | 仅 E4/E7/E9/F | 全面规则集 | 保守起步，不制造风格噪音 |

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| Task 19 拆分导致 UI 行为回归 | 每迁一个 Tab 独立提交 + 手动冒烟；迁移顺序按耦合度从低到高 |
| chardet 检测误判编码 | 用户仍可手动选编码覆盖；检测值仅在"自动检测"时使用 |
| ebooklib 覆盖内部行为（spine/toc 修改） | 测试断言直接读 opf/nav 字节，锁定实际产物 |
| 旧 config.json 序号兼容 | restore 兼容 int/数字串分支，Task 18 测试覆盖 |
| worker 内异常栈信息丢失 | `logger.exception` 已记录；弹窗用 error_handler 显示可读文案 |

## 验证（每任务完成后）

```bash
python -m pytest tests/ -v      # Task 1 建立后始终全绿
python -m ruff check .          # Task 21 后清零
git log --oneline               # 每任务一条英文提交
```

## 完成定义

- 23 个任务全部勾选，pytest 全绿，ruff 清零。
- Task 23 手动冒烟 12 项全部通过。
- `window.py` 显著瘦身（<900 行），新增 5 个模块可独立 import。
- AGENTS.md / README 与实际结构一致。

