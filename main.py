"""Chạy 1 vòng: lấy dữ liệu -> vẽ -> tách lớp -> gửi BLE (chỉ khi thay đổi ĐÁNG KỂ).

Task Scheduler (Windows) gọi file này định kỳ bằng pythonw.exe (không có cửa sổ).
Cờ dòng lệnh:
  --force    gửi lên thẻ kể cả khi không có thay đổi đáng kể
  --no-ble   chỉ vẽ + tách lớp, không gửi (dùng khi chưa có thẻ)
"""
import hashlib
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
OUT_DIR = ROOT / "out"
LAST_SENT = OUT_DIR / "last_sent.json"   # những gì ĐANG hiển thị trên thẻ (lần gửi thành công gần nhất)
CHANGE_THRESHOLD = 5                     # % đổi ít nhất bao nhiêu điểm so với lần gửi trước mới refresh

LOG_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)

# pythonw.exe không có cửa sổ -> sys.stdout/stderr = None -> mọi print() và lỗi sẽ biến mất.
# Chuyển hướng chúng vào file để vẫn đọc được khi có sự cố.
HEADLESS = sys.stdout is None or sys.stderr is None
if HEADLESS:
    sys.stdout = sys.stderr = open(LOG_DIR / "stdout.log", "a", encoding="utf-8", buffering=1)

handlers: list[logging.Handler] = [
    RotatingFileHandler(LOG_DIR / "monitor.log", maxBytes=200_000, backupCount=2, encoding="utf-8"),
]
if not HEADLESS:   # có cửa sổ -> in thêm ra màn hình; chạy nền thì chỉ ghi monitor.log (tránh ghi trùng)
    handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", handlers=handlers)
log = logging.getLogger("monitor")


def summary(data: dict | None) -> str:
    if not data:
        return "không có dữ liệu"
    s, w = data.get("session") or {}, data.get("weekly") or {}
    stale = " (CŨ)" if data.get("stale") else ""
    return f"{data.get('plan')} 5H {s.get('percent')}% 7D {w.get('percent')}%{stale}"


def display_state(claude: dict | None, gemini: dict | None) -> dict:
    """Những gì thẻ SẼ hiển thị (sau khi render xử lý: cửa sổ đã reset -> 0%, giờ làm tròn phút...)."""
    import render
    state = {}
    for name, data in (("claude", claude), ("gemini", gemini)):
        data = data or {}
        state[name] = {"plan": data.get("plan"), "stale": render.is_stale(data)}
        for key in ("session", "weekly"):
            pct, reset = render.effective(data.get(key))
            state[name][key] = {"percent": pct, "reset": reset.strftime("%H:%M %d/%m") if reset else None}
    return state


def change_reason(prev: dict | None, now: dict) -> str | None:
    """Lý do cần refresh thẻ, hoặc None nếu thay đổi quá nhỏ.
    So với lần GỬI gần nhất (không phải lần chạy gần nhất) -> tăng dần 1-2% mỗi lần vẫn được cộng dồn."""
    import render
    if not prev:
        return "chưa có ảnh nào trên thẻ"
    for name, n in now.items():
        p = prev.get(name) or {}
        if p.get("plan") != n["plan"]:
            return f"{name}: đổi gói {p.get('plan')} -> {n['plan']}"
        if p.get("stale") != n["stale"]:
            return f"{name}: dữ liệu {'thành cũ' if n['stale'] else 'mới trở lại'} (dấu !)"
        for key, label in (("session", "5H"), ("weekly", "7D")):
            a, b = p.get(key) or {}, n[key]
            if a.get("reset") != b["reset"]:
                return f"{name} {label}: giờ reset {a.get('reset')} -> {b['reset']}"
            pa, pb = a.get("percent"), b["percent"]
            if (pa is None) != (pb is None):
                return f"{name} {label}: {pa}% -> {pb}%"
            if pb is None:
                continue
            if (pa >= render.RED_THRESHOLD) != (pb >= render.RED_THRESHOLD):
                return f"{name} {label}: {pa}% -> {pb}% (qua ngưỡng đỏ {render.RED_THRESHOLD}%)"
            if abs(pb - pa) >= CHANGE_THRESHOLD:
                return f"{name} {label}: {pa}% -> {pb}%"
    return None


def load_last_sent() -> dict:
    try:
        return json.loads(LAST_SENT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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

    # Màn E-ink 3 màu tốn pin nhất lúc refresh -> chỉ gửi khi thay đổi ĐÁNG KỂ so với ảnh đang trên thẻ.
    digest = hashlib.sha256(black_bytes + red_bytes).hexdigest()
    state = display_state(claude, gemini)
    last = load_last_sent()
    if force:
        reason = "--force"
    elif last.get("digest") == digest:
        log.info("Ảnh không đổi so với lần gửi trước -> bỏ qua (tiết kiệm pin)")
        return 0
    else:
        reason = change_reason(last.get("state"), state)
        if reason is None:
            log.info("Thay đổi nhỏ (< %d điểm %%) -> bỏ qua, thẻ vẫn giữ ảnh cũ", CHANGE_THRESHOLD)
            return 0
    log.info("Cần cập nhật thẻ: %s", reason)
    if not use_ble:
        log.info("--no-ble: đã vẽ xong, không gửi")
        return 0

    try:
        import send_ble                # sẽ viết ở phần BLE của Giai đoạn 4
    except ModuleNotFoundError:
        log.info("Chưa có send_ble.py (chờ thẻ về) -> bỏ qua bước gửi")
        return 0

    if send_ble.send(black_bytes, red_bytes):
        LAST_SENT.write_text(json.dumps({"digest": digest, "state": state,
                                         "sent_at": datetime.now().isoformat(timespec="seconds")},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
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
