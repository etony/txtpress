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


def test_convert_gbk_output_survives_invalid_utf8(make_epub, tmp_path,
                                                  monkeypatch):
    """解码 replace 产生的 U+FFFD 在 gbk 输出下不应中断整个转换。"""
    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'), encoding='gbk')

    class StubDoc:
        def get_content(self):
            return b'<p>caf\xe9</p>'

    monkeypatch.setattr(conv, '_get_content_items', lambda: [StubDoc()])

    conv.convert()  # 修复前：写 gbk 时 UnicodeEncodeError
    conv.convert_chapter()

    text = (tmp_path / 'o.txt').read_text(encoding='gbk')
    assert 'caf?' in text  # U+FFFD 编码失败降级为 ?
    assert (tmp_path / 'o1.txt').exists()


def test_extract_images_dedupes_names(make_epub, tmp_path):
    """不同子目录的同名图片不能互相覆盖。"""
    epub_path = make_epub(images=['images/a.png', 'pics/a.png'])
    conv = Epub2Txt(epub_path, str(tmp_path / 'o.txt'))
    files = conv.extract_images(str(tmp_path / 'imgs'))
    assert sorted(files) == ['a.png', 'a_2.png']
    assert (tmp_path / 'imgs' / 'a.png').exists()
    assert (tmp_path / 'imgs' / 'a_2.png').exists()


def _stub_cover_book(name: str, item_id):
    """构造只含单张图片的桩 book，图片名与 id 可控。"""
    import ebooklib

    class StubItem:
        def __init__(self):
            self.id = item_id

        def get_type(self):
            return ebooklib.ITEM_IMAGE

        def get_name(self):
            return name

        def get_content(self):
            return b'PNG'

    class StubBook:
        def get_items(self):
            return [StubItem()]

    return StubBook()


def test_save_cover_tolerates_none_id(make_epub, tmp_path):
    """name 不含 cover 且 id=None：id 判断分支不抛 TypeError，也不误存封面。"""
    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))
    conv._book = _stub_cover_book('front.png', None)

    conv._save_cover_if_exists()  # 修复前 'cover' in None 抛 TypeError
    assert not (tmp_path / 'cover.png').exists()


def test_save_cover_matches_id_branch(make_epub, tmp_path):
    """name 不含 cover 但 id 含 cover：id 分支仍能识别并保存封面。"""
    conv = Epub2Txt(make_epub(), str(tmp_path / 'o.txt'))
    conv._book = _stub_cover_book('front.png', 'mycover')

    conv._save_cover_if_exists()
    saved = tmp_path / 'cover.png'
    assert saved.exists()
    assert saved.read_bytes() == b'PNG'


def _fake_mobi_extract(tmp_path, monkeypatch, files: dict):
    """伪造 mobi.extract：在临时目录生成给定文件并打桩返回。"""
    import mobi

    fake_dir = tmp_path / 'extracted'
    fake_dir.mkdir(exist_ok=True)
    for name, text in files.items():
        (fake_dir / name).write_text(text, encoding='utf-8')
    monkeypatch.setattr(mobi, 'extract', lambda p: (str(fake_dir), None))
    return fake_dir


def _run_mobi_txt(tmp_path) -> list[str]:
    from services import convert_mobi_to_txt

    out = convert_mobi_to_txt(tmp_path / 'in.mobi', tmp_path / 'out.txt')
    return Path(out).read_text(encoding='utf-8').splitlines()


def test_mobi_html_merge_order(tmp_path, monkeypatch):
    """混合 .htm/.html 时按自然序合并排序，part10 不排到 part2 前面。"""
    _fake_mobi_extract(tmp_path, monkeypatch, {
        'chapter1.htm': 'part1',
        'chapter2.html': 'part2',
        'chapter10.htm': 'part10',
    })
    # 自然序按数字段数值比较：1 < 2 < 10
    # 旧实现按扩展名分组输出 part2/part1/part10（.htm 全排最后）
    assert _run_mobi_txt(tmp_path) == ['part1', 'part2', 'part10']


def test_mobi_html_merge_interleaved(tmp_path, monkeypatch):
    """.htm 与 .html 交错命名时仍保持自然序，不按扩展名分组。"""
    _fake_mobi_extract(tmp_path, monkeypatch, {
        'a1.htm': 'x1',
        'a2.html': 'x2',
        'a10.htm': 'x10',
    })
    # a1.htm < a2.html < a10.htm（自然序），旧实现会把 .htm 全挤到 .html 之后
    assert _run_mobi_txt(tmp_path) == ['x1', 'x2', 'x10']


def test_mobi_html_merge_mixed_names(tmp_path, monkeypatch):
    """无数字与有数字文件名混合不触发 TypeError，顺序仍确定。"""
    _fake_mobi_extract(tmp_path, monkeypatch, {
        'text10.htm': 't10',
        'cover.html': 'cv',
        'text2.htm': 't2',
        'text1.htm': 't1',
    })
    # cover 无数字段，与 text* 首段比较均为 str，不产生 str/int 比较
    assert _run_mobi_txt(tmp_path) == ['cv', 't1', 't2', 't10']


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
