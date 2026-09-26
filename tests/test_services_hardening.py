# -*- coding: utf-8 -*-
"""services 防御性行为测试。"""
import os
from pathlib import Path

import pytest

from services import Epub2Txt


def test_process_document_tolerates_invalid_utf8(make_epub, tmp_path):
    """非 UTF-8 字节不应导致 UnicodeDecodeError。"""
    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))

    class StubItem:
        def get_content(self):
            return b'<p>caf\xe9</p>'

    text = conv._process_document(StubItem(), False)
    assert 'caf' in text


def test_extract_images_dedupes_names(make_epub, tmp_path):
    """不同子目录的同名图片不能互相覆盖。"""
    epub_path = make_epub(images=['images/a.png', 'pics/a.png'])
    conv = Epub2Txt(epub_path, str(tmp_path / 'o.txt'))
    files = conv.extract_images(str(tmp_path / 'imgs'))
    assert sorted(files) == ['a.png', 'a_2.png']
    assert (tmp_path / 'imgs' / 'a.png').exists()
    assert (tmp_path / 'imgs' / 'a_2.png').exists()


def test_save_cover_tolerates_none_id(make_epub, tmp_path):
    """item.id 为 None 时不应抛 TypeError。"""
    import ebooklib

    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))

    class StubItem:
        id = None

        def get_type(self):
            return ebooklib.ITEM_IMAGE

        def get_name(self):
            return 'frontcover.png'

        def get_content(self):
            return b'PNG'

    class StubBook:
        def get_items(self):
            return [StubItem()]

    conv._book = StubBook()
    conv._save_cover_if_exists()  # 不应抛异常
    assert (tmp_path / 'cover.png').exists()


def test_mobi_html_merge_order(tmp_path, monkeypatch):
    """混合 .htm/.html 时按文件名合并排序，.htm 不全排在 .html 之后。"""
    import mobi
    from services import convert_mobi_to_txt

    fake_dir = tmp_path / 'extracted'
    fake_dir.mkdir()
    (fake_dir / 'chapter1.htm').write_text('part1', encoding='utf-8')
    (fake_dir / 'chapter2.html').write_text('part2', encoding='utf-8')
    (fake_dir / 'chapter10.htm').write_text('part10', encoding='utf-8')
    monkeypatch.setattr(mobi, 'extract', lambda p: (str(fake_dir), None))

    out = convert_mobi_to_txt(tmp_path / 'in.mobi', tmp_path / 'out.txt')
    lines = Path(out).read_text(encoding='utf-8').splitlines()
    # 按文件名字典序：chapter1.htm < chapter10.htm < chapter2.html
    # 旧实现按扩展名分组输出为 part2/part1/part10（.htm 全排最后）
    assert lines == ['part1', 'part10', 'part2']


def test_extract_mobi_metadata_raises_on_failure(tmp_path):
    """MOBI 元数据提取失败必须抛 RuntimeError，不再静默返回空字段。"""
    from services import extract_mobi_metadata

    with pytest.raises(RuntimeError, match='无法读取 MOBI 元数据'):
        extract_mobi_metadata(tmp_path / 'missing.mobi')


def test_modi_writes_atomically(make_epub, tmp_path):
    """modi 写新文件成功且不残留 .tmp。"""
    from models import BookInfo

    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))
    target = str(tmp_path / 'new.epub')
    conv.modi(BookInfo(title='新标题'), filepath=target)
    assert os.path.exists(target)
    assert not os.path.exists(target + '.tmp')


def test_modi_write_failure_keeps_original(make_epub, tmp_path, monkeypatch):
    """写回失败时原文件保持完好，且不残留 .tmp 半成品。"""
    from ebooklib import epub
    from models import BookInfo

    path = make_epub()
    original = Path(path).read_bytes()
    conv = Epub2Txt(path, str(tmp_path / 'o.txt'))

    def boom(tmp_target, *args, **kwargs):
        # 模拟写到一半失败：先留下半成品 .tmp 再抛异常
        Path(tmp_target).write_bytes(b'partial')
        raise OSError('磁盘满')

    monkeypatch.setattr(epub, 'write_epub', boom)
    with pytest.raises(OSError):
        conv.modi(BookInfo(title='新标题'))

    assert Path(path).read_bytes() == original  # 原文件未被破坏
    assert not os.path.exists(path + '.tmp')    # 无半成品残留
