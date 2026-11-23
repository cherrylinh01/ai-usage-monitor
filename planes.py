"""Tách ảnh 3 màu thành 2 lớp (Đen, Đỏ) và đóng gói thành dãy byte cho màn E-ink."""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "out"

# ---------- Cấu hình phụ thuộc PHẦN CỨNG – đã kiểm chứng với thẻ AESL029FC (nRF52810) ----------
# Firmware 2.9" lưu ảnh THEO CỘT, bắt đầu từ cột bên phải; tương đương xoay 90° (ngược chiều kim
# đồng hồ) rồi đọc theo hàng. Đã so khớp từng byte với hàm canvas2bytes_bw của trang web shop.
ROTATE = 90
BLACK_BIT_IS_1 = False  # lớp đen: bit 0 = ĐEN, 1 = trắng/đỏ
RED_BIT_IS_1 = False    # lớp đỏ: bit 0 = ĐỎ, 1 = không đỏ (firmware này đảo so với thông lệ)


def split_planes(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Ảnh RGB -> 2 mặt nạ mode '1' (pixel bật = có mực). Đỏ được ưu tiên hơn đen."""
    img = img.convert("RGB")
    if ROTATE:
        img = img.rotate(ROTATE, expand=True)   # expand=True: 296x128 -> 128x296
    w, h = img.size
    black, red = Image.new("1", (w, h), 0), Image.new("1", (w, h), 0)
    src, bp, rp = img.load(), black.load(), red.load()
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            is_red = r > 128 and g < 128 and b < 128
            is_black = not is_red and (r + g + b) < 384
            bp[x, y] = 255 if is_black else 0
            rp[x, y] = 255 if is_red else 0
    return black, red


def pack(mask: Image.Image, on_bit_is_1: bool) -> bytes:
    """Gói 8 pixel ngang thành 1 byte. Pixel trái nhất = bit cao nhất (MSB). Đi từng hàng, trên xuống."""
    w, h = mask.size
    assert w % 8 == 0, "chiều rộng phải chia hết cho 8"
    px = mask.load()
    out = bytearray()
    for y in range(h):
        for x0 in range(0, w, 8):
            byte = 0
            for bit in range(8):
                on = px[x0 + bit, y] != 0
                if on == on_bit_is_1:
                    byte |= 0x80 >> bit      # 0x80 = 1000_0000, dịch phải 'bit' vị trí
            out.append(byte)
    return bytes(out)


def unpack_to_rgb(black_bytes: bytes, red_bytes: bytes, w: int, h: int) -> Image.Image:
    """Làm ngược: từ 2 dãy byte dựng lại ảnh RGB – để KIỂM TRA việc đóng gói có đúng không."""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    px = img.load()
    for i in range(w * h):
        byte_i, bit = divmod(i, 8)
        mask = 0x80 >> bit
        is_black = bool(black_bytes[byte_i] & mask) == BLACK_BIT_IS_1
        is_red = bool(red_bytes[byte_i] & mask) == RED_BIT_IS_1
        x, y = i % w, i // w
        px[x, y] = (255, 0, 0) if is_red else (0, 0, 0) if is_black else (255, 255, 255)
    return img


if __name__ == "__main__":
    src = Image.open(ROOT / "preview.png").convert("RGB")
    black, red = split_planes(src)
    black_bytes, red_bytes = pack(black, BLACK_BIT_IS_1), pack(red, RED_BIT_IS_1)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "black.bin").write_bytes(black_bytes)
    (OUT_DIR / "red.bin").write_bytes(red_bytes)

    # Ảnh minh hoạ 2 lớp xếp chồng: trên = lớp đen, dưới = lớp đỏ (pixel bật hiện màu đen)
    w, h = black.size
    sheet = Image.new("1", (w, h * 2 + 4), 1)
    sheet.paste(black.point(lambda v: 0 if v else 255), (0, 0))
    sheet.paste(red.point(lambda v: 0 if v else 255), (0, h + 4))
    sheet.resize((w * 3, (h * 2 + 4) * 3), Image.NEAREST).save(OUT_DIR / "planes_x3.png")

    # Kiểm tra khứ hồi: byte -> ảnh phải giống HỆT ảnh gốc (sau khi xoay nếu có)
    expected = src.rotate(ROTATE, expand=True) if ROTATE else src
    rebuilt = unpack_to_rgb(black_bytes, red_bytes, w, h)
    same = rebuilt.tobytes() == expected.tobytes()

    print(f"Kích thước lớp : {w}x{h} pixel -> {w // 8} byte/hàng x {h} hàng")
    print(f"black.bin      : {len(black_bytes)} byte | 8 byte đầu: {black_bytes[:8].hex(' ')}")
    print(f"red.bin        : {len(red_bytes)} byte | 8 byte đầu: {red_bytes[:8].hex(' ')}")
    print(f"Pixel đen/đỏ   : {black.histogram()[255]} / {red.histogram()[255]}")  # mode '1': ô 255 = pixel bật
    print(f"Kiểm tra khứ hồi (byte -> ảnh == ảnh gốc): {'ĐÚNG ✅' if same else 'SAI ❌'}")
