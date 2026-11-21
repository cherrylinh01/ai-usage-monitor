"""Thử font pixel: so sánh vẽ CÓ và KHÔNG khử răng cưa."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = ROOT / "fonts" / "PressStart2P-Regular.ttf"
W, H = 296, 128

img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)

y = 4
for size in (8, 12, 16, 24):            # 12 KHÔNG phải bội số của 8 -> để so sánh
    font = ImageFont.truetype(str(FONT), size)
    d.fontmode = "L"                    # bật khử răng cưa (mặc định) -> sinh pixel xám
    d.text((4, y), f"38% {size}", font=font, fill="black")
    d.fontmode = "1"                    # tắt khử răng cưa -> chỉ đen/trắng
    d.text((152, y), f"38% {size}", font=font, fill="black")
    y += size + 8

img.save(ROOT / "font_test.png")
img.resize((W * 4, H * 4), Image.NEAREST).save(ROOT / "font_test_x4.png")  # phóng to, giữ pixel vuông

colors = img.getcolors(maxcolors=4096)
print(f"Ảnh có {len(colors)} màu khác nhau (lý tưởng cho E-ink: 2–3 màu)")