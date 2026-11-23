# AI Usage Monitor (thẻ E-ink 2.9")

Hiển thị **% hạn mức đã dùng** và **giờ reset** của **Claude** và **Gemini** (phiên 5 giờ + tuần)
trên thẻ giá điện tử E-ink 3 màu 296×128 (firmware `NRF EPD`), gửi ảnh qua Bluetooth LE.

```
Claude Code token ──► fetch_claude.py ──┐
                                        ├─► render.py ─► planes.py ─► send_ble.py ─► thẻ E-ink
Gemini (Chrome + userscript) ──►        │   (ảnh 3 màu)  (lớp đen/đỏ)   (BLE)
   gemini_receiver.py ─► cache/ ────────┘
                         main.py chạy cả chuỗi; Task Scheduler gọi main.py mỗi 30 phút
```

> ⚠️ Dự án dùng **endpoint nội bộ, không công khai** của Anthropic và Google. Chúng có thể thay đổi
> bất cứ lúc nào; khi đó thẻ hiện số cũ kèm dấu `!` đỏ thay vì bị lỗi. Chỉ dùng cho tài khoản của chính bạn.

## Cài trên máy mới

> 📋 **Báo cáo tổng kết (kiến trúc, chi tiết kết nối, kết quả kiểm thử): [docs/BAO_CAO_TONG_KET.md](docs/BAO_CAO_TONG_KET.md)**
>
> 🪟 **Windows: làm theo hướng dẫn từng bước [docs/HUONG_DAN_WINDOWS.md](docs/HUONG_DAN_WINDOWS.md)**
> (cài công cụ, clone, đăng nhập Claude/Gemini, chạy tự động bằng Task Scheduler, xử lý sự cố).

Tóm tắt – yêu cầu: Python **3.11+** (khuyên 3.13 trên Windows), Chrome, Claude Code.

```bash
git clone https://github.com/<tài-khoản>/ai-usage-monitor.git
cd ai-usage-monitor
python manage.py setup        # Windows: py -3 manage.py setup   (hoặc manage.cmd setup)
```

`setup` tạo `.venv`, cài thư viện, tạo `config.toml` với **khoá bí mật mới** và in khoá ra màn hình. Sau đó:

1. **Claude**: chạy `claude`, đăng nhập bằng *Claude account with subscription*.
2. **Gemini**: cài Tampermonkey → `chrome://extensions` → Details → bật *Allow User Scripts* →
   tạo script mới, dán `gemini_userscript.js`, thay `SECRET` bằng khoá vừa in. Thêm `gemini.google.com`
   vào *Always keep these sites active* (`chrome://settings/performance`).
3. Chạy server Gemini: `.venv/bin/python gemini_receiver.py` (Windows: `.venv\Scripts\python gemini_receiver.py`).
4. Mở Gemini → **Settings → Hạn mức sử dụng** một lần (userscript ghi lại mẫu request).
5. Kiểm tra: `python manage.py status` (Windows: nhấp đúp `manage.cmd`).

## Đổi tài khoản

```bash
python manage.py switch-account claude   # đăng xuất/đăng nhập Claude Code + xoá cache Claude
python manage.py switch-account gemini   # xoá cache Gemini + hướng dẫn các bước trong Chrome
python manage.py switch-account          # cả hai
```

Với Gemini nên dùng **một Chrome profile riêng** chỉ đăng nhập đúng 1 tài khoản Google, để userscript
không ghi nhầm mẫu request của tài khoản khác.

## Các lệnh hằng ngày

| Việc | Lệnh |
|---|---|
| Kiểm tra mọi thứ | `python manage.py status` |
| Chạy 1 vòng (không gửi BLE) | `python main.py --no-ble` |
| Xem trước ảnh | mở `preview.png` |
| Đổi khoá bí mật Gemini | `python manage.py new-key` |
| Cài / gỡ chạy tự động (Windows: Task Scheduler · macOS: launchd) | `python manage.py install-tasks` / `uninstall-tasks` |
| Cập nhật thẻ ngay | `python manage.py run-now` |
| Kiểm thử tự động | `python tests/smoke_test.py` |
| Kiểm thử trên máy Windows của GitHub (bấm tay) | tab **Actions → Windows test → Run workflow**, hoặc `gh workflow run windows-test.yml` |

(Trên Windows thay `python` bằng `.venv\Scripts\python`, hoặc dùng `manage.cmd <lệnh>`.)

## Cấu trúc

| File | Vai trò |
|---|---|
| `fetch_claude.py` | Đọc token Claude Code (Keychain/macOS, `~/.claude/.credentials.json`/Windows), gọi API usage, tự làm mới token bằng `claude doctor` |
| `gemini_userscript.js` | Userscript Tampermonkey: bắt & phát lại truy vấn `executeQuery` của trang Hạn mức |
| `gemini_receiver.py` | Server `127.0.0.1` nhận số liệu từ userscript → `cache/gemini.json` |
| `render.py` | Vẽ giao diện 296×128 bằng Pillow + font pixel |
| `planes.py` | Tách lớp đen/đỏ, đóng gói 1 bit/pixel (4736 byte/lớp) |
| `main.py` | Chạy cả chuỗi, ghi log `logs/`, chỉ gửi khi ảnh thay đổi |
| `manage.py` / `manage.cmd` | setup / status / switch-account / new-key |
| `config.example.toml` | Mẫu cấu hình (bản thật `config.toml` **không** đưa lên Git) |

## Bảo mật

- `config.toml`, `cache/`, `logs/`, `out/` nằm trong `.gitignore` – **không bao giờ commit**.
- Token Claude chỉ được đọc lúc chạy, không in ra, không ghi lại.
- Server Gemini chỉ nghe ở `127.0.0.1` và yêu cầu header `X-Monitor-Key`.

## Font

`fonts/PressStart2P-Regular.ttf` – *Press Start 2P* của CodeMan38, giấy phép
[SIL Open Font License 1.1](fonts/OFL.txt).
