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
