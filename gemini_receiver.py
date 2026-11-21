"""Server nhỏ nhận số liệu Gemini từ userscript, lưu vào cache/gemini.json."""
import json
import tomllib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))["gemini"]
HOST, PORT = "127.0.0.1", CONFIG.get("port", 8765)  # chỉ máy này truy cập được
SECRET = CONFIG["secret"]                           # khoá nằm trong config.toml, không nằm trong code
CACHE_FILE = ROOT / "cache" / "gemini.json"


# Tên gói theo subscriptionTier. TIER1 = Pro (đã kiểm chứng với tài khoản của bạn);
# TIER2 = Ultra (suy ra từ "CAN_UPGRADE_TO_TIER2"). Tier lạ -> hiện nguyên văn (tối đa 5 ký tự).
TIER_NAMES = {"TIER1": "PRO", "TIER2": "ULTRA"}


def normalize(payload: dict) -> dict:
    """{tier, windows:[{poolType, percentageUsed: 0.02, windowRefreshesAt}]} -> cùng định dạng với Claude."""
    windows = [w for w in payload["windows"] if isinstance(w.get("percentageUsed"), (int, float))]
    by_type = {w.get("poolType"): w for w in windows}
    session, weekly = by_type.get("GXU_FIVE_HOURLY"), by_type.get("GXU_WEEKLY")

    if not (session or weekly):  # dự phòng: không có poolType -> cửa sổ reset sớm hơn = phiên ngắn
        dated = sorted((w for w in windows if w.get("windowRefreshesAt")),
                       key=lambda w: datetime.fromisoformat(w["windowRefreshesAt"]))
        session = dated[0] if dated else None
        weekly = dated[-1] if len(dated) > 1 else None

    def pick(w):
        if not w:
            return {"percent": None, "resets_at": None}
        return {"percent": round(w["percentageUsed"] * 100), "resets_at": w.get("windowRefreshesAt")}

    tier = payload.get("tier")
    return {
        "plan": TIER_NAMES.get(tier, tier[:5]) if tier else None,
        "session": pick(session),
        "weekly": pick(weekly),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "stale": False,
    }


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/gemini" or self.headers.get("X-Monitor-Key") != SECRET:
            return self._reply(403, "forbidden")
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length < 100_000:                 # chặn dữ liệu rỗng hoặc quá lớn
            return self._reply(400, "bad size")
        try:
            result = normalize(json.loads(self.rfile.read(length)))
        except (ValueError, KeyError, TypeError) as e:
            return self._reply(400, f"bad data: {e}")
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"[gemini] {result['plan']} | 5H {result['session']['percent']}% | 7D {result['weekly']['percent']}%")
        self._reply(200, "ok")

    def _reply(self, code: int, msg: str):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(msg.encode())

    def log_message(self, *args):                    # tắt log mặc định cho gọn
        pass


if __name__ == "__main__":
    print(f"Đang lắng nghe http://{HOST}:{PORT}/gemini  (Ctrl+C để dừng)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()