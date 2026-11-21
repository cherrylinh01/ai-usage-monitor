"""Lấy % quota Claude (phiên 5 giờ + tuần 7 ngày) và tên gói từ thông tin đăng nhập của Claude Code."""
import json
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CRED_FILE = Path.home() / ".claude" / ".credentials.json"          # Windows/Linux lưu ở đây
CACHE_FILE = Path(__file__).resolve().parent / "cache" / "claude.json"


def read_oauth() -> dict:
    """Đọc khối 'claudeAiOauth' mà Claude Code đã lưu. KHÔNG in nó ra màn hình (có token)."""
    if CRED_FILE.exists():
        raw = CRED_FILE.read_text(encoding="utf-8")
    elif platform.system() == "Darwin":
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, check=True,
        ).stdout
    else:
        raise FileNotFoundError("Không tìm thấy thông tin đăng nhập Claude Code")
    return json.loads(raw)["claudeAiOauth"]


def find_claude() -> str | None:
    """Tìm lệnh 'claude'. Task Scheduler có thể không có PATH như Terminal -> thử cả vị trí mặc định."""
    exe = shutil.which("claude")
    if exe:
        return exe
    for name in ("claude.exe", "claude"):
        p = Path.home() / ".local" / "bin" / name
        if p.exists():
            return str(p)
    return None


def ensure_fresh_token(oauth: dict) -> dict:
    """Access token sống ~8 giờ. Sắp hết hạn -> nhờ chính Claude Code làm mới (lệnh 'doctor' không tốn quota)."""
    if oauth.get("expiresAt", 0) / 1000 > time.time() + 300:     # còn > 5 phút -> dùng tiếp
        return oauth
    exe = find_claude()
    if not exe:
        raise FileNotFoundError("Token hết hạn và không tìm thấy lệnh 'claude' để làm mới")
    print("[claude] token hết hạn -> chạy 'claude doctor' để Claude Code tự làm mới", file=sys.stderr)
    subprocess.run(
        [exe, "doctor"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=90,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),  # Windows: không bật cửa sổ đen
    )
    return read_oauth()


def plan_label(oauth: dict) -> str:
    """'pro' -> 'PRO'; 'max' + tier '..._20x' -> 'MAX20'. Tối đa 5 ký tự cho vừa nhãn trên thẻ."""
    sub = (oauth.get("subscriptionType") or "").lower()
    tier = (oauth.get("rateLimitTier") or "").lower()
    if sub == "max":
        return "MAX20" if "20x" in tier else "MAX5" if "5x" in tier else "MAX"
    return sub.upper()[:5] or "?"


def fetch_raw_usage(token: str) -> dict:
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "ai-usage-monitor",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def _pick(block: dict | None) -> dict:
    """Rút gọn 1 khối hạn mức thành {percent, resets_at}."""
    block = block or {}
    pct = block.get("utilization")
    return {"percent": round(pct) if pct is not None else None,
            "resets_at": block.get("resets_at")}       # None = chưa có phiên đang chạy


def get_claude_usage() -> dict:
    """Hàm chính cho các module khác gọi. Không bao giờ crash: lỗi thì trả cache."""
    try:
        oauth = ensure_fresh_token(read_oauth())
        raw = fetch_raw_usage(oauth["accessToken"])
        result = {
            "plan": plan_label(oauth),
            "session": _pick(raw.get("five_hour")),
            "weekly": _pick(raw.get("seven_day")),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "stale": False,
        }
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    except Exception as e:
        print(f"[claude] lỗi: {e!r} -> dùng dữ liệu cache", file=sys.stderr)
        if CACHE_FILE.exists():
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            cached["stale"] = True
            return cached
        return {"plan": None, "session": _pick(None), "weekly": _pick(None), "fetched_at": None, "stale": True}


def to_local(iso_utc: str | None) -> str:
    """'2026-11-24T12:59:59+00:00' (UTC) -> '19:59 24/11' (giờ máy)."""
    if not iso_utc:
        return "--:-- --/--"
    return datetime.fromisoformat(iso_utc).astimezone().strftime("%H:%M %d/%m")


if __name__ == "__main__":
    if "--raw" in sys.argv:                       # chế độ gỡ lỗi: xem JSON gốc
        print(json.dumps(fetch_raw_usage(read_oauth()["accessToken"]), indent=2, ensure_ascii=False))
        sys.exit()
    u = get_claude_usage()
    print(json.dumps(u, indent=2))
    print(f"\nGói        : {u.get('plan')}")
    print(f"Phiên 5 giờ : {u['session']['percent']}% | reset {to_local(u['session']['resets_at'])}")
    print(f"Tuần 7 ngày : {u['weekly']['percent']}% | reset {to_local(u['weekly']['resets_at'])}")
    print("(DỮ LIỆU CŨ)" if u["stale"] else "(dữ liệu mới)")
