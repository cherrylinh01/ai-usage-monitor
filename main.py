"""Chạy 1 vòng: lấy dữ liệu -> vẽ -> tách lớp -> gửi BLE (chỉ khi ảnh thay đổi).

Task Scheduler (Windows) gọi file này định kỳ bằng pythonw.exe (không có cửa sổ).
Cờ dòng lệnh:
  --force    gửi lên thẻ kể cả khi ảnh không đổi
  --no-ble   chỉ vẽ + tách lớp, không gửi (dùng khi chưa có thẻ)
"""
import hashlib
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
OUT_DIR = ROOT / "out"
LAST_SENT = OUT_DIR / "last_sent.sha256"   # "dấu vân tay" của ảnh đã gửi lần trước

LOG_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

# pythonw.exe không có cửa sổ -> sys.stdout/stderr = None -> mọi print() và lỗi sẽ biến mất.
# Chuyển hướng chúng vào file để vẫn đọc được khi có sự cố.
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOG_DIR / "stdout.log", "a", encoding="utf-8", buffering=1)

handlers: list[logging.Handler] = [
    RotatingFileHandler(LOG_DIR / "monitor.log", maxBytes=200_000, backupCount=2, encoding="utf-8"),
    logging.StreamHandler(sys.stdout),
]
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", handlers=handlers)
log = logging.getLogger("monitor")


def summary(data: dict | None) -> str:
    if not data:
        return "không có dữ liệu"
    s, w = data.get("session") or {}, data.get("weekly") or {}
    stale = " (CŨ)" if data.get("stale") else ""
    return f"{data.get('plan')} 5H {s.get('percent')}% 7D {w.get('percent')}%{stale}"


def run(force: bool, use_ble: bool) -> int:
    # Import bên trong hàm để lỗi import (thiếu thư viện, thiếu font...) cũng được ghi vào log
    import planes
    import render
    from fetch_claude import get_claude_usage

    claude = get_claude_usage()        # gọi API (tự làm mới token nếu cần); lỗi -> dùng cache
    gemini = render.load("gemini")     # do userscript + gemini_receiver.py cập nhật
    log.info("Claude: %s | Gemini: %s", summary(claude), summary(gemini))

    img = render.render(claude, gemini)
    img.save(ROOT / "preview.png")
    black, red = planes.split_planes(img)
    black_bytes = planes.pack(black, planes.BLACK_BIT_IS_1)
    red_bytes = planes.pack(red, planes.RED_BIT_IS_1)
    (OUT_DIR / "black.bin").write_bytes(black_bytes)
    (OUT_DIR / "red.bin").write_bytes(red_bytes)

    # Màn E-ink 3 màu tốn pin nhất lúc refresh -> ảnh giống lần trước thì KHÔNG gửi.
    digest = hashlib.sha256(black_bytes + red_bytes).hexdigest()
    if not force and LAST_SENT.exists() and LAST_SENT.read_text().strip() == digest:
        log.info("Ảnh không đổi so với lần gửi trước -> bỏ qua (tiết kiệm pin)")
        return 0
    if not use_ble:
        log.info("--no-ble: đã vẽ xong, không gửi")
        return 0

    try:
        import send_ble                # sẽ viết ở phần BLE của Giai đoạn 4
    except ModuleNotFoundError:
        log.info("Chưa có send_ble.py (chờ thẻ về) -> bỏ qua bước gửi")
        return 0

    if send_ble.send(black_bytes, red_bytes):
        LAST_SENT.write_text(digest)
        log.info("Đã gửi ảnh lên thẻ")
        return 0
    log.warning("Gửi BLE thất bại – sẽ thử lại ở lần chạy sau")
    return 1


if __name__ == "__main__":
    try:
        code = run(force="--force" in sys.argv, use_ble="--no-ble" not in sys.argv)
    except Exception:
        log.exception("Lỗi không mong muốn")   # ghi cả traceback vào log, không để Task Scheduler "im lặng"
        code = 1
    sys.exit(code)
