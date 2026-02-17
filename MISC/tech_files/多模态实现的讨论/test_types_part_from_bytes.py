# =============================================================
# 测试脚本：验证 google.genai.types.Part 图片构造方式
# =============================================================
#
# 背景：
#   在多模态升级实现中，原方案使用 types.Part.from_data() 来构造
#   图片 Part 对象，但实际运行时发现该方法不存在 (AttributeError)。
#
# 结论：
#   - types.Part.from_data()   --> 不存在，会抛出 AttributeError
#   - types.Part.from_bytes()  --> 正确方式，经验证可用
#   - types.Part(inline_data=types.Blob(...)) --> 也可用，但更冗长
#
# 最终采用 types.Part.from_bytes(data=..., mime_type=...) 方式
# =============================================================

from google.genai import types

# 方式1：from_bytes（推荐，简洁）
p1 = types.Part.from_bytes(data=b'test_image_bytes', mime_type='image/png')
print(f"[from_bytes] Type: {type(p1)}")
print(f"[from_bytes] Part: {p1}")
print()

# 方式2：inline_data + Blob（等效，更冗长）
p2 = types.Part(inline_data=types.Blob(data=b'test_image_bytes', mime_type='image/png'))
print(f"[inline_data] Type: {type(p2)}")
print(f"[inline_data] Part: {p2}")
print()

# 方式3：from_data（不存在，取消注释会报错）
# p3 = types.Part.from_data(data=b'test', mime_type='image/png')  # AttributeError!

print("ALL TESTS PASSED")
