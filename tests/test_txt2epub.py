# -*- coding: utf-8 -*-
"""Txt2Epub 基础行为测试。"""
import os
import zipfile


def test_get_chapters(sample_txt, tmp_path):
    from services import Txt2Epub
    conv = Txt2Epub(sample_txt, str(tmp_path / 'unused.epub'))
    assert conv.get_chapters() == ['第一章 开始', '第二章 继续']


def test_convert_creates_epub(sample_txt, tmp_path):
    from services import Txt2Epub
    out = str(tmp_path / 'out.epub')
    conv = Txt2Epub(sample_txt, out)
    conv.title = '测试书'
    conv.convert()
    assert os.path.exists(out)
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None


def test_html_escaping(tmp_path):
    """正文中的 <、>、& 必须被转义，不能当成标签。"""
    from services import Txt2Epub
    txt = tmp_path / 'x.txt'
    txt.write_text(
        '第1章 前<后\n正文<b>加粗</b>与&符号\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'x.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()

    with zipfile.ZipFile(out) as z:
        joined = b''.join(
            z.read(n) for n in z.namelist() if n.endswith('.xhtml')
        ).decode('utf-8')
    assert '<b>加粗</b>' not in joined
    assert '&lt;' in joined
    assert '<h2>第1章 前&lt;后</h2>' in joined
    assert '加粗' in joined


def test_paragraph_split(tmp_path):
    """空行应拆分成独立 <p> 段落。"""
    from services import Txt2Epub
    txt = tmp_path / 'p.txt'
    txt.write_text(
        '第一章 标题\n第一段。\n\n第二段。\n',
        encoding='utf-8',
    )
    out = str(tmp_path / 'p.epub')
    conv = Txt2Epub(str(txt), out)
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()

    with zipfile.ZipFile(out) as z:
        joined = b''.join(
            z.read(n) for n in z.namelist() if n.endswith('.xhtml')
        ).decode('utf-8')
    assert '<p>第一段。</p>' in joined
    assert '<p>第二段。</p>' in joined


def test_preamble_threshold(tmp_path):
    """序章判定按 strip 后的原始文本长度阈值（当前语义加锁）。"""
    from services import Txt2Epub, _MIN_PREAMBLE_LEN

    def build(name, preamble_text):
        txt = tmp_path / f'{name}.txt'
        txt.write_text(
            preamble_text + '\n第一章 标题\n正文。\n',
            encoding='utf-8',
        )
        out = str(tmp_path / f'{name}.epub')
        conv = Txt2Epub(str(txt), out)
        conv.cover_path = str(tmp_path / 'missing.jpg')
        conv.convert()
        with zipfile.ZipFile(out) as z:
            return z.namelist()

    thr = _MIN_PREAMBLE_LEN
    # strip 后恰好等于阈值（两侧空白不计）→ 不生成序章
    names_eq = build('eq', '  ' + 'a' * thr + '  ')
    assert 'EPUB/xu.xhtml' not in names_eq
    # strip 后超过阈值 1 个字符 → 生成序章
    names_gt = build('gt', 'a' * (thr + 1))
    assert 'EPUB/xu.xhtml' in names_gt


def test_spine_without_cover(sample_txt, tmp_path):
    """封面缺失时 spine 不能引用 cover。"""
    from services import Txt2Epub
    out = tmp_path / 'no_cover.epub'
    conv = Txt2Epub(sample_txt, str(out))
    conv.cover_path = str(tmp_path / 'missing.jpg')
    conv.convert()
    with zipfile.ZipFile(str(out)) as z:
        opf = z.read('EPUB/content.opf').decode('utf-8')
    assert 'idref="cover"' not in opf


def test_spine_with_cover(sample_txt, tmp_path):
    """封面存在时 spine 应包含 cover（回归保护）。"""
    from services import Txt2Epub
    out = tmp_path / 'with_cover.epub'
    conv = Txt2Epub(sample_txt, str(out))
    conv.convert()  # 默认封面 resources/images/cover.jpeg 存在
    with zipfile.ZipFile(str(out)) as z:
        opf = z.read('EPUB/content.opf').decode('utf-8')
    assert 'idref="cover"' in opf


def test_preamble_in_toc(sample_txt, tmp_path):
    """序章必须出现在导航目录中。"""
    from services import Txt2Epub
    out = tmp_path / 'toc.epub'
    conv = Txt2Epub(sample_txt, str(out))
    conv.convert()
    with zipfile.ZipFile(str(out)) as z:
        nav = z.read('EPUB/nav.xhtml').decode('utf-8')
    assert '序章' in nav


def test_progress_completes(sample_txt, tmp_path):
    """最后一次进度上报应达到 total/total。"""
    from services import Txt2Epub
    conv = Txt2Epub(sample_txt, str(tmp_path / 'prog.epub'))
    calls = []
    conv.convert(progress=lambda c, t: calls.append((c, t)))
    assert calls
    assert calls[-1][0] == calls[-1][1]


def test_make_epub_variants(make_epub):
    """fixture 三种参数组合均能生成并回读 EPUB。"""
    from ebooklib import epub

    cases = [
        dict(name='cover.epub', with_cover=True),
        dict(name='images.epub', images=['images/a.png']),
        dict(name='chapters.epub', chapters=[('标题', '正文')]),
    ]
    for kwargs in cases:
        path = make_epub(**kwargs)
        book = epub.read_epub(path)
        assert book.get_metadata('DC', 'title')
