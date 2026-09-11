# -*- coding: utf-8 -*-
"""
错误处理模块 - 提供用户友好的错误提示
"""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget


# 错误码到友好提示的映射
ERROR_MESSAGES = {
    # 文件相关
    'file_not_found': '文件不存在，请检查路径是否正确',
    'file_permission': '没有权限访问该文件，请检查文件权限',
    'file_encoding': '文件编码识别失败，请手动选择正确的编码',
    'file_corrupted': '文件已损坏或格式不正确',
    
    # EPUB相关
    'epub_read_failed': '无法读取EPUB文件，文件可能已损坏',
    'epub_write_failed': '保存EPUB文件失败，请检查磁盘空间和写入权限',
    'epub_invalid': '不是有效的EPUB文件格式',
    
    # MOBI相关
    'mobi_read_failed': '无法读取MOBI文件，文件可能已损坏',
    'mobi_no_html': 'MOBI文件中未找到可提取的HTML内容',
    
    # 转换相关
    'regex_invalid': '正则表达式格式错误，请检查语法',
    'conversion_failed': '转换过程中发生错误',
    'chapter_not_found': '未找到匹配的章节标题',
    
    # 封面相关
    'cover_not_found': '未找到封面图片',
    'cover_format_unsupported': '不支持的图片格式，请使用JPG或PNG',
    
    # 磁盘相关
    'disk_full': '磁盘空间不足，请清理后重试',
    'output_path_invalid': '输出路径无效，请选择有效目录',
    
    # 输入相关
    'input_required': '请先填写必要信息',
    'path_invalid': '路径无效，请检查输入',
}


def get_error_message(error_code: str, detail: str = '') -> str:
    """
    获取用户友好的错误提示信息
    
    Args:
        error_code: 错误码
        detail: 额外的错误详情（可选）
    
    Returns:
        友好的错误提示信息
    """
    base_msg = ERROR_MESSAGES.get(error_code, '发生了未知错误')
    if detail:
        return f'{base_msg}\n\n详细信息: {detail}'
    return base_msg


def show_error(parent: QWidget, title: str, error_code: str, detail: str = ''):
    """
    显示用户友好的错误对话框
    
    Args:
        parent: 父窗口
        title: 对话框标题
        error_code: 错误码
        detail: 额外的错误详情（可选）
    """
    msg = get_error_message(error_code, detail)
    QMessageBox.critical(parent, title, msg)


def show_warning(parent: QWidget, title: str, error_code: str, detail: str = ''):
    """
    显示用户友好的警告对话框
    """
    msg = get_error_message(error_code, detail)
    QMessageBox.warning(parent, title, msg)


def show_info(parent: QWidget, title: str, message: str):
    """
    显示信息提示对话框
    """
    QMessageBox.information(parent, title, message)
