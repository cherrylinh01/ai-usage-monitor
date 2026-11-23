"""Vẽ giao diện 296x128 (Claude | Gemini) từ cache/*.json -> preview.png (3 màu: trắng/đen/đỏ)."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT_PATH = ROOT / "fonts" / "PressStart2P-Regular.ttf"
CACHE_DIR = ROOT / "cache"

W, H = 296, 128
WHITE, BLACK, RED = (255, 255, 255), (0, 0, 0), (255, 0, 0)
RED_THRESHOLD = 80   # % >= ngưỡng này thì tô đỏ
STALE_HOURS = 2      # dữ liệu cũ hơn bao nhiêu giờ thì hiện dấu "!" đỏ
GEMINI_PLAN = None   # tên gói Gemini giờ lấy tự động từ cache; gõ tay ở đây chỉ khi cần ghi đè

F8 = ImageFont.truetype(str(FONT_PATH), 8)    # chỉ dùng bội số của 8 -> nét đều
F24 = ImageFont.truetype(str(FONT_PATH), 24)

# ---------- Icon pixel: '#' = pixel tô màu, '.' = trống ----------
CLAUDE_ICON = """
.......#.......
.......#.......
..#....#....#..
...#...#...#...
....#..#..#....
.....#.#.#.....
......###......
###############
......###......
.....#.#.#.....
....#..#..#....
...#...#...#...
..#....#....#..
.......#.......
.......#.......
"""

GEMINI_ICON = """
.......#.......
.......#.......
.......#.......
......###......
......###......
.....#####.....
...#########...
###############
...#########...
.....#####.....
......###......
......###......
.......#.......
.......#.......
.......#.......
"""

RESET_ICON = """
.###.#.
#...##.
#..###.
#......
#.....#
#.....#
.#####.
"""


def draw_icon(d: ImageDraw.ImageDraw, x: int, y: int, art: str, color) -> None:
    """Vẽ icon từ chuỗi ký tự, mỗi '#' là 1 pixel."""
    for row, line in enumerate(art.strip().splitlines()):
        for col, ch in enumerate(line):
            if ch == "#":
                d.point((x + col, y + row), fill=color)


# ---------- Dữ liệu ----------
def load(name: str) -> dict | None:
    try:
        return json.loads((CACHE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_stale(data: dict | None) -> bool:
    if not data or data.get("stale") or not data.get("fetched_at"):
        return True
    age = datetime.now(timezone.utc) - datetime.fromisoformat(data["fetched_at"])
    return age > timedelta(hours=STALE_HOURS)


def effective(block: dict | None) -> tuple[int | None, datetime | None]:
    """Trả (percent, giờ reset theo giờ máy). Nếu cửa sổ ĐÃ reset -> coi như 0%."""
    block = block or {}
    pct, reset = block.get("percent"), block.get("resets_at")
    reset_dt = datetime.fromisoformat(reset).astimezone() if reset else None
    if reset_dt:
        # API trả giờ reset "rung" quanh mốc phút (04:59:59.6 lúc này, 05:00:00.2 lúc khác).
        # Làm tròn về phút gần nhất để ảnh không đổi vô cớ -> không refresh thẻ thừa (tốn pin).
        reset_dt = (reset_dt + timedelta(seconds=30)).replace(second=0, microsecond=0)
    if reset_dt and reset_dt <= datetime.now().astimezone():
        return 0, None
    return pct, reset_dt


# ---------- Vẽ ----------
def text_w(text: str, font) -> int:
    return round(font.getlength(text))


def draw_row(d, x0: int, y: int, label: str, block: dict | None) -> None:
    pct, reset_dt = effective(block)
    color = RED if (pct is not None and pct >= RED_THRESHOLD) else BLACK

    # Dòng 1: nhãn bên trái, icon reset + giờ reset căn phải
    d.text((x0 + 8, y), label, font=F8, fill=BLACK)
    reset_txt = reset_dt.strftime("%H:%M %d/%m") if reset_dt else "--:-- --/--"
    rx = x0 + 140 - text_w(reset_txt, F8)
    draw_icon(d, rx - 10, y, RESET_ICON, BLACK)
    d.text((rx, y), reset_txt, font=F8, fill=BLACK)

    # Dòng 2: % cỡ lớn
    d.text((x0 + 8, y + 11), f"{pct}%" if pct is not None else "--%", font=F24, fill=color)

    # Dòng 3: thanh tiến trình
    bx0, by0, bx1, by1 = x0 + 8, y + 38, x0 + 140, y + 43
    d.rectangle((bx0, by0, bx1, by1), outline=BLACK)
    if pct:
        fill_w = round((bx1 - bx0 - 2) * min(pct, 100) / 100)
        if fill_w > 0:
            d.rectangle((bx0 + 1, by0 + 1, bx0 + fill_w, by1 - 1), fill=color)


def draw_badge(d, x_right: int, y: int, text: str) -> None:
    """Nhãn chữ trắng trên nền đen, căn phải tại x_right."""
    w = text_w(text, F8) + 4
    d.rectangle((x_right - w, y - 2, x_right, y + 9), fill=BLACK)
    d.text((x_right - w + 2, y), text, font=F8, fill=WHITE)


def draw_column(d, x0: int, name: str, icon: str, icon_color, data: dict | None,
                default_plan: str | None = None) -> None:
    d.rounded_rectangle((x0 + 2, 2, x0 + 145, 125), radius=6, outline=BLACK, width=2)
    draw_icon(d, x0 + 8, 6, icon, icon_color)
    d.text((x0 + 28, 10), name, font=F8, fill=BLACK)
    plan = (data or {}).get("plan") or default_plan
    if plan:
        draw_badge(d, x0 + 127, 10, plan[:5])  # tối đa 5 ký tự để không đè lên tên
    if is_stale(data):
        d.text((x0 + 130, 10), "!", font=F8, fill=RED)
    d.line((x0 + 6, 24, x0 + 141, 24), fill=BLACK)
    data = data or {}
    draw_row(d, x0, 28, "5H", data.get("session"))
    draw_row(d, x0, 76, "7D", data.get("weekly"))


def render(claude: dict | None, gemini: dict | None) -> Image.Image:
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"  # TẮT khử răng cưa: chỉ đen/trắng/đỏ, không pixel xám
    draw_column(d, 0, "CLAUDE", CLAUDE_ICON, RED, claude)
    draw_column(d, 148, "GEMINI", GEMINI_ICON, BLACK, gemini, default_plan=GEMINI_PLAN)
    return img


def demo_data() -> tuple[dict, dict]:
    """Dữ liệu giả để thử màu đỏ và trường hợp 100%."""
    now = datetime.now(timezone.utc)
    soon, later = (now + timedelta(hours=3)).isoformat(), (now + timedelta(days=3)).isoformat()
    def make(s, w):
        return {"session": {"percent": s, "resets_at": soon}, "weekly": {"percent": w, "resets_at": later},
                "fetched_at": now.isoformat(), "stale": False}
    claude, gemini = make(85, 38), make(100, 52)
    claude["plan"], gemini["plan"] = "MAX20", "ULTRA"   # thử nhãn dài nhất
    return claude, gemini


if __name__ == "__main__":
    claude, gemini = demo_data() if "--demo" in sys.argv else (load("claude"), load("gemini"))
    img = render(claude, gemini)
    img.save(ROOT / "preview.png")
    img.resize((W * 3, H * 3), Image.NEAREST).save(ROOT / "preview_x3.png")
    colors = sorted(c for _, c in img.getcolors(maxcolors=4096))
    print(f"Đã lưu preview.png | số màu: {len(colors)} -> {colors}")
