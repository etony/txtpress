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
    """传 None 时保持原序（回归保护）。"""
    txt = tmp_path / 'o.txt'
    txt.write_text('第1章 甲\n甲。\n第1章 乙\n乙。\n', encoding='utf-8')
    conv = Txt2Epub(str(txt), str(tmp_path / 'o.epub'))
    assert conv.get_chapters() == ['第1章 甲', '第1章 乙']
    conv.set_chapter_order(None)
    assert conv.get_chapters() == ['第1章 甲', '第1章 乙']
