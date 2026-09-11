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