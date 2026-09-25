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
    assert texts[3].count('---') == 2  # 两章各追加一次分隔线


def test_convert_chapter_ignores_sep(make_epub, tmp_path):
    """按章节导出时每个文件只有一章，不应追加章节分隔符。"""
    conv = Epub2Txt(make_epub(), str(tmp_path / 'base.txt'))
    conv.sep = '\n---\n'
    conv.convert_chapter()

    files = list(tmp_path.glob('base*.txt'))
    assert len(files) == 2  # 实际产物为 base1.txt / base2.txt
    for f in files:
        assert '---' not in f.read_text(encoding='utf-8')
    assert conv.sep == '\n---\n'  # 导出结束后 sep 应恢复原值
