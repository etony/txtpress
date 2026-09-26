# -*- coding: utf-8 -*-
"""章节排序 / 重命名行为测试。"""
import zipfile

from services import Txt2Epub


def test_rename_by_index(tmp_path):
    """重命名 + 调序：新标题生效、顺序正确、正文不串章。"""
    txt = tmp_path / 'r.txt'
    txt.write_text(
        '第一章 啊\n正文一。\n第一章 啊\n正文二。\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'r.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.set_chapter_order([(1, '改B'), (0, '改A')])
    conv.convert()

    with zipfile.ZipFile(out) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
        assert '改B' in nav and '改A' in nav
        assert nav.index('改B') < nav.index('改A')
        ca = z.read('EPUB/改A.xhtml').decode('utf-8')
        cb = z.read('EPUB/改B.xhtml').decode('utf-8')
    assert '正文一' in ca and '正文二' in cb


def test_duplicate_titles_not_dropped(tmp_path):
    """重复章节标题默认顺序下两章都要生成。"""
    txt = tmp_path / 'd.txt'
    txt.write_text(
        '第一章 啊\n正文一。\n第一章 啊\n正文二。\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'd.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()
    with zipfile.ZipFile(out) as z:
        names = [n for n in z.namelist() if n.endswith('.xhtml')]
    assert len([n for n in names if 'nav' not in n and 'xu' not in n]) == 2


def test_original_order_when_none(tmp_path):
    """传 None 时保持原序并实际转换（回归保护）。"""
    txt = tmp_path / 'o.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    out = str(tmp_path / 'o.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    assert conv.get_chapters() == ['第1章 甲', '第1章 乙']
    conv.set_chapter_order(None)
    conv.convert()
    with zipfile.ZipFile(out) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
    assert nav.index('第1章 甲') < nav.index('第1章 乙')


def test_out_of_range_index_skipped(tmp_path):
    """越界索引跳过不崩溃，合法项生效，未命中的章补到末尾。"""
    txt = tmp_path / 'b.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    out = str(tmp_path / 'b.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.set_chapter_order([(5, 'X'), (0, 'A')])
    conv.convert()
    with zipfile.ZipFile(out) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
        names = [n for n in z.namelist()
                 if n.endswith('.xhtml') and 'nav' not in n]
    assert 'X' not in nav          # 越界项被丢弃
    assert 'A' in nav and '乙' in nav
    assert nav.index('A') < nav.index('乙')
    assert len(names) == 2         # 不丢章


def test_duplicate_index_first_wins(tmp_path):
    """重复索引首次生效，其余忽略，不丢章。"""
    txt = tmp_path / 'e.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    out = str(tmp_path / 'e.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.set_chapter_order([(0, 'A'), (0, 'B')])
    conv.convert()
    with zipfile.ZipFile(out) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
        names = [n for n in z.namelist()
                 if n.endswith('.xhtml') and 'nav' not in n]
    assert 'A' in nav and 'B' not in nav
    assert '乙' in nav
    assert len(names) == 2


def test_partial_order_appends_missing(tmp_path):
    """部分列表：未出现的章按原序补到末尾。"""
    txt = tmp_path / 'p.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    out = str(tmp_path / 'p.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.set_chapter_order([(1, 'B')])
    conv.convert()
    with zipfile.ZipFile(out) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
    assert 'B' in nav and '甲' in nav
    assert nav.index('B') < nav.index('甲')


def test_blank_new_title_falls_back(tmp_path):
    """新标题全空白时回退原标题，避免生成空文件名。"""
    txt = tmp_path / 'f.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    out = str(tmp_path / 'f.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.set_chapter_order([(0, '   '), (1, '乙章')])
    conv.convert()
    with zipfile.ZipFile(out) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
        names = [n for n in z.namelist()
                 if n.endswith('.xhtml') and 'nav' not in n]
    assert '第1章 甲' in nav and '乙章' in nav
    assert 'EPUB/.xhtml' not in names
