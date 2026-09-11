# MOBI->TXT 书籍信息显示功能设计文档

## 概述

在 tab3 MOBI->TXT 选项卡中添加书籍信息显示功能，用于读取和显示加载的 MOBI 文件的书籍元数据。

## 需求

1. **书籍信息字段**：显示详细信息，包括标题、作者、出版日期、语言、出版商、ISBN、描述等
2. **显示时机**：选择文件后自动显示，同时提供手动刷新按钮
3. **显示位置**：在 tab3 顶部独立区域显示
4. **显示格式**：可编辑字段，允许用户修改
5. **封面图片**：显示 MOBI 文件的封面图片

## 技术方案

### 1. 书籍信息提取函数

**位置**：`services.py`

**函数签名**：
```python
def extract_mobi_metadata(mobi_path: Path) -> dict:
    """
    从 MOBI 文件中提取书籍元数据。

    Args:
        mobi_path: MOBI 文件路径

    Returns:
        包含书籍信息的字典，字段包括：
        - title: 书名
        - creator: 作者
        - publisher: 出版商
        - description: 描述
        - isbn: ISBN
        - language: 语言
        - published: 出版日期
        - subject: 主题
        - cover_offset: 封面图片偏移量（用于提取封面）
    """
```

**实现步骤**：
1. 使用 `mobi.mobi_sectioner.Sectionizer` 读取 MOBI 文件
2. 使用 `mobi.mobi_header.MobiHeader` 解析文件头
3. 调用 `getMetaData()` 获取元数据字典
4. 提取并格式化所需字段
5. 返回标准化的书籍信息字典

**错误处理**：
- 文件不存在：返回空字典
- 文件格式错误：返回空字典并记录日志
- 元数据缺失：使用默认值（空字符串）

### 2. 封面提取函数

**位置**：`services.py`

**函数签名**：
```python
def extract_mobi_cover(mobi_path: Path, cover_offset: int) -> Optional[bytes]:
    """
    从 MOBI 文件中提取封面图片。

    Args:
        mobi_path: MOBI 文件路径
        cover_offset: 封面图片偏移量

    Returns:
        封面图片的二进制数据，如果提取失败返回 None
    """
```

### 3. UI 布局

**位置**：`window.py` 的 `_setup_tab3` 方法

**布局结构**：
1. 在源文件组上方添加书籍信息组
2. 使用卡片式布局：左侧封面图片，右侧信息字段
3. 信息字段使用网格布局排列

**新增控件**：
- `self._lbl_cover`: 封面图片显示标签
- `self._le_book_title`: 书名输入框
- `self._le_book_author`: 作者输入框
- `self._le_book_publisher`: 出版商输入框
- `self._le_book_isbn`: ISBN 输入框
- `self._le_book_language`: 语言输入框
- `self._le_book_published`: 出版日期输入框
- `self._le_book_description`: 描述文本框

### 4. 交互逻辑

1. **自动提取**：选择 MOBI 文件后，自动调用 `extract_mobi_metadata` 提取信息
2. **手动刷新**：添加"刷新信息"按钮，支持手动重新提取
3. **封面显示**：提取封面偏移量后，调用 `extract_mobi_cover` 获取封面图片
4. **信息编辑**：允许用户修改书籍信息字段

## 实现步骤

1. 在 `services.py` 中添加 `extract_mobi_metadata` 函数
2. 在 `services.py` 中添加 `extract_mobi_cover` 函数
3. 在 `window.py` 的 `_setup_tab3` 方法中添加书籍信息组
4. 修改 `_on_browse_mobi` 方法，选择文件后自动提取信息
5. 添加"刷新信息"按钮及其事件处理
6. 实现封面图片显示逻辑

## 测试策略

1. 测试 `extract_mobi_metadata` 函数对不同 MOBI 文件的兼容性
2. 测试封面提取功能
3. 测试 UI 交互逻辑
4. 测试错误处理情况

## 注意事项

1. MOBI 文件格式复杂，不同文件的元数据字段可能不同
2. 封面提取可能失败，需要优雅处理
3. 保持现有功能的兼容性
4. 遵循项目的代码风格和约定