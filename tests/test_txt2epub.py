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
