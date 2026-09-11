# MOBI->TXT 书籍信息显示功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 tab3 MOBI->TXT 选项卡中添加书籍信息显示功能，用于读取和显示加载的 MOBI 文件的书籍元数据。

**Architecture:** 使用 mobi 库的 MobiHeader 类提取 MOBI 文件的元数据，在 UI 层添加书籍信息卡片布局，支持自动和手动刷新。

**Tech Stack:** Python, PyQt6, mobi 库, BeautifulSoup

---

### Task 1: 添加书籍信息提取函数

**Files:**
- Modify: `services.py:837`
- Test: 手动测试（创建测试脚本）

- [ ] **Step 1: 在 services.py 末尾添加 extract_mobi_metadata 函数**

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
    metadata = {
        'title': '',
        'creator': '',
        'publisher': '',
        'description': '',
        'isbn': '',
        'language': '',
        'published': '',
        'subject': '',
        'cover_offset': None
    }
    
    try:
        from mobi.mobi_sectioner import Sectionizer
        from mobi.mobi_header import MobiHeader
        
        sect = Sectionizer(str(mobi_path))
        mobi_header = MobiHeader(sect, 0)
        exth_metadata = mobi_header.getMetaData()
        
        # 提取元数据字段
        metadata['title'] = exth_metadata.get('Title', [''])[0]
        metadata['creator'] = exth_metadata.get('Creator', [''])[0]
        metadata['publisher'] = exth_metadata.get('Publisher', [''])[0]
        metadata['description'] = exth_metadata.get('Description', [''])[0]
        metadata['isbn'] = exth_metadata.get('ISBN', [''])[0]
        metadata['language'] = exth_metadata.get('Language', [''])[0]
        metadata['published'] = exth_metadata.get('Published', [''])[0]
        metadata['subject'] = exth_metadata.get('Subject', [''])[0]
        
        # 提取封面偏移量
        if 'CoverOffset' in exth_metadata:
            metadata['cover_offset'] = int(exth_metadata['CoverOffset'][0])
            
    except Exception as e:
        logger.error(f'提取 MOBI 元数据失败: {e}')
    
    return metadata
```

- [ ] **Step 2: 测试函数基本功能**

创建测试脚本 `test_mobi_metadata.py`：
```python
from pathlib import Path
from services import extract_mobi_metadata

# 测试函数签名和返回值
def test_extract_mobi_metadata():
    # 使用一个存在的 MOBI 文件路径进行测试
    # 如果没有测试文件，可以测试空路径的情况
    result = extract_mobi_metadata(Path('nonexistent.mobi'))
    assert isinstance(result, dict)
    assert 'title' in result
    assert 'creator' in result
    print("测试通过")

if __name__ == '__main__':
    test_extract_mobi_metadata()
```

运行：`python test_mobi_metadata.py`
预期：测试通过

- [ ] **Step 3: 提交代码**

```bash
git add services.py test_mobi_metadata.py
git commit -m "feat: 添加 extract_mobi_metadata 函数用于提取 MOBI 文件元数据"
```

### Task 2: 添加封面提取函数

**Files:**
- Modify: `services.py:837`
- Test: 手动测试

- [ ] **Step 1: 在 services.py 末尾添加 extract_mobi_cover 函数**

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
    try:
        from mobi.mobi_sectioner import Sectionizer
        
        sect = Sectionizer(str(mobi_path))
        cover_data = sect.loadSection(cover_offset)
        return cover_data
    except Exception as e:
        logger.error(f'提取 MOBI 封面失败: {e}')
        return None
```

- [ ] **Step 2: 测试函数基本功能**

更新 `test_mobi_metadata.py`：
```python
from pathlib import Path
from services import extract_mobi_metadata, extract_mobi_cover

# 测试函数签名和返回值
def test_extract_mobi_metadata():
    result = extract_mobi_metadata(Path('nonexistent.mobi'))
    assert isinstance(result, dict)
    assert 'title' in result
    assert 'creator' in result
    print("extract_mobi_metadata 测试通过")

def test_extract_mobi_cover():
    # 测试空路径的情况
    result = extract_mobi_cover(Path('nonexistent.mobi'), 0)
    assert result is None
    print("extract_mobi_cover 测试通过")

if __name__ == '__main__':
    test_extract_mobi_metadata()
    test_extract_mobi_cover()
```

运行：`python test_mobi_metadata.py`
预期：测试通过

- [ ] **Step 3: 提交代码**

```bash
git add services.py test_mobi_metadata.py
git commit -m "feat: 添加 extract_mobi_cover 函数用于提取 MOBI 文件封面"
```

### Task 3: 修改 tab3 UI 布局

**Files:**
- Modify: `window.py:602-653`

- [ ] **Step 1: 在 _setup_tab3 方法中添加书籍信息组**

在 `_setup_tab3` 方法的 `# ---- 源文件 ----` 部分之前添加：

```python
        # ---- 书籍信息 ----
        grp = QGroupBox('书籍信息')
        gl = QHBoxLayout(grp)
        gl.setSpacing(10)
        
        # 封面图片
        self._lbl_cover = QLabel()
        self._lbl_cover.setFixedSize(120, 160)
        self._lbl_cover.setStyleSheet('border: 1px solid #ccc;')
        self._lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gl.addWidget(self._lbl_cover)
        
        # 信息字段
        info_layout = QGridLayout()
        info_layout.setSpacing(8)
        
        self._le_book_title = QLineEdit()
        self._le_book_title.setReadOnly(True)
        info_layout.addWidget(QLabel('标题:'), 0, 0)
        info_layout.addWidget(self._le_book_title, 0, 1)
        
        self._le_book_author = QLineEdit()
        self._le_book_author.setReadOnly(True)
        info_layout.addWidget(QLabel('作者:'), 0, 2)
        info_layout.addWidget(self._le_book_author, 0, 3)
        
        self._le_book_publisher = QLineEdit()
        self._le_book_publisher.setReadOnly(True)
        info_layout.addWidget(QLabel('出版商:'), 1, 0)
        info_layout.addWidget(self._le_book_publisher, 1, 1)
        
        self._le_book_isbn = QLineEdit()
        self._le_book_isbn.setReadOnly(True)
        info_layout.addWidget(QLabel('ISBN:'), 1, 2)
        info_layout.addWidget(self._le_book_isbn, 1, 3)
        
        self._le_book_language = QLineEdit()
        self._le_book_language.setReadOnly(True)
        info_layout.addWidget(QLabel('语言:'), 2, 0)
        info_layout.addWidget(self._le_book_language, 2, 1)
        
        self._le_book_published = QLineEdit()
        self._le_book_published.setReadOnly(True)
        info_layout.addWidget(QLabel('出版日期:'), 2, 2)
        info_layout.addWidget(self._le_book_published, 2, 3)
        
        gl.addLayout(info_layout)
        layout.addWidget(grp)
```

- [ ] **Step 2: 运行程序验证 UI 布局**

运行：`python main.py`
预期：tab3 中显示书籍信息组，包含封面图片区域和信息字段

- [ ] **Step 3: 提交代码**

```bash
git add window.py
git commit -m "feat: 在 tab3 中添加书籍信息卡片布局"
```

### Task 4: 实现自动提取书籍信息

**Files:**
- Modify: `window.py:1241-1249`

- [ ] **Step 1: 修改 _on_browse_mobi 方法**

```python
    def _on_browse_mobi(self):
        """浏览——选择 MOBI 文件，并自动生成 TXT 保存路径。"""
        path, _ = QFileDialog.getOpenFileName(
            self, '选择 MOBI 文件', '.', '*.mobi;;All Files(*)')
        if path:
            self._le_mobi.setText(path)
            d, fname = os.path.split(path)
            base, _ = os.path.splitext(fname)
            self._le_mobi_txt.setText(os.path.join(d, base + '.txt'))
            
            # 自动提取书籍信息
            self._load_mobi_metadata(path)
```

- [ ] **Step 2: 添加 _load_mobi_metadata 方法**

在 `_on_browse_mobi_txt` 方法之前添加：

```python
    def _load_mobi_metadata(self, mobi_path: str):
        """加载 MOBI 文件的书籍信息"""
        from services import extract_mobi_metadata, extract_mobi_cover
        
        metadata = extract_mobi_metadata(Path(mobi_path))
        
        # 填充信息字段
        self._le_book_title.setText(metadata.get('title', ''))
        self._le_book_author.setText(metadata.get('creator', ''))
        self._le_book_publisher.setText(metadata.get('publisher', ''))
        self._le_book_isbn.setText(metadata.get('isbn', ''))
        self._le_book_language.setText(metadata.get('language', ''))
        self._le_book_published.setText(metadata.get('published', ''))
        
        # 提取并显示封面
        cover_offset = metadata.get('cover_offset')
        if cover_offset is not None:
            cover_data = extract_mobi_cover(Path(mobi_path), cover_offset)
            if cover_data:
                pixmap = QPixmap()
                pixmap.loadFromData(cover_data)
                self._lbl_cover.setPixmap(pixmap.scaled(
                    120, 160, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                self._lbl_cover.setText('无封面')
        else:
            self._lbl_cover.setText('无封面')
```

- [ ] **Step 3: 添加必要的导入**

在 `window.py` 文件开头添加：

```python
from pathlib import Path
```

- [ ] **Step 4: 测试自动提取功能**

运行：`python main.py`
选择一个 MOBI 文件
预期：自动提取并显示书籍信息

- [ ] **Step 5: 提交代码**

```bash
git add window.py
git commit -m "feat: 选择 MOBI 文件后自动提取书籍信息"
```

### Task 5: 添加手动刷新按钮

**Files:**
- Modify: `window.py:602-653`

- [ ] **Step 1: 在书籍信息组中添加刷新按钮**

在 `info_layout` 定义之后添加：

```python
        # 刷新按钮
        btn_refresh = QPushButton('🔄 刷新信息')
        btn_refresh.setToolTip('重新提取 MOBI 文件的书籍信息')
        btn_refresh.clicked.connect(self._on_refresh_mobi_info)
        info_layout.addWidget(btn_refresh, 3, 0, 1, 4)
```

- [ ] **Step 2: 添加 _on_refresh_mobi_info 方法**

在 `_load_mobi_metadata` 方法之后添加：

```python
    def _on_refresh_mobi_info(self):
        """手动刷新 MOBI 文件的书籍信息"""
        mobi_path = self._le_mobi.text().strip()
        if not mobi_path or not os.path.exists(mobi_path):
            QMessageBox.warning(self, '提示', '请先选择有效的 MOBI 文件')
            return
        self._load_mobi_metadata(mobi_path)
```

- [ ] **Step 3: 测试手动刷新功能**

运行：`python main.py`
选择一个 MOBI 文件，点击"刷新信息"按钮
预期：重新提取并显示书籍信息

- [ ] **Step 4: 提交代码**

```bash
git add window.py
git commit -m "feat: 添加刷新书籍信息按钮"
```

### Task 6: 重置功能集成

**Files:**
- Modify: `window.py:1282-1287`

- [ ] **Step 1: 修改 _on_reset_tab3 方法**

```python
    def _on_reset_tab3(self):
        """重置 tab3 的所有输入。"""
        self._le_mobi.clear()
        self._le_mobi_txt.clear()
        self._le_book_title.clear()
        self._le_book_author.clear()
        self._le_book_publisher.clear()
        self._le_book_isbn.clear()
        self._le_book_language.clear()
        self._le_book_published.clear()
        self._lbl_cover.clear()
        self._lbl_cover.setText('')
        logger.info('tab3 重置')
```

- [ ] **Step 2: 测试重置功能**

运行：`python main.py`
选择 MOBI 文件，点击"重置"按钮
预期：所有字段清空

- [ ] **Step 3: 提交代码**

```bash
git add window.py
git commit -m "feat: 集成书籍信息重置功能"
```

### Task 7: 清理和最终测试

**Files:**
- Test: 手动测试

- [ ] **Step 1: 删除测试文件**

```bash
rm test_mobi_metadata.py
```

- [ ] **Step 2: 完整功能测试**

运行：`python main.py`
1. 测试选择 MOBI 文件后自动提取书籍信息
2. 测试手动刷新功能
3. 测试重置功能
4. 测试转换功能（确保不影响原有功能）

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: 完成 MOBI->TXT 书籍信息显示功能"
```

## 执行说明

1. 每个任务完成后运行程序验证
2. 遇到问题及时修复
3. 保持代码风格与项目一致
4. 使用中文注释
5. 遵循项目的错误处理规范