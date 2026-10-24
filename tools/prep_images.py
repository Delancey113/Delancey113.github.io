"""一次性图片处理脚本：压缩示例配图并生成 favicon。
用法：python tools/prep_images.py
"""
import os
from PIL import Image

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "source", "img")


def to_jpg(name_in, name_out, max_width, quality=82):
    src = os.path.join(BASE, name_in)
    if not os.path.exists(src):
        print(f"  跳过（不存在）: {name_in}")
        return
    im = Image.open(src).convert("RGB")
    if im.width > max_width:
        h = round(im.height * max_width / im.width)
        im = im.resize((max_width, h), Image.LANCZOS)
    dst = os.path.join(BASE, name_out)
    im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    size_kb = os.path.getsize(dst) / 1024
    print(f"  {name_out}  {im.width}x{im.height}  {size_kb:.0f} KB")


def square(name_in, name_out, size):
    src = os.path.join(BASE, name_in)
    if not os.path.exists(src):
        print(f"  跳过（不存在）: {name_in}")
        return
    im = Image.open(src).convert("RGBA")
    im = im.resize((size, size), Image.LANCZOS)
    dst = os.path.join(BASE, name_out)
    im.save(dst, "PNG", optimize=True)
    print(f"  {name_out}  {size}x{size}  {os.path.getsize(dst)/1024:.0f} KB")


print("压缩横幅与封面：")
to_jpg("index-banner.png", "index-banner.jpg", 1920)
to_jpg("default-cover.png", "default-cover.jpg", 1200)
to_jpg("post-cover-1.png", "post-cover-1.jpg", 1200)
to_jpg("post-cover-2.png", "post-cover-2.jpg", 1200)

print("生成头像与图标：")
square("avatar.png", "avatar.png", 300)
square("avatar.png", "favicon.png", 128)

# 清理原始大图
for f in ["default-cover.png", "post-cover-1.png", "post-cover-2.png"]:
    p = os.path.join(BASE, f)
    if os.path.exists(p):
        os.remove(p)
        print(f"  已删除原始大图：{f}")

print("完成。")
