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
        book.toc = tuple(items)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        if with_cover:
            book.set_cover('cover.jpeg', b'\xff\xd8\xff\xe0fake')
            book.spine = ['cover'] + items
        else:
            book.spine = list(items)
        path = str(tmp_path / name)
        epub.write_epub(path, book, {})
        return path

    return _make
