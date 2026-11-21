"""Công cụ quản lý dự án – chạy giống nhau trên macOS và Windows.

  python manage.py setup                    cài lần đầu: .venv + thư viện + config.toml (khoá mới)
  python manage.py status                   kiểm tra từng thành phần có hoạt động không
  python manage.py switch-account [claude|gemini|all]   đổi tài khoản
  python manage.py new-key                  tạo khoá bí mật mới cho server Gemini

Lệnh 'setup' chỉ dùng thư viện chuẩn -> chạy được bằng Python hệ thống trước khi có .venv.
"""
import argparse
import platform
import secrets
import socket
import subprocess
import sys
import tomllib
import venv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IS_WIN = platform.system() == "Windows"
VENV_DIR = ROOT / ".venv"
VENV_PY = VENV_DIR / ("Scripts/python.exe" if IS_WIN else "bin/python")
CONFIG = ROOT / "config.toml"
EXAMPLE = ROOT / "config.example.toml"
CACHE_DIR = ROOT / "cache"
LAST_SENT = ROOT / "out" / "last_sent.sha256"
PLACEHOLDER = "DAN-KHOA-BI-MAT-CUA-BAN-VAO-DAY"

# Console Windows đôi khi không phải UTF-8 -> tránh lỗi khi in tiếng Việt
for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


# ---------------- tiện ích ----------------
def load_config() -> dict:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


def venv_cmd(*args: str) -> str:
    """Chuỗi lệnh để người dùng copy, đúng cú pháp từng hệ điều hành."""
    py = r".venv\Scripts\python" if IS_WIN else ".venv/bin/python"
    return " ".join([py, *args])


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def age_text(iso: str | None) -> tuple[str, float]:
    if not iso:
        return "chưa có", float("inf")
    hours = (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 3600
    return (f"{hours * 60:.0f} phút trước" if hours < 1 else f"{hours:.1f} giờ trước"), hours


def remove(path: Path) -> None:
    if path.exists():
        path.unlink()
        print(f"  đã xoá {path.relative_to(ROOT)}")


def print_key() -> None:
    key = load_config()["gemini"]["secret"]
    print("\nKhoá bí mật của MÁY NÀY (dán vào dòng SECRET của userscript trong Tampermonkey):")
    print(f"    {key}\n")


# ---------------- setup ----------------
def cmd_setup(_args) -> None:
    if sys.version_info < (3, 11):
        sys.exit("Cần Python 3.11 trở lên (để có tomllib).")
    if not VENV_PY.exists():
        print("Tạo môi trường ảo .venv ...")
        venv.create(VENV_DIR, with_pip=True)
    print("Cài thư viện từ requirements.txt ...")
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=True)
    for d in ("cache", "out", "logs"):
        (ROOT / d).mkdir(exist_ok=True)
    if CONFIG.exists():
        print("config.toml đã có -> giữ nguyên.")
    else:
        CONFIG.write_text(EXAMPLE.read_text(encoding="utf-8").replace(PLACEHOLDER, secrets.token_hex(16)),
                          encoding="utf-8")
        print("Đã tạo config.toml với khoá mới.")
    print_key()
    print("Bước tiếp theo:")
    print("  1. Đăng nhập Claude Code:      claude   (chọn Claude account with subscription)")
    print("  2. Cài userscript Gemini:       dán gemini_userscript.js vào Tampermonkey + khoá ở trên")
    print(f"  3. Chạy server Gemini:          {venv_cmd('gemini_receiver.py')}")
    print("  4. Mở Gemini > Settings > Hạn mức sử dụng 1 lần (để userscript ghi mẫu request)")
    print(f"  5. Kiểm tra tổng thể:           {venv_cmd('manage.py status')}")


# ---------------- new-key ----------------
def cmd_new_key(_args) -> None:
    text = CONFIG.read_text(encoding="utf-8")
    old = load_config()["gemini"]["secret"]
    CONFIG.write_text(text.replace(old, secrets.token_hex(16), 1), encoding="utf-8")
    print("Đã đổi khoá trong config.toml.")
    print_key()
    print("Nhớ: (1) dán khoá mới vào Tampermonkey, (2) khởi động lại gemini_receiver.py.")


# ---------------- status ----------------
def cmd_status(_args) -> None:
    problems = 0

    def check(ok: bool, msg: str, fix: str = "") -> None:
        nonlocal problems
        print(f"  {'[OK]' if ok else '[!!]'} {msg}" + ("" if ok or not fix else f"\n        -> {fix}"))
        problems += not ok

    print(f"Dự án: {ROOT}  ({platform.system()}, Python {platform.python_version()})\n")
    print("Môi trường")
    check(VENV_PY.exists(), ".venv đã tạo", "python manage.py setup")
    check((ROOT / "fonts" / "PressStart2P-Regular.ttf").exists(), "Font pixel có trong fonts/",
          "xem README, mục Font")
    cfg = {}
    if CONFIG.exists():
        cfg = load_config().get("gemini", {})
        check(cfg.get("secret", PLACEHOLDER) != PLACEHOLDER, "config.toml có khoá thật", "python manage.py new-key")
    else:
        check(False, "config.toml tồn tại", "python manage.py setup")

    print("\nClaude")
    sys.path.insert(0, str(ROOT))
    try:
        import fetch_claude as fc
        oauth = fc.read_oauth()
        exp = datetime.fromtimestamp(oauth.get("expiresAt", 0) / 1000)
        check(True, f"Đã đăng nhập Claude Code – gói {fc.plan_label(oauth)}, "
                    f"token hạn {exp:%H:%M %d/%m} (tự làm mới khi cần)")
        check(fc.find_claude() is not None, "Tìm thấy lệnh 'claude' (để làm mới token)", "cài lại Claude Code")
    except Exception as e:  # noqa: BLE001 – chỉ để báo cáo
        check(False, f"Chưa đọc được đăng nhập Claude Code ({type(e).__name__})", "chạy: claude  rồi đăng nhập")

    print("\nGemini")
    port = cfg.get("port", 8765)
    check(port_open(port), f"Server gemini_receiver.py đang chạy (cổng {port})", venv_cmd("gemini_receiver.py"))

    print("\nDữ liệu cache")
    import json
    for name, max_h in (("claude", 1), ("gemini", 2)):
        f = CACHE_DIR / f"{name}.json"
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        text, hours = age_text(data.get("fetched_at"))
        s, w = data.get("session") or {}, data.get("weekly") or {}
        detail = f"{data.get('plan')} 5H {s.get('percent')}% 7D {w.get('percent')}%" if data else ""
        fix = (venv_cmd("fetch_claude.py") if name == "claude"
               else "mở 1 tab Gemini (userscript tự cập nhật mỗi 30 phút)")
        check(hours <= max_h, f"{name}.json cập nhật {text}  {detail}", fix)

    log = ROOT / "logs" / "monitor.log"
    if log.exists():
        print("\n3 dòng cuối logs/monitor.log")
        for line in log.read_text(encoding="utf-8").splitlines()[-3:]:
            print("   ", line)

    print(f"\n{'Mọi thứ ổn.' if problems == 0 else f'Có {problems} mục cần xử lý (xem dấu [!!]).'}")


# ---------------- switch-account ----------------
def cmd_switch(args) -> None:
    which = args.which
    if which in ("claude", "all"):
        sys.path.insert(0, str(ROOT))
        import fetch_claude as fc
        exe = fc.find_claude()
        if not exe:
            sys.exit("Không tìm thấy lệnh 'claude'. Cài Claude Code trước.")
        print("== Claude ==")
        subprocess.run([exe, "auth", "logout"])
        print("Đăng nhập tài khoản mới (trình duyệt sẽ mở ra) ...")
        subprocess.run([exe, "auth", "login", "--claudeai"])
        remove(CACHE_DIR / "claude.json")

    if which in ("gemini", "all"):
        print("== Gemini ==")
        remove(CACHE_DIR / "gemini.json")
        print("  Làm tiếp trong Chrome (profile dành cho dự án):")
        print("   1. Đăng xuất tài khoản Google cũ, đăng nhập tài khoản mới")
        print("   2. Mở Gemini > Settings > Hạn mức sử dụng 1 lần -> userscript ghi mẫu request MỚI")
        print("   3. Console phải hiện 'đã lưu mẫu request' và 'server trả lời: 200'")

    remove(LAST_SENT)  # buộc lần chạy sau gửi ảnh lên thẻ dù số liệu trùng
    print(f"\nXong. Kiểm tra lại bằng: {venv_cmd('manage.py status')}")


def main() -> None:
    p = argparse.ArgumentParser(description="Quản lý AI Usage Monitor")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="cài lần đầu").set_defaults(func=cmd_setup)
    sub.add_parser("status", help="kiểm tra tổng thể").set_defaults(func=cmd_status)
    sub.add_parser("new-key", help="tạo khoá bí mật mới").set_defaults(func=cmd_new_key)
    sw = sub.add_parser("switch-account", help="đổi tài khoản")
    sw.add_argument("which", nargs="?", choices=["claude", "gemini", "all"], default="all")
    sw.set_defaults(func=cmd_switch)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
