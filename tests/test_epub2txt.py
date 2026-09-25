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
