"""Gửi ảnh 2 lớp (đen/đỏ) lên thẻ E-ink NRF_EPD qua Bluetooth LE – chạy được trên macOS và Windows.

Giao thức lấy từ trang điều khiển của shop (bản mở rộng của tsl0922/EPD-nRF5), màn 2.9" 296x128:
  1. SET_TIME(mode 0)            dừng các tác vụ đồng hồ trên thẻ
  2. INIT (0x01)                 -> thẻ trả lời notification "t=<số>" khi bộ nhớ màn sẵn sàng
  3. WRITE_IMAGE (0x30) lớp đen  từng gói [0x30, cờ, <=128 byte]
  4. WRITE_IMAGE (0x30) lớp đỏ
  5. SET_TIME(mode 3)            chuẩn bị chế độ ảnh
  6. REFRESH (0x05)              thẻ vẽ ảnh (màn 3 màu mất ~20-30 giây)

  python send_ble.py --scan      liệt kê thẻ tìm thấy
  python send_ble.py             gửi out/black.bin + out/red.bin
"""
import asyncio
import logging
import re
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

ROOT = Path(__file__).resolve().parent
log = logging.getLogger("ble")

CHAR_UUID = "62750002-d828-918d-fb46-b6c11c675aec"   # characteristic nhận lệnh + gửi notification

CMD_INIT, CMD_REFRESH, CMD_SET_TIME, CMD_WRITE_IMAGE = 0x01, 0x05, 0x20, 0x30
CHUNK = 128                 # byte dữ liệu ảnh mỗi gói (giống trang web shop)
FLAG_FIRST, FLAG_NEXT = 0x00, 0xF0
FLAG_BLACK, FLAG_RED = 0x0F, 0x00
MODE_STOP_CLOCK, MODE_PICTURE = 0, 3


def ble_config() -> dict:
    """[ble] trong config.toml (không bắt buộc): name_prefix, address."""
    try:
        return tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8-sig")).get("ble", {})
    except (OSError, ValueError):   # thiếu file / file TOML hỏng -> dùng mặc định
        return {}


def norm(name: str | None) -> str:
    """'NRF_EPD_5119' / 'NRF EPD 5119' -> 'NRF EPD 5119' để so khớp cả hai kiểu đặt tên."""
    return re.sub(r"[_\s]+", " ", name or "").strip().upper()


def bluetooth_permission_hint() -> str:
    """macOS: đọc trạng thái quyền Bluetooth của CHƯƠNG TRÌNH ĐANG CHẠY (Terminal hoặc AIUsageMonitor.app)."""
    if sys.platform != "darwin":
        return ""
    try:
        from CoreBluetooth import CBManager   # có sẵn vì bleak trên macOS cài kèm pyobjc
        state = int(CBManager.authorization())
    except Exception:  # noqa: BLE001
        return ""
    meaning = {0: "CHƯA HỎI (macOS chưa hiện hộp thoại xin quyền)", 1: "BỊ HẠN CHẾ",
               2: "BỊ TỪ CHỐI", 3: "đã cho phép"}
    hint = f" Quyền Bluetooth của macOS: {meaning.get(state, state)}."
    if state != 3:
        hint += (" -> System Settings > Privacy & Security (Quyền riêng tư & Bảo mật) > Bluetooth:"
                 " bật AIUsageMonitor / Terminal.")
    return hint


async def find_device(timeout: float = 10.0):
    """Quét theo TÊN (không gán cứng MAC/UUID) -> chạy được trên cả macOS lẫn Windows."""
    cfg = ble_config()
    want_addr = (cfg.get("address") or "").upper()
    prefix = norm(cfg.get("name_prefix", "NRF EPD"))
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches = []
    for dev, adv in found.values():
        name = adv.local_name or dev.name
        if want_addr and dev.address.upper() == want_addr:
            return dev, name, adv.rssi
        if norm(name).startswith(prefix):
            matches.append((adv.rssi, dev, name))
    if not matches:
        log.warning("Quét %.0f giây: thấy %d thiết bị Bluetooth, không cái nào là thẻ NRF_EPD.%s",
                    timeout, len(found), bluetooth_permission_hint())
        return None, None, None
    rssi, dev, name = max(matches, key=lambda m: m[0])   # nhiều thẻ -> chọn thẻ gần nhất (sóng mạnh nhất)
    return dev, name, rssi


def set_time_packet(mode: int) -> bytes:
    ts = int(time.time())
    tz_hours = round(datetime.now().astimezone().utcoffset().total_seconds() / 3600)   # VN = +7
    return bytes([CMD_SET_TIME, (ts >> 24) & 0xFF, (ts >> 16) & 0xFF, (ts >> 8) & 0xFF, ts & 0xFF,
                  tz_hours & 0xFF, mode])


async def _send(black: bytes, red: bytes, refresh_wait: float) -> bool:
    dev, name, rssi = await find_device()
    if dev is None:
        log.warning("Không tìm thấy thẻ (tên bắt đầu bằng NRF_EPD). Thẻ có ở gần không? "
                    "Có trang web/ứng dụng nào khác đang kết nối với thẻ không?")
        return False
    log.info("Tìm thấy %s (RSSI %s dBm) – đang kết nối...", name, rssi)

    init_ok = asyncio.Event()

    def on_notify(_sender, data: bytearray) -> None:
        text = bytes(data).decode("utf-8", errors="replace")
        if re.fullmatch(r"t=\d+\s*", text):
            init_ok.set()

    async with BleakClient(dev, timeout=20.0) as client:
        await client.start_notify(CHAR_UUID, on_notify)

        async def write(packet: bytes) -> None:
            await client.write_gatt_char(CHAR_UUID, packet, response=True)

        await write(set_time_packet(MODE_STOP_CLOCK))
        await asyncio.sleep(0.15)
        await write(bytes([CMD_INIT]))
        try:
            await asyncio.wait_for(init_ok.wait(), timeout=45)
        except TimeoutError:
            log.warning("Thẻ không trả lời INIT trong 45 giây – huỷ gửi.")
            return False
        log.info("Thẻ sẵn sàng – gửi lớp đen + đỏ (%d + %d byte)...", len(black), len(red))

        for data, plane in ((black, FLAG_BLACK), (red, FLAG_RED)):
            for offset in range(0, len(data), CHUNK):
                flag = (FLAG_FIRST if offset == 0 else FLAG_NEXT) | plane
                await write(bytes([CMD_WRITE_IMAGE, flag]) + data[offset:offset + CHUNK])
                await asyncio.sleep(0.008)

        await write(set_time_packet(MODE_PICTURE))
        await write(bytes([CMD_REFRESH]))
        log.info("Đã ra lệnh refresh – chờ %.0f giây cho màn vẽ xong...", refresh_wait)
        await asyncio.sleep(refresh_wait)   # giữ kết nối trong lúc màn đang nháy, như trang web shop
    return True


def send(black: bytes, red: bytes, refresh_wait: float = 30.0) -> bool:
    """Hàm main.py gọi. Trả True nếu gửi xong. Không ném lỗi ra ngoài."""
    try:
        return asyncio.run(_send(black, red, refresh_wait))
    except Exception as e:  # noqa: BLE001 – lỗi Bluetooth rất đa dạng; ghi log rồi để lần sau thử lại
        log.warning("Lỗi Bluetooth: %r", e)
        return False


async def _scan() -> None:
    found = await BleakScanner.discover(timeout=10.0, return_adv=True)
    rows = sorted(((adv.rssi, dev.address, adv.local_name or dev.name) for dev, adv in found.values()),
                  reverse=True)
    for rssi, addr, name in rows:
        mark = "  <== thẻ E-ink" if norm(name).startswith("NRF EPD") else ""
        if name:
            print(f"{rssi:>5} dBm  {addr}  {name}{mark}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if "--scan" in sys.argv:
        asyncio.run(_scan())
    else:
        out = ROOT / "out"
        ok = send((out / "black.bin").read_bytes(), (out / "red.bin").read_bytes())
        sys.exit(0 if ok else 1)
