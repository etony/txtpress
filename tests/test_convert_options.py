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
    conv.configure(ConvertOptions())   # 全默认 → 不覆盖
    assert conv.title == '原标题'
    assert conv.language == 'cn'       # 默认值与 Txt2Epub 现状一致


def test_configure_unknown_field_raises(sample_txt):
    @dataclass
    class BadOpts:
        no_such: int = 1

    conv = Txt2Epub(sample_txt, 'out.epub')
    with pytest.raises(AttributeError):
        conv.configure(BadOpts())


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
