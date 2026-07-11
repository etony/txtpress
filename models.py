# -*- coding: utf-8 -*-
"""
TxtPress — 数据模型，类型安全的 dataclass，替代裸 dict。

为什么要用 dataclass？
- 字段类型明确，写代码时有自动补全
- 比 dict 更安全，拼写错误会在 IDE 中直接标红
- 配合 fields() / asdict() 可以方便地序列化和反序列化
- 自带 __init__ / __repr__ / __eq__，省去模板代码

设计思路：
  BookInfo  = 一本书的元数据，在 EPUB 的 OPF 文件和 UI 之间传递
  AppConfig = 用户偏好，通过 JSON 持久化，下次启动自动恢复
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Optional


@dataclass
class BookInfo:
    """
    EPUB 书籍的元数据。

    这些信息会写入 EPUB 文件的 OPF 元数据区，
    电子书阅读器（如 Kindle、多看）会读取并显示。
    cover 是封面图片的二进制数据，单独从 EPUB 提取。

    dataclass 自动生成 __init__，所以可以直接写：
        info = BookInfo(title='百年孤独', creator='马尔克斯')

    字段默认值让某些字段可以留空（如 contributor 不填也没关系）。
    """
    title: str = '未知'              # dc:title（书名）
    creator: str = ''                # dc:creator（作者）
    contributor: str = ''            # dc:contributor（贡献者，如编辑、译者）
    date: str = ''                   # dc:date（出版/创建日期，ISO 格式）
    description: str = ''            # dc:description（描述/简介）
    cover: Optional[bytes] = None    # 封面图片的二进制数据（不是路径，是文件内容）


@dataclass
class AppConfig:
    """
    用户偏好配置，通过 config.json 持久化。

    load() 和 save() 实现了配置的读写。
    每次启动时加载，关闭时自动保存。
    这样用户上次选的编码、正则表达式等设置都会保持。

    为什么不用 QSettings？
      QSettings 存储位置由操作系统决定（注册表/plist），
      不利于手动查看和备份。JSON 文件更透明。
    """
    txt_encoding: int = 0          # TXT→EPUB 时用的文件编码（ComboBox index，0=自动检测）
    out_encoding: str = 'utf-8'    # EPUB→TXT 时用的输出编码
    chapter_sep: str = ''          # 章节之间的分隔符
    chapter_regex: str = ''        # 匹配章节标题的正则（空=使用 services.DEFAULT_CHAPTER_REGEX）
    fanjian_enabled: bool = False  # 是否开启繁→简转换

    @classmethod
    def load(cls, path: str | Path) -> AppConfig:
        """
        从 JSON 文件加载配置。

        如果文件不存在，返回全部默认值。
        如果 JSON 里有 dataclass 不认识的字段（比如手动编辑 config.json 加的），
        会自动忽略掉，不会报错。

        用法：
            cfg = AppConfig.load('config.json')

        要点：
          - fields(cls) 是 dataclass 提供的反射方法，返回所有字段定义
          - 用字段名集合做白名单过滤，避免脏数据
          - cls(**filtered) 解包字典创建实例，比手动逐字段赋值简洁
        """
        if not os.path.exists(path):
            return cls()
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # fields(cls) 返回 dataclass 定义的所有字段名，
        # 只保留这些字段，多余的扔掉（安全的配置加载策略）。
        valid_keys = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        # 兼容旧配置：txt_encoding 从字符串迁移为 int
        if isinstance(filtered.get('txt_encoding'), str):
            filtered['txt_encoding'] = 0
        return cls(**filtered)

    def save(self, path: str | Path) -> None:
        """
        保存配置到 JSON 文件。

        asdict(self) 把 dataclass 转为普通 dict（递归转换）。
        ensure_ascii=False 让中文正常显示，而不是转成 \\uXXXX。
        indent=2 让 JSON 文件可读性更好，方便手动查看和调试。
        """
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
