# -*- coding: utf-8 -*-
"""章节正则校验测试。"""
import pytest

from services import Txt2Epub, validate_chapter_regex, DEFAULT_CHAPTER_REGEX


def test_default_regex_ok():
    validate_chapter_regex(DEFAULT_CHAPTER_REGEX)  # 不抛异常


def test_regex_without_capture_group(sample_txt, tmp_path):
    conv = Txt2Epub(sample_txt, str(tmp_path / 'out.epub'))
    conv.regex = r'^第.*章.*$'
    with pytest.raises(ValueError, match='捕获组'):
        conv.get_chapters()


def test_regex_with_two_capture_groups(sample_txt, tmp_path):
    conv = Txt2Epub(sample_txt, str(tmp_path / 'out.epub'))
    conv.regex = r'(第)(\d+)章.*'
    with pytest.raises(ValueError, match='捕获组'):
        conv.get_chapters()


def test_invalid_regex_syntax(sample_txt, tmp_path):
    conv = Txt2Epub(sample_txt, str(tmp_path / 'out.epub'))
    conv.regex = '(未闭合'
    with pytest.raises(ValueError, match='无效的正则'):
        conv.get_chapters()
