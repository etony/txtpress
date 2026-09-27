# -*- coding: utf-8 -*-
"""通用工具函数。"""
from __future__ import annotations

import os
import subprocess
import sys

from loguru import logger


def open_dir(dirname: str):
    """跨平台打开文件管理器。

    各平台的命令：
    - Windows: os.startfile()（内置，不需要 subprocess）
    - macOS:   open 命令
    - Linux:   xdg-open 命令（大多数桌面环境预装）

    为什么不直接用 Python 的 webbrowser 模块？
    webbrowser.open('file:///path') 在某些系统上会打开浏览器而不是文件管理器。
    """
    if not dirname:
        return
    logger.info(f'打开目录: {dirname}')
    if sys.platform == 'win32':
        os.startfile(dirname)
    elif sys.platform == 'darwin':
        subprocess.run(['open', dirname], check=False)
    else:
        subprocess.run(['xdg-open', dirname], check=False)
