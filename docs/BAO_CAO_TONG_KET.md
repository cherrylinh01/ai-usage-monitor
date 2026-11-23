# Báo cáo tổng kết – AI Usage Monitor trên thẻ E-ink

Thiết bị hiển thị **% hạn mức đã dùng** và **giờ reset** của **Claude** và **Gemini** (phiên 5 giờ + tuần)
trên thẻ giá điện tử E-ink 3 màu 2.9", cập nhật tự động qua Bluetooth LE.

| | |
|---|---|
| Repo | `cherrylinh01/ai-usage-monitor` (private) |
| Máy phát triển | macOS – Python 3.14 |
| Máy chạy hằng ngày | Windows – Python 3.13, Task Scheduler |
| Thẻ | Alibaba Cloud / SoluM `AESL029FC`, chip Nordic nRF52810, tên BLE `NRF_EPD_5119` |

---

## 1. Kiến trúc

```
                    ┌──────────────── máy tính (Mac khi phát triển / Windows khi chạy thật) ────────────────┐
Claude Code login ──► fetch_claude.py ── API /api/oauth/usage ──► cache/claude.json ─┐                       │
                                                                                     ├─► main.py (30 phút/lần)│
Chrome + Tampermonkey ─ userscript bắt/phát lại executeQuery ─► gemini_receiver.py ──► cache/gemini.json ─┘   │
  (trang Gemini đang mở)          POST 127.0.0.1:8765 + khoá                                │                  │
                                                                     render.py ─► planes.py ─► send_ble.py ────┘
                                                                     (ảnh 3 màu)  (2 lớp bit)    │ Bluetooth LE
                                                                                                 ▼
                                                                                  Thẻ E-ink NRF_EPD (296×128)
```

Mỗi khối làm **một việc** và nói chuyện với khối sau qua **file** (`cache/*.json`, `out/*.bin`) → kiểm thử
được từng khối riêng, hỏng khối nào thì thẻ vẫn hiện số cũ kèm dấu `!` đỏ thay vì tắt hẳn.

---

## 2. Chi tiết các kết nối (từ đầu)

### 2.1 Claude – lấy % qua tài khoản Claude Code

| Mục | Chi tiết |
|---|---|
| Nguồn dữ liệu | `GET https://api.anthropic.com/api/oauth/usage` – endpoint mà lệnh `/usage` của Claude Code dùng (**không công khai**) |
| Xác thực | Header `Authorization: Bearer <accessToken>` + `anthropic-beta: oauth-2025-04-20` |
| Token nằm ở đâu | macOS: **Keychain**, mục `Claude Code-credentials` (đọc bằng `security find-generic-password`) · Windows: `%USERPROFILE%\.claude\.credentials.json` |
| Trường dùng | `five_hour.utilization` / `resets_at` (phiên 5 giờ), `seven_day.*` (tuần); gói từ `subscriptionType` + `rateLimitTier` (`pro` → `PRO`, `max`+`20x` → `MAX20`) |
| Token hết hạn | Access token sống ~8 giờ. Khi còn < 5 phút, `fetch_claude.py` chạy **`claude doctor`** để chính Claude Code tự làm mới (không gọi model → **không tốn hạn mức**, không mở phiên 5 giờ mới). Code **không bao giờ** tự ghi vào Keychain/file đăng nhập |
| Khi lỗi | Dùng `cache/claude.json` lần trước, đánh dấu `stale` → thẻ hiện `!` |
| Kết nối tài khoản | Cài Claude Code → `claude` → *Claude account with subscription* → đăng nhập claude.ai |

### 2.2 Gemini – lấy % qua trang "Hạn mức sử dụng"

Gemini Apps dùng **giới hạn theo lượng tính toán** (cửa sổ 5 giờ + tuần), hiển thị ở
**Settings → Hạn mức sử dụng** (`gemini.google.com/usage`). Không có API công khai, nên:

| Bước | Chi tiết |
|---|---|
| Nguồn dữ liệu | Trang Hạn mức gọi GraphQL `…/_/BardChatUi/graphql/schemas/GEMINI_WEB_GRAPHQL/executeQuery?query_signature=…` (persisted query, GET) |
| Dữ liệu | `getUsageInfo.subscriptionTier` (`TIER1` = Pro, `TIER2` ≈ Ultra – suy luận) và `pools[]` gồm `poolType` (`GXU_FIVE_HOURLY` / `GXU_WEEKLY`), `percentageUsed` (0–1), `gxu.windowRefreshesAt` |
| Bắt dữ liệu | **Userscript Tampermonkey** (`gemini_userscript.js`) bọc `fetch` của trang, đọc **bản sao** response. Thay "dây huỷ" `AbortController` của thư viện Relay để bản sao không bị huỷ giữa chừng |
| Tự cập nhật | Lần đầu mở trang Hạn mức → userscript **ghi lại mẫu request** (`GM_setValue`). Sau đó cứ 30 phút, ở **bất kỳ tab Gemini nào**, nó **phát lại** mẫu đó (cookie đăng nhập tự đính kèm vì cùng nguồn). Khoá `replayLock` tránh nhiều tab gọi trùng |
| Gửi về máy | `POST http://127.0.0.1:8765/gemini` kèm header `X-Monitor-Key` (khoá trong `config.toml`) bằng `GM_xmlhttpRequest`. Server chỉ nghe `127.0.0.1`; header tuỳ chỉnh khiến trang web khác bị CORS chặn |
| Lưu | `gemini_receiver.py` chuẩn hoá theo `poolType` → `cache/gemini.json` (ghi file tạm rồi đổi tên – không bao giờ để file ghi dở) |
| Điều kiện | Chrome có **ít nhất 1 tab Gemini mở**; Tampermonkey bật *Allow User Scripts*; server đang chạy |
| Kết nối tài khoản | Chrome profile riêng đăng nhập đúng 1 tài khoản Google → mở trang Hạn mức 1 lần |

### 2.3 Vẽ & đóng gói ảnh

| Bước | Chi tiết |
|---|---|
| `render.py` | Pillow, canvas 296×128, **chỉ 3 màu** trắng/đen/đỏ, font pixel *Press Start 2P* cỡ 8/24 (bội số của 8), tắt khử răng cưa (`fontmode="1"`) |
| Quy tắc hiển thị | Đỏ khi ≥ 80%; cửa sổ đã reset → 0% và `--:--`; giờ reset **làm tròn phút** (API "rung" ±0,5 giây); dấu `!` khi dữ liệu cũ > 2 giờ; nhãn gói chữ trắng nền đen |
| `planes.py` | Tách 2 lớp 1 bit/pixel, mỗi lớp **4736 byte**. Thẻ này: **xoay 90°** (firmware lưu theo cột từ phải sang), lớp đen bit 0 = đen, lớp đỏ **bit 0 = đỏ**. Đã so khớp **từng byte** với code trang web của shop |

### 2.4 Bluetooth LE – gửi lên thẻ

| Mục | Giá trị |
|---|---|
| Service / Characteristic | `62750001-d828-918d-fb46-b6c11c675aec` / `62750002-…` (ghi lệnh + nhận notification) |
| Tìm thẻ | Quét theo **tên** (`NRF_EPD…`/`NRF EPD…`), chọn RSSI mạnh nhất – không gán cứng MAC (Windows) hay UUID (macOS) |
| Trình tự | `SET_TIME(0x20, mode 0)` → `INIT (0x01)` → **chờ notification `t=…`** → lớp đen: gói `[0x30, 0x00/0xF0 \| 0x0F, ≤128 byte]` → lớp đỏ: `[0x30, 0x00/0xF0 \| 0x00, …]` → `SET_TIME(mode 3)` → `REFRESH (0x05)` → giữ kết nối 30 giây |
| Kiểu ghi | Write **with response** (chắc chắn, không mất gói) |
| Thời gian | ~15 giây truyền + ~30 giây màn vẽ |
| Tiết kiệm pin | Chỉ gửi khi **thay đổi đáng kể** so với ảnh đang trên thẻ (`out/last_sent.json`): % đổi ≥ 5 điểm (cộng dồn), qua ngưỡng đỏ, giờ reset đổi, gói đổi, dấu `!` bật/tắt |
| Lưu ý | Không *Pair* thẻ trong cài đặt hệ điều hành; thẻ nhận **1 kết nối/lần** (đóng trang web shop trước) |

### 2.5 Chạy tự động

| | Windows | macOS |
|---|---|---|
| Server Gemini | Tác vụ **`Gemini receiver`**: chạy khi đăng nhập, nền (`pythonw.exe`), tự bật lại khi chết | **Chạy tay** trong Terminal (`python gemini_receiver.py`) |
| Cập nhật thẻ | Tác vụ **`Update display`**: 2 phút sau đăng nhập rồi mỗi 30 phút | **Chạy tay** `python main.py` |
| Cài / gỡ | `manage.cmd install-tasks` / `uninstall-tasks` (không cần Administrator) | – |
| Log | `logs\monitor.log`, `logs\receiver.log`, `logs\stdout.log` | như Windows |

---

## 3. Quy trình cài đặt

### 3.1 macOS (máy phát triển)
```bash
git clone https://github.com/cherrylinh01/ai-usage-monitor.git ~/ai-usage-monitor
cd ~/ai-usage-monitor
python3 manage.py setup                     # .venv + thư viện + config.toml (in khoá)
curl -fsSL https://claude.ai/install.sh | bash   # rồi thêm ~/.local/bin vào PATH, chạy `claude` để đăng nhập
```
Chrome: Tampermonkey → *Allow User Scripts* → dán `gemini_userscript.js` + khoá → mở trang Hạn mức 1 lần.
Mỗi lần dùng: `source .venv/bin/activate` → `python gemini_receiver.py` (để mở) → `python main.py`.
Lần đầu dùng Bluetooth: macOS hỏi quyền cho **Terminal** → *Allow*.

### 3.2 Windows (máy chạy hằng ngày)
Làm theo **[docs/HUONG_DAN_WINDOWS.md](HUONG_DAN_WINDOWS.md)** – 12 bước có kiểm tra sau mỗi bước:
`winget` cài Python 3.13/Git/gh → `gh repo clone` → `manage.cmd setup` → đăng nhập Claude Code →
Chrome profile + Tampermonkey + userscript → `manage.cmd install-tasks` → `send_ble.py --scan`.

### 3.3 Đổi tài khoản / đổi máy
| Việc | Lệnh |
|---|---|
| Đổi tài khoản Claude | `manage.py switch-account claude` (logout → login, xoá cache) |
| Đổi tài khoản Gemini | `manage.py switch-account gemini` → đổi tài khoản trong Chrome profile → mở trang Hạn mức 1 lần |
| Máy mới | Làm lại mục 3.1/3.2 – mỗi máy có **khoá riêng** và Tampermonkey riêng |
| Nhận code mới | `git pull` → `manage.py setup` |

---

## 4. Kết quả rà soát & kiểm thử

Ngày rà soát: **23/11/2026**. Bài kiểm thử tự động `tests/smoke_test.py` chạy trong **bản sao tạm** của dự án
(không đụng cấu hình/cache/thẻ thật), dùng **thẻ giả** thay Bluetooth và **dữ liệu cố định**.

### 4.1 macOS (máy thật, Python 3.14.5)

| Hạng mục | Kết quả |
|---|---|
| `manage.py status` | Mọi mục `[OK]`: .venv, font, khoá, đăng nhập Claude (PRO), lệnh `claude`, server Gemini, cache Claude & Gemini mới |
| `tests/smoke_test.py` | **16/16 đạt** |
| Lấy % Claude thật | ✅ khớp `/usage` (đã đối chiếu nhiều lần, kể cả nhánh token hết hạn → `claude doctor`) |
| Lấy % Gemini thật | ✅ khớp trang Hạn mức (bắt khi mở trang + phát lại tự động) |
| Gửi BLE lên thẻ thật `NRF_EPD_5119` | ✅ ~15 giây truyền, ảnh đúng chiều, đúng màu đỏ |
| Ngưỡng 5 điểm / bỏ qua khi không đổi | ✅ (thẻ giả, 9 tình huống + 6 tình huống trong smoke test) |

### 4.2 Windows (máy Windows thật của GitHub Actions – `windows-latest`)

Workflow `.github/workflows/windows-test.yml`, lần chạy cuối **thành công 8/8 bước**:

| Bước | Kết quả trên Windows |
|---|---|
| 1. `manage.cmd setup` | ✅ tạo `.venv`, cài Pillow 13 + **bleak (import được trên Windows)**, tạo `config.toml` + in khoá |
| 2. `tests\smoke_test.py` | ✅ **16/16 đạt** – gồm `pythonw.exe main.py` ghi log khi chạy nền, `config.toml` có BOM vẫn đọc được |
| 3. `send_ble` khi máy không có Bluetooth | ✅ báo `No Bluetooth adapter found`, trả `False`, **không crash** |
| 4. `manage.cmd install-tasks` | ✅ đăng ký 2 tác vụ **không cần Administrator** |
| 5. Soát cấu hình tác vụ | ✅ `Gemini receiver`: Running bằng `pythonw.exe`, trigger khi đăng nhập · `Update display`: Delay **PT2M**, lặp **PT30M**, thời hạn **Indefinitely** |
| 6. Server chạy nền qua Task Scheduler | ✅ POST thật → `HTTP 200`, `cache\gemini.json` = PRO 5H 20% 7D 10%, `logs\receiver.log` có đủ dòng |
| 7. `run-now` + `status` | ✅ tác vụ chạy, log ghi rõ: chưa đăng nhập Claude → dùng cache; không có Bluetooth → *"Gửi BLE thất bại – sẽ thử lại"*; `status` chỉ đúng 3 mục cần xử lý |
| 8. `manage.cmd uninstall-tasks` | ✅ gỡ sạch |

Lỗi phát hiện trong quá trình kiểm thử Windows và đã sửa:
- Khi chạy nền, mỗi dòng log bị ghi 2 lần (`monitor.log` + `stdout.log`) → chỉ ghi `monitor.log`.
- (Kịch bản kiểm thử) Windows PowerShell 5.1 đọc script không BOM theo bảng mã ANSI → hỏng tiếng Việt.
  Điều này **xác nhận** lựa chọn `-EncodedCommand` trong `manage.py` là đúng.
- (Kịch bản kiểm thử) gọi `.cmd` từ `.cmd` phải có `call`. Người dùng gõ từ PowerShell/nhấp đúp không bị ảnh hưởng.

### 4.3 Những gì CHƯA kiểm thử được tự động
| Hạng mục | Lý do | Cách kiểm tra khi cài |
|---|---|---|
| Đăng nhập Claude Code thật trên Windows | Máy kiểm thử không có tài khoản | Hướng dẫn Windows bước 4 (`fetch_claude.py` → `Gói: PRO`) |
| Tampermonkey + Gemini trên Chrome Windows | Cần trình duyệt + tài khoản Google | Bước 5.6 (server in `[gemini] PRO …`) |
| Bluetooth thật trên Windows | Máy kiểm thử không có Bluetooth | Bước 12 (`send_ble.py --scan`, `main.py --force`) |
| Tác vụ chạy lại sau khi **khởi động lại máy** | Không khởi động lại được máy kiểm thử | Bước 8 |

---

## 5. Hạn chế đã biết

| Hạn chế | Ảnh hưởng | Cách giảm thiểu hiện có |
|---|---|---|
| Endpoint Claude & GraphQL Gemini **không công khai** | Có thể đổi bất cứ lúc nào | Lỗi → dùng cache + dấu `!`; `fetch_claude.py --raw` và DevTools để trinh sát lại |
| `claude doctor` làm mới token là **hành vi phụ** không có tài liệu | Bản Claude Code sau có thể bỏ | Khi đó cần mở Claude Code thường xuyên; thẻ báo `!` |
| Gemini cần **tab Chrome mở** | Đóng Chrome lâu → số Gemini cũ | `chrome://settings/onStartup` mở sẵn Gemini; dấu `!` sau 2 giờ |
| `TIER2 = Ultra` là **suy luận** | Gói lạ hiện nguyên văn (vd `TIER3`) | Bổ sung vào `TIER_NAMES` trong `gemini_receiver.py` |
| macOS **chưa tự chạy** | Phải mở server + `main.py` tay | Dùng Windows cho chạy hằng ngày (có Task Scheduler) |
| Ngưỡng 5 điểm | Số trên thẻ có thể chậm ≤ 4 điểm | Đổi `CHANGE_THRESHOLD` trong `main.py` |

---

## 6. Sự cố đã gặp trong quá trình làm & bài học

| Sự cố | Nguyên nhân | Cách xử lý |
|---|---|---|
| `zsh: command not found: claude` | `~/.local/bin` chưa có trong PATH | Thêm vào `~/.zshrc`, mở Terminal mới |
| Lệnh trong ô nhập của app không thấy `.venv` | Mỗi lệnh chạy shell mới | Dùng Terminal thật hoặc gọi thẳng `.venv/bin/python` |
| Không tìm thấy request `StreamGenerate` | Gemini chuyển sang WebChannel | Bỏ đếm prompt; phát hiện trang Hạn mức (compute-based) |
| `AbortError` khi đọc response | Relay huỷ `AbortController` sau khi đọc xong | Thay "dây huỷ" riêng cho `executeQuery` |
| `tìm thấy 0 cửa sổ` | `windowRefreshesAt` nằm trong object con `gxu` | Đọc JSON thật rồi viết parser theo cấu trúc thật |
| iframe ẩn bị chặn | `X-Frame-Options: DENY` (chống clickjacking) | Ghi & phát lại request thay vì iframe |
| Phát lại "im lặng" | Khoá 5 phút không mở sau khi thành công, không có log | Mở khoá khi thành công + log mọi nhánh bỏ qua |
| `401 Unauthorized` (Claude) | Access token hết hạn sau ~8 giờ | `claude doctor` tự làm mới |
| `Address already in use` | Server cũ còn chạy ở cửa sổ khác | `lsof -iTCP:8765` tìm và dùng tiếp / tắt |
| Lớp đỏ sai màu (dự đoán) | Firmware dùng bit 0 = đỏ, lưu theo cột | Đọc code trang shop, so khớp từng byte |
| Thẻ refresh thừa | Giờ reset API rung quanh mốc phút | Làm tròn phút |
| Số Gemini không cập nhật | Server Gemini trên Mac không chạy | Bật lại server; `manage.py status` chỉ ra ngay |

---

## 7. Lệnh nhanh

| Việc | macOS | Windows |
|---|---|---|
| Kiểm tra tổng thể | `python manage.py status` | nhấp đúp `manage.cmd` |
| Kiểm thử tự động | `python tests/smoke_test.py` | `.venv\Scripts\python tests\smoke_test.py` |
| Quét thẻ | `python send_ble.py --scan` | `.venv\Scripts\python send_ble.py --scan` |
| Gửi ngay | `python main.py --force` | `.\manage.cmd run-now` |
| Xem log | `tail logs/monitor.log` | `Get-Content logs\monitor.log -Tail 20` |
| Kiểm thử trên Windows thật (GitHub) | `gh workflow run windows-test.yml` | – |
