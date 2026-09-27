# -*- coding: utf-8 -*-
"""ConvertOptions 配置测试。"""
from dataclasses import dataclass

import pytest

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
    conv.configure(ConvertOptions())   # 空值字段（title=''）被 skip
    assert conv.title == '原标题'
    # 非空默认值总是生效：language 默认 'cn' 会重置已设的 'en'
    conv.language = 'en'
    conv.configure(ConvertOptions())
    assert conv.language == 'cn'


def test_configure_unknown_field_raises(sample_txt):
    @dataclass
    class BadOpts:
        no_such: int = 1

    conv = Txt2Epub(sample_txt, 'out.epub')
    with pytest.raises(AttributeError):
        conv.configure(BadOpts())


def test_configure_reserved_field_raises(sample_txt):
    """预留字段（publisher 等）传非空值要响亮报错。"""
    conv = Txt2Epub(sample_txt, 'out.epub')
    with pytest.raises(AttributeError):
        conv.configure(ConvertOptions(publisher='X'))


def test_configure_maps_path_aliases(sample_txt):
    """text_path/out_path 显式映射到 txt_path/epub_path 属性。"""
    conv = Txt2Epub(sample_txt, 'out.epub')
    conv.configure(ConvertOptions(text_path='a.txt', out_path='b.epub'))
    assert conv.txt_path == 'a.txt'
    assert conv.epub_path == 'b.epub'


def test_configure_chapter_order(sample_txt):
    """chapter_order 为 None 跳过，非 None 覆盖。"""
    conv = Txt2Epub(sample_txt, 'out.epub')
    conv.configure(ConvertOptions(chapter_order=[(1, '乙'), (0, '甲')]))
    assert conv._chapter_order == [(1, '乙'), (0, '甲')]
    conv.configure(ConvertOptions())   # None 不清空已有顺序
    assert conv._chapter_order == [(1, '乙'), (0, '甲')]


def test_configure_then_convert_end_to_end(sample_txt, tmp_path):
    """configure 设置的元数据必须写入产物 EPUB。"""
    from ebooklib import epub

    out = str(tmp_path / 'opts.epub')
    conv = Txt2Epub(sample_txt, out)
    conv.configure(ConvertOptions(title='定制书名', author='某作者'))
    conv.convert()
    book = epub.read_epub(out)
    # ebooklib 0.20 的 metadata 条目为 (value, extra) 元组
    assert book.get_metadata('DC', 'title')[0][0] == '定制书名'
    assert book.get_metadata('DC', 'creator')[0][0] == '某作者'
