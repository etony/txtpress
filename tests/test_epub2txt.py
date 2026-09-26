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


def test_convert_creates_missing_outdir_with_cover(make_epub, tmp_path):
    """输出目录不存在 + 有封面时也应成功（先建目录再存封面）。"""
    out = str(tmp_path / 'newdir' / 'o.txt')
    conv = Epub2Txt(make_epub(with_cover=True), out)
    conv.convert()
    assert Path(out).exists()
    assert (tmp_path / 'newdir' / 'cover.jpeg').exists()


def test_convert_chapter_outdir_empty(make_epub, tmp_path, monkeypatch):
    """txt_path 无目录部分（如 out.txt）时不能因 makedirs('') 崩溃。"""
    monkeypatch.chdir(tmp_path)
    conv = Epub2Txt(make_epub(), 'base.txt')
    conv.convert_chapter()
    assert (tmp_path / 'base1.txt').exists()
