# -*- coding: utf-8 -*-
"""
TxtPress — Windows 无控制台启动入口。

双击此文件可直接启动程序（不显示控制台窗口）。
实际逻辑委托给 main.py 中的 main() 函数。

用法：
    python main.pyw
"""

from main import main

if __name__ == '__main__':
    main()
