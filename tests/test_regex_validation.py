# -*- coding: utf-8 -*-
"""章节正则校验测试。"""
import re

import pytest

from services import Txt2Epub, validate_chapter_regex, DEFAULT_CHAPTER_REGEX


def test_default_regex_ok():
    assert isinstance(
        validate_chapter_regex(DEFAULT_CHAPTER_REGEX), re.Pattern
    )


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


def test_validate_before_open(tmp_path):
    """校验必须先于 open()：不存在的路径 + 非法正则，应报正则错误。

    若校验被挪回 open() 之后，会先抛 FileNotFoundError 而失败。
    """
    conv = Txt2Epub(str(tmp_path / 'missing.txt'), str(tmp_path / 'out.epub'))
    conv.regex = r'^第.*章.*$'  # 0 捕获组
    with pytest.raises(ValueError, match='捕获组'):
        conv.get_chapters()


def test_named_capture_group_ok():
    """命名捕获组也算 1 个组，应通过。"""
    validate_chapter_regex(r'(?P<title>第.+章)')


def test_non_capturing_group_rejected():
    """非捕获组 (?:...) 不算组，应被拒。"""
    with pytest.raises(ValueError, match='捕获组'):
        validate_chapter_regex(r'(?:第.+章)')
