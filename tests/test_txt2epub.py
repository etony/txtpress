# -*- coding: utf-8 -*-
"""Txt2Epub 基础行为测试。"""
import os
import zipfile


def test_get_chapters(sample_txt, tmp_path):
    from services import Txt2Epub
    conv = Txt2Epub(sample_txt, str(tmp_path / 'unused.epub'))
    assert conv.get_chapters() == ['第一章 开始', '第二章 继续']


def test_convert_creates_epub(sample_txt, tmp_path):
    from services import Txt2Epub
    out = str(tmp_path / 'out.epub')
    conv = Txt2Epub(sample_txt, out)
    conv.title = '测试书'
    conv.convert()
    assert os.path.exists(out)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None


def test_make_epub_variants(make_epub):
    """fixture 三种参数组合均能生成并回读 EPUB。"""
    from ebooklib import epub

    cases = [
        dict(name='cover.epub', with_cover=True),
        dict(name='images.epub', images=['images/a.png']),
        dict(name='chapters.epub', chapters=[('标题', '正文')]),
    ]
    for kwargs in cases:
        path = make_epub(**kwargs)
        book = epub.read_epub(path)
        assert book.get_metadata('DC', 'title')
