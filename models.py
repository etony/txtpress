# -*- coding: utf-8 -*-
"""
TxtPress — 数据模型，类型安全的 dataclass，替代裸 dict。

为什么要用 dataclass？
- 字段类型明确，写代码时有自动补全
- 比 dict 更安全，拼写错误会在 IDE 中直接标红
- 配合 fields() / asdict() 可以方便地序列化

BookInfo   EPUB 元信息（书名、作者、日期等）
AppConfig  用户偏好配置（上次选了什么编码、正则等）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path
from typing import Optional


@dataclass
class BookInfo:
    """
    EPUB 书籍的元数据。

    这些信息会写入 EPUB 文件的 OPF 元数据区，
    电子书阅读器（如 Kindle、多看）会读取并显示。
    cover 是封面图片的二进制数据，单独从 EPUB 提取。
    """
    title: str = '未知'              # dc:title
    creator: str = ''                # dc:creator（作者）
    contributor: str = ''            # dc:contributor（贡献者）
    date: str = ''                   # dc:date（出版/创建日期）
    description: str = ''            # dc:description（描述/简介）
    cover: Optional[bytes] = None    # 封面图片的二进制数据


@dataclass
class AppConfig:
    """
    用户偏好配置，通过 config.json 持久化。

    load() 和 save() 实现了配置的读写。
    每次启动时加载，关闭时自动保存。
    这样用户上次选的编码、正则表达式等设置都会保持。
    """
    txt_encoding: str = 'utf-8'   # TXT→EPUB 时用的文件编码
    out_encoding: str = 'utf-8'   # EPUB→TXT 时用的输出编码
    chapter_sep: str = ''          # 章节之间的分隔符
    chapter_regex: str = (         # 匹配章节标题的正则
        r'^\s*([第卷][0123456789一二三四五六七八九十零〇百千两]*[章回部节集卷].*)\s*'
    )
    fanjian_enabled: bool = False  # 是否开启繁→简转换

    @classmethod
    def load(cls, path: str | Path) -> AppConfig:
        """
        从 JSON 文件加载配置。

        如果文件不存在，返回全部默认值。
        如果 JSON 里有 dataclass 不认识的字段（比如手动编辑 config.json 加的），
        会自动忽略掉，不会报错。
        """
        if not os.path.exists(path):
            return cls()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # fields(cls) 返回 dataclass 定义的所有字段名，
        # 只保留这些字段，多余的扔掉。
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    def save(self, path: str | Path) -> None:
        """
        保存配置到 JSON 文件。

        ensure_ascii=False 让中文正常显示，而不是转成 \\uXXXX。
        indent=2 让 JSON 文件可读性更好，方便手动查看。
        """
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
