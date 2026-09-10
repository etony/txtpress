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

# ---- 默认值常量 ----
# 当用户未填写时使用的默认值
DEFAULT_AUTHOR = 'etony.an@gmail.com'
DEFAULT_DESC = '原始内容源于互联网，仅供个人学习娱乐使用。'
DEFAULT_ID = 'id_etony.an@gmail.com'
