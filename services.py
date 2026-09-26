# -*- coding: utf-8 -*-
"""
TxtPress — 核心业务层，TXT ↔ EPUB ↔ MOBI 格式转换。

这个文件是程序的"大脑"——所有文件格式转换的实际逻辑都在这里。
每个类/函数只做一件事，方便测试和复用。

类：
  - Txt2Epub      TXT → EPUB（含章节拆分、封面、CSS）
  - Epub2Txt      EPUB → TXT（合并 / 按章节 / 元信息 / 封面 / 图片提取）
  - Epub2Mobi     EPUB → MOBI（框架接口，需外部工具）

函数：
  - convert_mobi_to_txt()      MOBI → TXT（基于 mobi 库）

设计原则：
  - 所有转换方法接受可选的 progress 和 status 回调，
    这样 UI 层可以通过 worker.py 实时更新进度条和状态栏。
  - 不依赖 PyQt，理论上可以直接用命令行调用。
  - 每个转换器一次只做一个方向的转换（单向设计，降低复杂度）。
"""

from __future__ import annotations

import html
import os
import re
import uuid
import datetime
import shutil
from pathlib import Path
from typing import Callable, Optional

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from loguru import logger
from opencc import OpenCC

from models import BookInfo
from constants import (
    DEFAULT_COVER, DEFAULT_AUTHOR, DEFAULT_DESC, DEFAULT_ID
)


# =====================================================================
# 常量
# =====================================================================

# 用于过滤过短的序言文本（少于这个字符数就不生成单独的序章章节）
_MIN_PREAMBLE_LEN = 5

# 文件名最大长度限制（避免某些文件系统路径过长的问题）
_MAX_FILENAME_LEN = 50

# 进度状态栏中显示的章节标题最大长度（截断显示，保持状态栏简洁）
_STATUS_TITLE_LEN = 20

# 匹配中文章节标题的正则表达式
# 匹配"第一章"、"第十二章"、"第二百三十章"、"卷三"、"上回"等
# 正则拆解：
#   ^\s*          行首 + 任意空白
#   [第卷]         以"第"或"卷"开头
#   [0123456789一二三四五六七八九十零〇百千两]*  零个或多个数字/中文数字
#   [章回部节集卷]  结尾的章节单位词
#   .*            标题剩余内容
#   \s*           结尾空白
DEFAULT_CHAPTER_REGEX = (
    r'^\s*([第卷][0123456789一二三四五六七八九十零〇百千两]*[章回部节集卷].*)\s*'
)

# EPUB 内嵌的 CSS 样式
# 控制正文、标题、目录页的显示效果，阅读器（如 Kindle）会按此渲染
# 注意：
#   - @namespace 是 EPUB 3 必需的，声明 epub 前缀用于目录页选择器
#   - widows/orphans 控制段落分页时保留最少行数（提升阅读体验）
#   - nav[epub|type~='toc'] 选择器匹配 EPUB 3 的目录页
CSS_STYLE = '''
@namespace epub "http://www.idpf.org/2007/ops";
body {
    font-family: Cambria, "Liberation Serif", Georgia, "Times New Roman", serif;
}
h1 {
    text-align: left; text-indent: 2em;
    font-family: "Microsoft YaHei", sans-serif;
    font-weight: bold; color: #D2691E; line-height: 300%;
    margin: 30px 0 0 0;
}
h2 {
    text-align: left; text-indent: 2em;
    font-family: "Microsoft YaHei", sans-serif;
    font-weight: bold; color: #D2691E; line-height: 240%;
    margin: 20px 0 0 0;
}
p {
    text-indent: 1.25em; margin: 0; widows: 2; orphans: 2;
}
ol { list-style-type: none; }
ol > li:first-child { margin-top: 0.3em; }
nav[epub|type~='toc'] > ol > li > ol { list-style-type: square; }
nav[epub|type~='toc'] > ol > li > ol > li { margin-top: 0.3em; }
'''


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
            f'当前有 {compiled.groups} 个: {pattern}\n'
            f'提示：请把要作为章节标题的部分用半角括号 () 包起来'
        )
    return compiled


# =====================================================================
# Txt2Epub — TXT → EPUB
# =====================================================================

class Txt2Epub:
    """
    TXT 文本 → EPUB 电子书转换器。

    用法：
        1. 创建实例，传入 TXT 和 EPUB 路径
        2. 根据需要修改属性（title, author, cover_path 等）
        3. 调用 convert() 开始转换
        4. 可选传入 progress/status 回调跟踪进度

    章节拆分逻辑：
        - 用正则匹配章节标题（如"第一章"、"第十二章"）
        - 按标题位置把文本切成多个段落
        - 每个段落生成一个 EPUB 章节（.xhtml 文件）
        - 最开头的无标题文本作为"序章"

    re.split 配合捕获组（正则中的括号）的妙用：
        re.split(r'(第...章)', text) 返回的列表是：
        [前文, "第一章", 第一章正文, "第二章", 第二章正文, ...]
        这样标题和正文交替出现，天然配对，非常方便。
    """

    def __init__(self, txt_path: str, epub_path: str):
        """
        Args:
            txt_path:  源 TXT 文件路径
            epub_path: 输出的 EPUB 文件路径
        """
        self.txt_path = txt_path
        self.epub_path = epub_path
        # ---- 以下属性可在 convert() 前修改 ----
        self.title = 'epub'                                       # 书名（默认用文件名）
        self.author = DEFAULT_AUTHOR                             # 作者
        self.language = 'cn'                                      # 语言
        self.id_epub = DEFAULT_ID                                # EPUB 唯一 ID
        self.cover_path = DEFAULT_COVER                          # 封面图片路径
        self.encoding = 'utf-8'                                   # TXT 文件编码
        self.regex = DEFAULT_CHAPTER_REGEX                        # 章节匹配正则
        self.description = ''                                     # EPUB 描述
        self.contributor = ''                                     # 贡献者
        self.date = ''                                            # 日期
        self.css_style = CSS_STYLE                                # EPUB CSS样式
        # ---- 内部状态 ----
        self._splits: Optional[list[str]] = None                  # 解析后的章节片段缓存
        self._cached_path: str = ''                               # 上次解析时的文件路径（用于缓存失效）
        self._cached_encoding: str = ''                           # 上次解析时的编码（用于缓存失效）
        self._cached_regex: str = ''                              # 上次解析时的正则（用于缓存失效）
        self._chapter_order: Optional[list[tuple[int, str]]] = None   # 自定义章节顺序 [(原始索引, 新标题)]

    def load_css_from_file(self, css_path: str):
        """从文件加载自定义CSS样式"""
        if os.path.exists(css_path):
            with open(css_path, 'r', encoding='utf-8') as f:
                self.css_style = f.read()

    def apply_text_style(self, font_family: str, toc_marker: str) -> None:
        """在 CSS 末尾追加正文字体与目录样式的覆盖规则。

        为什么用追加而不是字符串替换？
        default/minimal/modern 三个样式文件的 font-family 和
        list-style-type 写法各不相同，定向 replace 会静默失效。
        CSS 层叠规则：同优先级下后写的规则生效，追加即可全局覆盖。

        幂等：覆盖块以 /* TxtPress override */ 标记开头，每次先删除
        旧标记块再追加，重复调用不会堆叠重复规则。
        """
        # 先删除旧的覆盖块（从标记注释到字符串末尾），保证幂等
        marker = '/* TxtPress override */'
        idx = self.css_style.find(marker)
        if idx != -1:
            self.css_style = self.css_style[:idx].rstrip() + '\n'
        overrides = []
        if font_family:
            overrides.append(f'body {{ font-family: {font_family}; }}')
        if toc_marker:
            # 用后代选择器而非 > ol > li > ol：产物 nav.xhtml 的 TOC 是
            # 扁平 <nav><ol><li><a>（无嵌套），子代选择器匹配 0 个元素；
            # 后代选择器特异性 (0,1,2) 高于 default.css 的 ol { none }
            overrides.append(
                "nav[epub|type~='toc'] ol { "
                f'list-style-type: {toc_marker}; }}'
            )
        if overrides:
            self.css_style = (
                self.css_style.rstrip() + '\n\n' + marker + '\n'
                + '\n'.join(overrides) + '\n'
            )

    def set_chapter_order(self, ordered: list[tuple[int, str]] | None) -> None:
        """设置自定义章节顺序：[(原始索引, 新标题), ...]。

        用索引而不是标题匹配：重命名后的标题查不到原章，
        重复标题也会互相覆盖。传 None 表示按原始文件顺序。
        只影响 convert() 的输出顺序，对 get_chapters() 无效
        （get_chapters 始终返回原始顺序）。"""
        self._chapter_order = ordered

    def _parse(self):
        """
        读取 TXT 文件，按正则拆分章节。

        拆分结果存到 self._splits，格式是：
        [ 序章文本, 标题1, 正文1, 标题2, 正文2, ... ]

        有缓存，但 encoding 或 regex 变化时会重新解析。

        缓存设计说明：
        因为 get_chapters() 和 convert() 都会调用 _parse()，
        而 convert() 在后台线程执行，get_chapters() 在主线程执行，
        缓存可以避免重复读取大文件。

        注意：
          - 当用户改了编码、正则或文件路径后，缓存自动失效
        """
        cache_valid = (
            self._splits is not None
            and self._cached_path == self.txt_path
            and self._cached_encoding == self.encoding
            and self._cached_regex == self.regex
        )
        if cache_valid:
            return
        # 先校验正则（能编译且恰好 1 个捕获组），无效就不必读文件了
        compiled = validate_chapter_regex(self.regex)
        # 记录当前参数，下次调用时判断缓存是否仍然有效
        self._cached_path = self.txt_path
        self._cached_encoding = self.encoding
        self._cached_regex = self.regex
        with open(self.txt_path, 'r', encoding=self.encoding, errors='replace') as f:
            content = f.read()
            # re.split 用正则切割文本，如果正则带有捕获组（括号），
            # 捕获的内容也会被包含在结果列表中。
            # 这就是为什么结果交替出现 文本 / 标题 / 文本 / 标题 ...
            # re.M（MULTILINE）让 ^ 匹配每行开头，而不只是字符串开头。
            self._splits = compiled.split(content)

    def get_chapters(self) -> list[str]:
        """
        返回章节标题列表（用于预览或排序）。

        从 _splits 中每隔一项取出标题：
        indices 1, 3, 5, ... 对应的就是第一、二、三章的标题。

        举例说明：
          如果 _splits = ['前言...', '第一章', '正文1...', '第二章', '正文2...']
          那么 get_chapters() 返回 ['第一章', '第二章']
        """
        self._parse()
        return [self._splits[i] for i in range(1, len(self._splits) - 1, 2)]

    def convert(
        self,
        progress: Optional[Callable[[int, int], None]] = None,
        status: Optional[Callable[[str], None]] = None,
    ) -> None:
        """执行 TXT → EPUB 转换的核心逻辑。"""
        if status:
            status('正在创建 EPUB 书籍…')

        # ---- 创建 EPUB 书籍对象 ----
        # ebooklib 的 EpubBook 是内存中的 EPUB 模型，
        # 所有操作完成后调用 epub.write_epub() 写入磁盘。
        # 这种"先构建再写入"的模式避免了频繁 IO。
        book = epub.EpubBook()

        # ---- 元数据 ----
        # DC（Dublin Core）是 EPUB 元数据的标准命名空间
        # set_identifier / set_title / set_language 是便捷方法
        # add_metadata 用于设置非标准字段
        book.set_identifier(self.id_epub)
        book.set_title(self.title)
        book.set_language(self.language)
        d = self.date or str(datetime.datetime.now())
        book.add_metadata('DC', 'date', d)
        c = self.contributor or DEFAULT_AUTHOR
        book.add_metadata('DC', 'contributor', c)
        desc = self.description or DEFAULT_DESC
        book.add_metadata('DC', 'description', desc)
        book.add_author(self.author)

        # ---- 封面 ----
        # 只有封面真实存在时才注册封面并写入 spine，
        # 否则 spine 会引用不存在的 item，产出结构非法的 EPUB
        has_cover = os.path.exists(self.cover_path)
        if has_cover:
            with open(self.cover_path, 'rb') as f:
                book.set_cover('cover.jpeg', f.read())

        # ---- 导航与样式 ----
        # EpubNcx / EpubNav 是 EPUB 的目录文件（阅读器里点"目录"看到的）
        # NCX 是 EPUB 2 的目录格式，Nav 是 EPUB 3 的格式。
        # ebooklib 两者都添加，保障兼容性。
        book.add_item(epub.EpubNcx())
        nav = epub.EpubNav()
        book.add_item(nav)

        # 把 CSS 样式添加为 EPUB 的一个资源文件
        nav_css = epub.EpubItem(
            uid='style_nav',
            file_name='style/nav.css',
            media_type='text/css',
            content=self.css_style,
        )
        book.add_item(nav_css)
        # 目录页必须挂样式表，否则 nav.css 里的目录样式规则全部无效
        # （ebooklib 只会把 item.links 输出到 nav.xhtml 的 <head>；
        #   nav.xhtml 在 EPUB 根、css 在 style/ 下，相对路径 style/nav.css 成立）
        nav.add_item(nav_css)
        # spine 定义了 EPUB 的阅读顺序；'cover' 是封面页占位符
        book.spine = ['cover'] if has_cover else []

        # ---- 章节解析 ----
        self._parse()
        splits = self._splits

        # 将 splits 按 (标题, 正文) 配对，组成章节列表
        # pairs 是 [(标题1, 正文1), (标题2, 正文2), ...]
        chapters = [(splits[i], splits[i + 1])
                     for i in range(1, len(splits) - 1, 2)]

        # ---- 应用自定义章节顺序 ----
        # 按 (原始索引, 新标题) 重排：索引避免重命名查不到、重复标题覆盖
        if self._chapter_order:
            reordered = []
            used: set[int] = set()
            for idx, new_title in self._chapter_order:
                # isinstance 防御：异常来源的 data() 可能返回 None
                if isinstance(idx, int) and 0 <= idx < len(chapters) and idx not in used:
                    old_title, body = chapters[idx]
                    # 空白新标题回退原标题，避免生成空文件名和空目录链接
                    title = (new_title or '').strip() or old_title
                    reordered.append((title, body))
                    used.add(idx)
            # 未出现在列表中的章节按原序补到末尾（防止丢章）
            for i, pair in enumerate(chapters):
                if i not in used:
                    reordered.append(pair)
            if reordered:
                chapters = reordered

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
            # 加入目录，阅读器里才能看到序章
            book.toc.append(epub.Link('xu.xhtml', '序章', 'intro'))
            if progress and total > 0:
                progress(1, total)

        # 进度偏移：有序章时序章已占第 1 步，章节从第 2 步开始计
        done = 1 if has_preamble else 0

        # ---- 逐章生成 HTML 内容 ----
        used_names = set()  # 用于检测同名冲突（两个章节同名的情况）
        for idx, (title, body) in enumerate(chapters, start=1):
            if status:
                status(f'正在处理第 {idx}/{len(chapters)} 章: {title.strip()[:_STATUS_TITLE_LEN]}…')
            if progress and total > 0:
                progress(done + idx, total)

            body_html = _text_to_html(body)
            # 将标题中的特殊字符替换为下划线，生成合法的文件名
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', title.strip())[:_MAX_FILENAME_LEN]
            # 处理同名冲突：如果两个章节标题相同，加数字后缀区分
            if safe_name in used_names:
                suffix = 2
                while f'{safe_name}_{suffix}' in used_names:
                    suffix += 1
                safe_name = f'{safe_name}_{suffix}'
            used_names.add(safe_name)
            ch = epub.EpubHtml(
                title=title.strip(),
                file_name=f'{safe_name}.xhtml',
                lang='zh',
            )
            ch.content = (
                f'<h2>{html.escape(title.strip(), quote=False)}</h2>{body_html}'
            )
            ch.add_item(nav_css)

            book.add_item(ch)
            book.toc.append(epub.Link(f'{safe_name}.xhtml', title.strip(), 'intro'))
            book.spine.append(ch)

        # ---- 写入磁盘 ----
        # 最后一个参数 {} 是选项字典，这里不传任何额外选项。
        if status:
            status('正在写入 EPUB 文件…')
        epub.write_epub(self.epub_path, book, {})


# =====================================================================
# Epub2Txt — EPUB → TXT
# =====================================================================

class Epub2Txt:
    """
    EPUB 电子书 → TXT 文本文件转换器。

    除了转换外，还提供：
    - get_info()       提取元数据（标题、作者、封面等）
    - get_cover()      提取封面图片二进制
    - extract_images() 提取 EPUB 中所有图片
    - modi()           修改 EPUB 元数据并保存

    转换有两种模式：
    - convert()          合并所有章节为单个 TXT
    - convert_chapter()  每章导出为一个独立的 TXT 文件

    关键设计：
    __init__ 里就调用 epub.read_epub() 把 EPUB 加载到内存，
    之后的所有操作都在内存中的 _book 对象上进行，不重复读取。
    这意味着一旦创建实例，源文件就被锁定了（windows 上不能移动）。
    """

    def __init__(self, epub_path: str, txt_path: str, encoding: str = 'utf-8'):
        """
        Args:
            epub_path: 源 EPUB 文件路径
            txt_path:  输出的 TXT 文件路径（按章节导出时作为模板）
            encoding:  输出 TXT 的编码
        """
        self.epub_path = epub_path
        self.txt_path = txt_path
        self.encoding = encoding
        self.sep = ''                                         # 章节间分隔符
        self._dir = os.path.dirname(txt_path) if txt_path else ''  # 输出目录
        try:
            self._book = epub.read_epub(epub_path)            # 读取 EPUB 到内存
        except Exception as e:
            raise ValueError(f'无法读取 EPUB 文件: {epub_path}') from e
        self._cc_converter = None                             # 繁简转换器（lazy 初始化）

    @property
    def _cc(self):
        """繁体→简体转换器（lazy 初始化）。

        为什么要 lazy？
        OpenCC 初始化需要加载词典，大约耗时 100-200ms。
        如果不是每次都需要繁简转换（大多数用户不用），
        创建实例但不初始化 OpenCC，避免不必要的性能开销。
        当用户真正勾选了繁简转换时，_cc 属性才会触发初始化。
        """
        if self._cc_converter is None:
            self._cc_converter = OpenCC('t2s')
        return self._cc_converter

    # ---- 元信息提取 ----

    def get_info(self) -> BookInfo:
        """提取 EPUB 元数据。

        通过 DC（Dublin Core）命名空间从 EPUB 中提取标准元数据。
        使用循环 + 属性名称映射的方式，比逐字段 try/except 更简洁。

        setattr(info, attr, value) 等价于 info.attr = value，
        但 setattr 允许我们动态指定属性名。
        """
        info = BookInfo()
        dc_fields = [
            ('title', 'title'), ('creator', 'creator'),
            ('contributor', 'contributor'), ('date', 'date'),
            ('description', 'description'),
        ]
        for attr, dc_name in dc_fields:
            try:
                setattr(info, attr,
                        self._book.get_metadata('DC', dc_name)[0][0])
            except Exception:
                # get_metadata 可能因字段不存在而抛异常，
                # 跳过即可，保持默认值。
                logger.debug(f'元数据字段 {dc_name} 不存在或为空')
        return info

    def get_cover(self) -> Optional[bytes]:
        """
        提取封面图片二进制数据。

        不同 EPUB 生成工具把封面放在不同位置：
        1. 用 ID 查找：cover / cover-img / cover-image
        2. 按资源类型查找 ITEM_COVER
        3. 按文件名查找：包含 "cover" 的图片
        三重策略确保各种 EPUB 都能提取到封面。

        为什么有这么多策略？
        EPUB 标准对封面位置没有严格规定，
        有些工具把封面标记为 ITEM_COVER 类型，
        有些只是 ID 叫 "cover" 的普通图片，
        有些甚至把封面放在 ITEM_IMAGE 但文件名含 "cover"。
        多策略覆盖了 Calibre、Sigil、Kindle Previewer 等各种工具的产出。
        """
        cover_types = (ebooklib.ITEM_IMAGE, ebooklib.ITEM_COVER)

        # 策略一：按资源 ID 查找
        for cid in ('cover', 'cover-img', 'cover-image'):
            try:
                item = self._book.get_item_with_id(cid)
                if item.get_type() in cover_types:
                    return item.get_content()
            except Exception:
                logger.debug(f'封面查找策略一失败: ID={cid}')

        # 策略二：按资源类型查找（有些 EPUB 的 covers 在 ITEM_COVER 类型中）
        # 如果有多于 1 个 ITEM_COVER 项，取第二个（第一个通常是元数据占位）
        try:
            items = list(self._book.get_items_of_type(ebooklib.ITEM_COVER))
            if len(items) > 1:
                return items[1].get_content()
        except Exception:
            logger.debug('封面查找策略二失败: ITEM_COVER')

        # 策略三：在所有图片中找文件名含 cover 的
        try:
            for item in self._book.get_items_of_type(ebooklib.ITEM_IMAGE):
                if 'cover' in item.get_name():
                    return item.get_content()
        except Exception:
            logger.debug('封面查找策略三失败: 文件名匹配')

        return None

    def extract_images(self, output_dir: str) -> list[str]:
        """
        提取 EPUB 内嵌图片到 output_dir。

        遍历 EPUB 中所有资源，只要是 ITEM_IMAGE 类型就写入磁盘。
        注意：有些 EPUB 将封面也标记为 ITEM_IMAGE，所以封面也会被提取。

        Args:
            output_dir: 图片输出目录（自动创建）

        Returns:
            提取成功的图片文件名列表
        """
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

    # ---- 元信息修改 ----

    def _fix_toc_uids(self):
        """
        修复 TOC 中缺失 uid 的 Link 对象。

        某些外部工具生成的 EPUB，其目录项的 uid 为 None，
        ebooklib 写回时会将 uid 作为 XML 属性写入，不允许 None。
        此方法递归遍历 TOC，为缺 uid 的 Link 分配唯一 ID。
        """
        def _assign(item):
            if isinstance(item, epub.Link) and not item.uid:
                item.uid = f'navpoint-{uuid.uuid4().hex[:8]}'
            elif isinstance(item, tuple):
                link, children = item
                _assign(link)
                for child in children:
                    _assign(child)

        for item in self._book.toc:
            _assign(item)

    def modi(self, info: BookInfo, filepath: Optional[str] = None) -> None:
        """
        修改 EPUB 元数据并保存。

        set_unique_metadata 会替换同名字段的旧值（不会追加）。
        如果 info.cover 不为 None，同时更新封面图片。

        Args:
            info:     新的元数据
            filepath: 保存路径（不传则覆盖原文件）
        """
        self._fix_toc_uids()
        self._book.set_unique_metadata('DC', 'title', info.title)
        self._book.set_unique_metadata('DC', 'date', info.date)
        self._book.set_unique_metadata('DC', 'creator', info.creator)
        self._book.set_unique_metadata('DC', 'contributor', info.contributor)
        desc = info.description or DEFAULT_DESC
        self._book.set_unique_metadata('DC', 'description', desc)
        if info.cover is not None:
            # 直接替换已有封面图片内容，而非调用 set_cover()。
            # set_cover() 会创建 EpubCoverHtml 页面，
            # 某些 EPUB 中该页面内容为空，导致写回时 lxml 报 Document is empty。
            replaced = False
            for item in self._book.get_items():
                if item.get_type() in (ebooklib.ITEM_IMAGE, ebooklib.ITEM_COVER):
                    name = item.get_name()
                    cid = getattr(item, 'id', '')
                    if 'cover' in name.lower() or 'cover' in str(cid).lower():
                        item.set_content(info.cover)
                        replaced = True
                        break
            if not replaced:
                self._book.set_cover('cover.jpeg', info.cover)
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

    # ---- 提取封面图片到磁盘 ----

    def _save_cover_if_exists(self) -> None:
        """
        提取封面图片到输出目录。

        在合并/按章节导出 TXT 时被调用，把封面保存到 TXT 同目录下。

        判断逻辑：
        - 类型是 ITEM_IMAGE 或 ITEM_COVER（图片）
        - 文件名或 ID 包含 "cover" 字样
        两个条件都满足才认为是封面。

        注意：有些 EPUB 的封面 ID 可能是 "frontcover"、"cvr" 等变体。
        目前只匹配含 "cover" 的 ID。
        """
        for item in self._book.get_items():
            is_cover_type = item.get_type() in (
                ebooklib.ITEM_IMAGE, ebooklib.ITEM_COVER)
            is_cover_name = (
                'cover' in item.get_name()
                or 'cover' in str(item.id or '')
            )
            if is_cover_type and is_cover_name:
                _, ext = os.path.splitext(item.get_name())
                out = os.path.join(self._dir, f'cover{ext}')
                with open(out, 'wb') as f:
                    f.write(item.get_content())
                return

    def _process_document(self, item, fanjian: bool) -> str:
        """
        解析 EPUB 文档项，提取纯文本并应用繁简转换和分隔符。

        BeautifulSoup 解析：
        1. 找到第一个 <h1>-<h4> 标签，在其后插入一个换行符
           （这样标题和正文之间会有一个空行）
        2. 提取纯文本（get_text() 返回所有文本，不带 HTML 标签）
        3. 如果勾选了繁简转换，调用 OpenCC
        4. 在末尾添加章节分隔符（如果用户设置了的话）

        Args:
            item: epub 文档项（EpubHtml 对象）
            fanjian: 是否进行繁→简转换

        Returns:
            处理后的纯文本字符串
        """
        # EPUB规范要求XHTML使用UTF-8编码，不应用用户指定的输出编码
        # 但存在不规范文件；解码失败用替换字符兜底，
        # 不让单个文档毁掉整次转换
        soup = BeautifulSoup(
            item.get_content().decode('utf-8', errors='replace'),
            'html.parser',
        )
        for tag in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            tag.insert_after(soup.new_string('\n'))
            break  # 只在第一个标题后加换行
        text = self._cc.convert(soup.get_text()) if fanjian else soup.get_text()
        text = text.rstrip('\n') + '\n'
        # 分隔符追加到每章文本末尾（未设置时 sep 为空串，不追加）
        if self.sep:
            text += self.sep
        return text

    def _get_content_items(self):
        """
        获取 EPUB 中所有有价值的文档项。

        过滤掉：
        - 非文档类型（如图片、CSS）
        - nav.xhtml（EPUB 3 的导航页）
        - toc.ncx（EPUB 2 的目录文件）
        - cover.xhtml（封面说明页）
        这些内容对读者没有意义，不应该出现在输出 TXT 中。
        """
        return [
            item for item in self._book.get_items()
            if item.get_type() == ebooklib.ITEM_DOCUMENT
            and item.get_name() not in ('nav.xhtml', 'toc.ncx', 'cover.xhtml')
        ]

    # ---- 转换 ----

    def convert(
        self,
        fanjian: bool = False,
        progress: Optional[Callable[[int, int], None]] = None,
        status: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        合并所有章节到单个 TXT 文件。

        流程：
        1. 提取封面到目录
        2. 遍历 EPUB 中所有文档（排除 nav.xhtml / toc.ncx / cover.xhtml）
        3. 解析每个文档的 HTML，提取纯文本
        4. 写入 TXT 文件，按用户设置添加章节分隔符

        注意：所有文档按 EPUB spine 顺序（即阅读顺序）依次处理。

        Args:
            fanjian: 是否进行繁→简转换
            progress: 进度回调 (current, total)
            status:   状态回调 (message)
        """
        # 先确保输出目录存在，再提取封面（顺序反了目录不存在会 FileNotFoundError）
        out_dir = self._dir
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self._save_cover_if_exists()

        docs = self._get_content_items()
        total = len(docs)

        with open(self.txt_path, 'w', encoding=self.encoding) as f:
            for idx, item in enumerate(docs, start=1):
                if status:
                    status(f'正在处理第 {idx}/{total} 个文档…')
                if progress:
                    progress(idx, total)

                text = self._process_document(item, fanjian)
                f.write(text)

    def convert_chapter(
        self,
        fanjian: bool = False,
        progress: Optional[Callable[[int, int], None]] = None,
        status: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        按章节导出为多个 TXT 文件。

        每个 EPUB 文档独立保存为一个 TXT 文件，文件名格式：
            原文件名1.txt
            原文件名2.txt
            ...

        输出目录 = TXT 路径所在目录（如果不存在，自动创建）。

        Args:
            fanjian: 是否进行繁→简转换
            progress: 进度回调 (current, total)
            status:   状态回调 (message)
        """
        out_dir = self._dir
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        self._save_cover_if_exists()

        base = os.path.splitext(os.path.basename(self.txt_path))[0]
        ext = os.path.splitext(self.txt_path)[1]

        docs = self._get_content_items()
        total = len(docs)

        # 按章节导出每个文件只有一章，章节间分隔符不适用，
        # 导出前暂时清空 sep，结束后恢复（try/finally 保证异常路径也恢复）
        saved_sep = self.sep
        self.sep = ''
        try:
            for idx, item in enumerate(docs, start=1):
                if status:
                    status(f'正在导出第 {idx}/{total} 章…')
                if progress:
                    progress(idx, total)

                text = self._process_document(item, fanjian)

                chapter_path = os.path.join(out_dir, f'{base}{idx}{ext}')
                with open(chapter_path, 'w', encoding=self.encoding) as f:
                    f.write(text)
        finally:
            self.sep = saved_sep


# =====================================================================
# Epub2Mobi — EPUB → MOBI（框架）
# =====================================================================

class Epub2Mobi:
    """
    EPUB → MOBI 转换（框架接口，需外部工具）。

    当前只是占位符，因为 MOBI 转换需要 Calibre 的 ebook-convert 命令
    或 KindleGen 工具，这些没有包含在 Python 依赖中。

    未来实现方式：
        1. 检测系统是否安装了 Calibre
        2. 调用 subprocess 执行 ebook-convert
        3. 解析输出反馈给 progress/status 回调

    为什么保留这个空类？
    1. UI 中已有"→MOBI"按钮，需要一个对应的处理逻辑
    2. 作为未来扩展的骨架，方便开发
    3. NotImplementedError 比"按钮没有反应"的用户体验好
    """

    def __init__(self, epub_path: str, mobi_path: str):
        self.epub_path = epub_path
        self.mobi_path = mobi_path

    def convert(self):
        raise NotImplementedError(
            'EPUB→MOBI 转换需要安装 Calibre 或 KindleGen。\n'
            '当前为框架接口，待实现。'
        )


# =====================================================================
# convert_mobi_to_txt — MOBI → TXT（独立函数）
# =====================================================================

def convert_mobi_to_txt(
    mobi_path: Path,
    txt_path: Optional[Path] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    status: Optional[Callable[[str], None]] = None,
) -> Path:
    """
    将 MOBI 文件转换为 TXT。

    为什么这是一个独立函数而不是类？
    MOBI→TXT 逻辑简单（解压→提取 HTML→合并文本），
    不需要像 EPUB 转换那样维护复杂的内部状态。
    函数比类更清晰（即"纯函数"风格）。

    转换原理：
    1. 用 mobi 库解压 MOBI 文件到临时目录
    2. 在临时目录中找到所有 HTML 文件
    3. 用 BeautifulSoup 解析 HTML，提取纯文本
    4. 合并所有文本写入 TXT 文件
    5. 清理临时目录

    注意：
    - mobi 库的 extract() 会创建临时目录，需要及时清理
    - HTML 文件按文件名排序，确保章节顺序正确
    - 如果 MOBI 包含特殊格式（如表格、脚注），提取效果可能不完美

    Args:
        mobi_path: MOBI 文件路径
        txt_path:  输出 TXT 路径（不传则自动在 MOBI 同目录生成）
        progress:  进度回调 (current, total)
        status:    状态回调 (message)

    Returns:
        输出的 TXT 文件路径
    """
    import mobi

    txt_path = txt_path or mobi_path.with_suffix('.txt')

    if status:
        status('正在解压 MOBI 文件…')

    # mobi.extract 返回 (临时目录, 文件名) 的元组
    # tmpdir 是字符串，需转换成 Path 才能用 rglob
    tmpdir, _ = mobi.extract(str(mobi_path))
    tmpdir = Path(tmpdir)

    try:
        # .html 与 .htm 合并后按文件名自然序排序：
        # 先避免 .htm 全排到最后；再按数字段比较，
        # 保证 text2.htm 排在 text10.htm 之前（字典序会把 text10 插到 text2 前，≥10 章章节错乱）
        def _natural_key(p):
            return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', p.name)]

        html_files = sorted(
            list(tmpdir.rglob('*.html')) + list(tmpdir.rglob('*.htm')),
            key=_natural_key,
        )
        if not html_files:
            raise RuntimeError('未能在解压目录里找到 html 文件')

        total = len(html_files)

        # 逐个解析 HTML，提取纯文本
        # get_text(separator='\n', strip=True) 用换行符连接文本块，
        # 并自动去除首尾空白。
        parts = []
        for idx, hf in enumerate(html_files, start=1):
            if status:
                status(f'正在解析第 {idx}/{total} 个文档…')
            if progress:
                progress(idx, total)
            soup = BeautifulSoup(hf.read_bytes(), 'html.parser')
            parts.append(soup.get_text(separator='\n', strip=True))

        # 合并写入 TXT
        txt_path.write_text('\n'.join(parts), encoding='utf-8')
    finally:
        # 清理临时目录（ignore_errors=True 防止权限问题报错）
        shutil.rmtree(tmpdir, ignore_errors=True)

    return txt_path


def extract_mobi_metadata(mobi_path: Path) -> dict:
    """
    从 MOBI 文件中提取书籍元数据。

    Args:
        mobi_path: MOBI 文件路径

    Returns:
        包含书籍信息的字典，字段包括：
        - title: 书名
        - creator: 作者
        - publisher: 出版商
        - description: 描述
        - isbn: ISBN
        - language: 语言
        - published: 出版日期
        - subject: 主题
        - cover_offset: 封面图片偏移量（用于提取封面）
    """
    metadata = {
        'title': '',
        'creator': '',
        'publisher': '',
        'description': '',
        'isbn': '',
        'language': '',
        'published': '',
        'subject': '',
        'cover_offset': None
    }
    
    try:
        from mobi.mobi_sectioner import Sectionizer
        from mobi.mobi_header import MobiHeader
        
        sect = Sectionizer(str(mobi_path))
        mobi_header = MobiHeader(sect, 0)
        exth_metadata = mobi_header.getMetaData()
        
        # 提取元数据字段
        metadata['title'] = exth_metadata.get('Title', [''])[0]
        metadata['creator'] = exth_metadata.get('Creator', [''])[0]
        metadata['publisher'] = exth_metadata.get('Publisher', [''])[0]
        metadata['description'] = exth_metadata.get('Description', [''])[0]
        metadata['isbn'] = exth_metadata.get('ISBN', [''])[0]
        metadata['language'] = exth_metadata.get('Language', [''])[0]
        metadata['published'] = exth_metadata.get('Published', [''])[0]
        metadata['subject'] = exth_metadata.get('Subject', [''])[0]
        
        # 提取封面偏移量
        if 'CoverOffset' in exth_metadata:
            metadata['cover_offset'] = int(exth_metadata['CoverOffset'][0])
            
    except Exception as e:
        logger.error(f'提取 MOBI 元数据失败: {e}')
        # 不再静默吞错：让 UI 层弹出可读的错误提示
        raise RuntimeError(f'无法读取 MOBI 元数据: {e}') from e

    return metadata


def extract_mobi_cover(mobi_path: Path, cover_offset: int) -> Optional[bytes]:
    """
    从 MOBI 文件中提取封面图片。

    Args:
        mobi_path: MOBI 文件路径
        cover_offset: 封面图片偏移量（未使用，保留接口兼容）

    Returns:
        封面图片的二进制数据，如果提取失败返回 None
    """
    import mobi
    
    try:
        # 使用 mobi.extract 解压 MOBI 文件到临时目录
        tmpdir, _ = mobi.extract(str(mobi_path))
        tmpdir = Path(tmpdir)
        
        try:
            # 在临时目录中查找图片文件（优先查找 cover 相关文件）
            cover_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
            
            # 首先查找文件名包含 cover 的图片
            for ext in cover_extensions:
                for img_file in tmpdir.rglob(f'*cover*{ext}'):
                    return img_file.read_bytes()
            
            # 如果没有找到 cover 文件，查找第一个图片文件
            for ext in cover_extensions:
                for img_file in tmpdir.rglob(f'*{ext}'):
                    return img_file.read_bytes()
            
            return None
        finally:
            # 清理临时目录
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
            
    except Exception as e:
        logger.error(f'提取 MOBI 封面失败: {e}')
        return None
