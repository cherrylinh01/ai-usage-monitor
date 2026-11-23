"""Kiểm thử tự động toàn bộ luồng – chạy được trên macOS và Windows, KHÔNG cần thẻ, KHÔNG cần đăng nhập.

    python tests/smoke_test.py          (Windows: .venv\\Scripts\\python tests\\smoke_test.py)

Chạy trong một BẢN SAO TẠM của dự án -> không đụng config.toml, cache, log hay thẻ thật.
Kiểm tra: vẽ ảnh 3 màu, tách lớp + khứ hồi, server Gemini (khoá đúng/sai, ghép poolType),
ngưỡng refresh 5 điểm với thẻ giả, chạy nền không cửa sổ (pythonw trên Windows), manage.py status.
"""
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
IS_WIN = platform.system() == "Windows"
PY = sys.executable
PORT = 8799                     # cổng riêng cho kiểm thử, không đụng server thật (8765)
KEY = "khoa-kiem-thu-123"
results: list[tuple[bool, str]] = []

for stream in (sys.stdout, sys.stderr):
    if stream and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name))
    print(f"  [{'OK' if ok else 'LỖI'}] {name}" + (f"  ({detail})" if detail else ""), flush=True)


def run(args: list[str], cwd: Path, **kw) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, env=env, **kw)


def fake_cache(s: int, w: int, plan: str = "PRO") -> dict:
    now = datetime.now(timezone.utc)
    return {"plan": plan, "fetched_at": now.isoformat(), "stale": False,
            "session": {"percent": s, "resets_at": (now + timedelta(hours=3)).replace(second=0).isoformat()},
            "weekly": {"percent": w, "resets_at": (now + timedelta(days=2)).replace(second=0).isoformat()}}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="aiusage-test-"))
    proj = tmp / "proj"
    shutil.copytree(SRC, proj, ignore=shutil.ignore_patterns(
        ".venv", ".git", "cache", "out", "logs", "config.toml", "__pycache__", "*.bak", "preview*.png"))
    # BOM ở đầu file: Notepad đời cũ trên Windows hay thêm -> code phải đọc được
    (proj / "config.toml").write_text(f'﻿[gemini]\nsecret = "{KEY}"\nport = {PORT}\n', encoding="utf-8")
    print(f"Python {platform.python_version()} trên {platform.system()} | bản sao tạm: {proj}\n", flush=True)

    # ---------- 1. Vẽ + tách lớp ----------
    print("1. Vẽ ảnh và tách lớp")
    write_json(proj / "cache" / "claude.json", fake_cache(85, 38))
    write_json(proj / "cache" / "gemini.json", fake_cache(0, 5))
    r = run([PY, "render.py"], proj)
    check(r.returncode == 0 and "số màu: 3" in r.stdout, "render.py tạo ảnh đúng 3 màu", r.stdout.strip()[-80:])
    r = run([PY, "planes.py"], proj)
    check(r.returncode == 0 and "ĐÚNG" in r.stdout, "planes.py: 2 lớp x 4736 byte, khứ hồi đúng",
          (r.stdout + r.stderr).strip().splitlines()[-1][-80:] if (r.stdout + r.stderr).strip() else "")
    sizes = [(proj / "out" / f).stat().st_size if (proj / "out" / f).exists() else 0 for f in ("black.bin", "red.bin")]
    check(sizes == [4736, 4736], "black.bin/red.bin đúng 4736 byte", str(sizes))

    # ---------- 2. Server Gemini ----------
    print("\n2. Server nhận số liệu Gemini")
    server = subprocess.Popen([PY, "gemini_receiver.py"], cwd=proj,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", PORT)) == 0:
                    break
            time.sleep(0.2)
        payload = {"tier": "TIER1", "windows": [
            {"poolType": "GXU_WEEKLY", "percentageUsed": 0.0537, "windowRefreshesAt": "2030-01-08T13:46:35Z"},
            {"poolType": "GXU_FIVE_HOURLY", "percentageUsed": 0.42, "windowRefreshesAt": "2030-01-01T17:46:35Z"}]}

        def post(key: str) -> int:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/gemini", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json", "X-Monitor-Key": key})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.status
            except urllib.error.HTTPError as e:
                return e.code
            except OSError:
                return -1

        check(post("sai-khoa") == 403, "khoá sai bị từ chối (403)")
        check(post(KEY) == 200, "khoá đúng được nhận (200) – đọc được config.toml có BOM")
        g = json.loads((proj / "cache" / "gemini.json").read_text(encoding="utf-8"))
        check(g["plan"] == "PRO" and g["session"]["percent"] == 42 and g["weekly"]["percent"] == 5,
              "ghép đúng poolType -> PRO, 5H 42%, 7D 5%", f"{g['plan']} {g['session']} {g['weekly']}")
    finally:
        server.terminate()
        server.wait(timeout=10)

    # ---------- 3. Ngưỡng refresh với thẻ giả ----------
    print("\n3. Ngưỡng refresh 5 điểm (thẻ giả, không cần Bluetooth)")
    (proj / "send_ble.py").write_text(  # thay send_ble thật bằng bản giả: chỉ ghi lại số lần gửi
        "from pathlib import Path\n"
        "def send(b, r):\n"
        "    p = Path(__file__).with_name('sent.count')\n"
        "    p.write_text(str(int(p.read_text()) + 1 if p.exists() else 1))\n"
        "    return True\n", encoding="utf-8")
    (proj / "run_offline.py").write_text(  # chạy main.run nhưng lấy số liệu Claude từ cache (không gọi API)
        "import json, sys, fetch_claude\n"
        "fetch_claude.get_claude_usage = lambda: json.load(open('cache/claude.json', encoding='utf-8'))\n"
        "import main\n"
        "sys.exit(main.run(force=False, use_ble=True))\n", encoding="utf-8")
    write_json(proj / "cache" / "gemini.json", fake_cache(0, 5))
    sent = lambda: int((proj / "sent.count").read_text()) if (proj / "sent.count").exists() else 0
    for label, s, w, expect in [("lần đầu", 46, 38, 1), ("y hệt", 46, 38, 1), ("+3 điểm", 49, 38, 1),
                                ("cộng dồn +5", 51, 38, 2), ("7D 38->79", 51, 79, 3),
                                ("7D 79->80: +1 nhưng qua ngưỡng đỏ", 51, 80, 4)]:
        write_json(proj / "cache" / "claude.json", fake_cache(s, w))
        r = run([PY, "run_offline.py"], proj)
        check(r.returncode == 0 and sent() == expect, f"{label}: tổng số lần gửi = {expect}", f"thực tế {sent()}")

    # ---------- 4. Chạy nền không cửa sổ ----------
    print("\n4. Chạy nền (không có cửa sổ)")
    log = proj / "logs" / "monitor.log"
    before = log.read_text(encoding="utf-8").count("\n") if log.exists() else 0
    if IS_WIN:
        pyw = Path(PY).with_name("pythonw.exe")
        r = run([str(pyw), "main.py", "--no-ble"], proj)
        label = "pythonw.exe main.py ghi log vào logs\\monitor.log"
    else:  # mô phỏng pythonw: không có stdout/stderr
        r = run([PY, "-c", "import sys,runpy; sys.stdout=sys.stderr=None; sys.argv=['main.py','--no-ble']; "
                           "runpy.run_path('main.py', run_name='__main__')"], proj)
        label = "mô phỏng pythonw (stdout=None): main.py vẫn ghi log"
    after = log.read_text(encoding="utf-8").count("\n") if log.exists() else 0
    check(after > before, label, f"{after - before} dòng log mới")
    # Máy kiểm thử không đăng nhập Claude -> phải dùng cache, KHÔNG crash
    tail = log.read_text(encoding="utf-8").splitlines()[-3:] if log.exists() else []
    check(not any("Lỗi không mong muốn" in t for t in tail),
          "main.py chạy hết không lỗi (máy chưa đăng nhập Claude thì dùng cache)")

    # ---------- 5. manage.py ----------
    print("\n5. manage.py")
    r = run([PY, "manage.py", "status"], proj)
    check(r.returncode == 0 and "Môi trường" in r.stdout, "manage.py status chạy được")
    r = run([PY, "manage.py", "new-key"], proj)
    new_cfg = (proj / "config.toml").read_text(encoding="utf-8-sig")
    check(r.returncode == 0 and KEY not in new_cfg and "secret" in new_cfg, "manage.py new-key đổi khoá")

    shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for ok, n in results if not ok]
    print(f"\nKẾT QUẢ: {len(results) - len(failed)}/{len(results)} đạt" + (f" | LỖI: {failed}" if failed else " ✅"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
