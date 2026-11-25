# Hướng dẫn cài đặt trên Linux

Làm theo từng bước, mỗi bước có mục **Kiểm tra**. Đã thử với Ubuntu/Debian; Fedora, Arch, openSUSE
làm tương tự (chỉ khác lệnh cài gói).

## Bạn cần
- Linux có **systemd** (Ubuntu, Debian, Fedora, Arch... đều có) và **Bluetooth** (có sẵn hoặc USB dongle).
- Python **3.11+**, `git`, Chrome (hoặc Chromium), Claude Code, gói **BlueZ**.
- Thẻ E-ink NRF EPD, để cách máy dưới ~3 m.

## Bước 1 – Cài công cụ
Ubuntu/Debian:
```bash
sudo apt update
sudo apt install -y git python3 python3-venv bluez
```
Fedora: `sudo dnf install -y git python3 bluez` · Arch: `sudo pacman -S git python bluez bluez-utils`

**Kiểm tra:**
```bash
python3 --version      # phải từ 3.11 trở lên
systemctl --user --version | head -1
```
Nếu Python cũ hơn 3.11 (Ubuntu 22.04 mặc định 3.10): cài bản mới (`sudo apt install python3.12 python3.12-venv`)
và dùng `python3.12` thay cho `python3` ở mọi lệnh bên dưới.

## Bước 2 – Bật Bluetooth
```bash
sudo systemctl enable --now bluetooth
bluetoothctl show | grep -E "Powered|Controller"
```
Phải thấy `Powered: yes`. Nếu `no`: `bluetoothctl power on`. Nếu máy bị khoá bằng rfkill: `rfkill unblock bluetooth`.

**Không cần ghép đôi (pair)** thẻ trong Cài đặt Bluetooth – chương trình tự quét theo tên `NRF_EPD`.
Máy chủ không có giao diện (server) vẫn chạy được; chỉ cần dịch vụ `bluetooth` đang chạy.

## Bước 3 – Tải code và cài
```bash
git clone https://github.com/cherrylinh01/ai-usage-monitor.git
cd ai-usage-monitor
python3 manage.py setup
```
`setup` tạo `.venv`, cài thư viện, tạo `config.toml` với **khoá bí mật mới** và in khoá ra. Hãy copy khoá này
(dùng ở Bước 5).

**Kiểm tra:** `python3 manage.py status` – mục "Môi trường" phải `[OK]`.

> Lỗi *"Không tạo được .venv"* → `sudo apt install python3-venv` rồi chạy lại.

## Bước 4 – Đăng nhập Claude
```bash
curl -fsSL https://claude.ai/install.sh | bash     # cài Claude Code (bỏ qua nếu đã có)
claude                                              # chọn "Claude account with subscription"
```
Máy không có trình duyệt: lệnh in ra một đường link, mở link đó trên máy khác, đăng nhập rồi dán mã về.
Trên Linux, token nằm ở `~/.claude/.credentials.json` (chương trình chỉ đọc, không in ra, không đưa lên Git).

Nếu sau đó gõ `claude` báo không tìm thấy: thêm `export PATH="$HOME/.local/bin:$PATH"` vào `~/.bashrc`
rồi mở lại Terminal.

**Kiểm tra:** `.venv/bin/python fetch_claude.py` in ra % 5H và 7D thật; `python3 manage.py status` mục Claude `[OK]`.

## Bước 5 – Kết nối Gemini (Chrome + Tampermonkey)
1. Cài **Tampermonkey** trong Chrome. Vào `chrome://extensions` → Tampermonkey → Details → bật **Allow User Scripts**.
2. Tạo script mới, dán toàn bộ `gemini_userscript.js`, thay `DAN-KHOA-BI-MAT-CUA-BAN-VAO-DAY` bằng khoá ở Bước 3
   (xem lại khoá: `grep secret config.toml`). Lưu (Ctrl+S).
3. `chrome://settings/performance` → *Always keep these sites active* → thêm `gemini.google.com`.
4. Chạy server: `.venv/bin/python gemini_receiver.py` (giữ cửa sổ mở, hoặc làm Bước 7 để chạy nền).
5. Mở `gemini.google.com` → **Settings → Hạn mức sử dụng** một lần.

Dùng **một Chrome profile riêng**, chỉ đăng nhập đúng 1 tài khoản Google.

**Kiểm tra:** Console (F12) của trang Gemini có "đã lưu mẫu request" và "server trả lời: 200";
`python3 manage.py status` mục Gemini `[OK]`.

## Bước 6 – Thử gửi lên thẻ
Kích hoạt thẻ (nháy/đang chờ), để gần máy, rồi:
```bash
.venv/bin/python send_ble.py --scan       # phải thấy dòng "<== thẻ E-ink"
.venv/bin/python main.py --force          # vẽ + gửi; màn nháy ~20-30 giây
```
Các dòng log cần thấy: `Tìm thấy NRF_EPD_...` → `Thẻ sẵn sàng` → `Đã gửi ảnh lên thẻ`.

**Không thấy thẻ?**
- Thẻ có đang được ứng dụng/trang web khác kết nối không? Đóng chúng lại (một thẻ chỉ nhận 1 kết nối).
- `bluetoothctl show` phải `Powered: yes`; `rfkill list` không được `blocked`.
- Thử `sudo systemctl restart bluetooth`, rồi quét lại.
- Quét ở máy ảo (VM) thường **không** thấy Bluetooth trừ khi gắn USB dongle vào VM.
- Chương trình không cần `sudo`. Nếu báo lỗi D-Bus *AccessDenied*, kiểm tra tài khoản có đăng nhập phiên
  người dùng bình thường (không phải `su`).

## Bước 7 – Chạy tự động (systemd người dùng)
```bash
python3 manage.py install-tasks
```
Lệnh cài 3 unit trong `~/.config/systemd/user/`:

| Unit | Việc |
|---|---|
| `aiusagemonitor-receiver.service` | server Gemini chạy nền, chết thì tự bật lại |
| `aiusagemonitor-update.timer` | sau 1 phút, rồi mỗi 30 phút gọi `main.py` |
| `aiusagemonitor-update.service` | một lần chạy `main.py` (do timer gọi) |

> Cổng 8765 đang bận (bạn đang chạy server tay)? Bấm Ctrl+C rồi chạy lại lệnh.

**Chạy cả khi chưa đăng nhập sau khi bật máy** (không bắt buộc, hữu ích với máy chủ/mini PC):
```bash
sudo loginctl enable-linger "$USER"
```
Không bật thì tác vụ chạy từ lúc bạn đăng nhập đến khi đăng xuất.

**Kiểm tra:**
```bash
python3 manage.py status          # mục "systemd" phải [OK]
systemctl --user list-timers | grep aiusagemonitor
tail logs/monitor.log
```
Chạy ngay: `python3 manage.py run-now` · Gỡ: `python3 manage.py uninstall-tasks`.

## Đổi tài khoản / đổi khoá / nhận code mới
```bash
python3 manage.py switch-account claude     # hoặc gemini / (bỏ trống = cả hai)
python3 manage.py new-key                   # khoá mới, nhớ cập nhật userscript
git pull && python3 manage.py setup         # cập nhật code
python3 manage.py install-tasks             # cài lại unit nếu muốn áp dụng thay đổi
```

## Xem log khi có sự cố
```bash
tail -n 30 logs/monitor.log logs/receiver.log
journalctl --user -u aiusagemonitor-receiver -n 30 --no-pager
journalctl --user -u aiusagemonitor-update -n 30 --no-pager
```

## Chạy tự động bằng cron (máy không có systemd)
```bash
crontab -e
```
Thêm 2 dòng (sửa đường dẫn cho đúng):
```
@reboot cd /home/BAN/ai-usage-monitor && .venv/bin/python gemini_receiver.py >> logs/receiver.log 2>&1
*/30 * * * * cd /home/BAN/ai-usage-monitor && .venv/bin/python main.py >/dev/null 2>&1
```

## Kiểm thử tự động
```bash
.venv/bin/python tests/smoke_test.py       # 16 bài, không cần thẻ/đăng nhập
```
Hoặc chạy trên máy Ubuntu của GitHub: tab **Actions → Linux test → Run workflow**
(hoặc `gh workflow run linux-test.yml`).
