# -*- coding: utf-8 -*-
"""
TxtPress — 全局常量定义。

集中管理资源路径和默认值常量，避免在多个模块中重复定义。
所有模块从这里导入常量，确保一致性。
"""

from __future__ import annotations

import os

# ---- 路径常量 ----
# BASE_DIR: 项目根目录，用于定位资源文件和配置文件
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.path.join(BASE_DIR, 'resources', 'images')
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
DEFAULT_COVER = os.path.join(RES_DIR, 'cover.jpeg')
STYLES_DIR = os.path.join(BASE_DIR, 'styles')

# ---- 默认值常量 ----
# 当用户未填写时使用的默认值
DEFAULT_AUTHOR = 'etony.an@gmail.com'
DEFAULT_DESC = '原始内容源于互联网，仅供个人学习娱乐使用。'
DEFAULT_ID = 'id_etony.an@gmail.com'

# ---- 章节正则预设 ----
REGEX_PRESETS = {
    '中文标准（第X章）': r'^\s*([第卷][0123456789一二三四五六七八九十零〇百千两]*[章回部节集卷].*)\s*',
    '数字编号（Chapter X）': r'^\s*(Chapter\s+\d+.*)\s*$',
    '数字编号（第X节）': r'^\s*(第\d+节.*)\s*$',
    '卷+章': r'^\s*(卷[一二三四五六七八九十\d]+.*)\s*$',
    '自定义（用户输入）': '',
}

# ---- EPUB 字体预设 ----
FONT_PRESETS = {
    '宋体': 'SimSun, "Song Ti", serif',
    '黑体': 'SimHei, "Hei Ti", sans-serif',
    '微软雅黑': '"Microsoft YaHei", sans-serif',
    '楷体': 'KaiTi, "Kai Ti", serif',
    '仿宋': 'FangSong, "Fang Song", serif',
    '思源宋体': '"Source Han Serif SC", "Noto Serif CJK SC", serif',
    '思源黑体': '"Source Han Sans SC", "Noto Sans CJK SC", sans-serif',
    '霞鹜文楷': '"LXGW WenKai", serif',
}

# ---- 目录样式预设 ----
TOC_STYLES = {
    '默认': 'square',
    '圆点': 'disc',
    '圆圈': 'circle',
    '无标记': 'none',
    '数字': 'decimal',
}
