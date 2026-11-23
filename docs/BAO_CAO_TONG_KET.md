# Báo cáo tổng kết – AI Usage Monitor trên thẻ E-ink

Thiết bị hiển thị **% hạn mức đã dùng** và **giờ reset** của **Claude** và **Gemini** (phiên 5 giờ + tuần)
trên thẻ giá điện tử E-ink 3 màu 2.9", **tự cập nhật qua Bluetooth LE** trên cả macOS và Windows.

| | |
|---|---|
| Trạng thái | ✅ **Hoàn thành** – chạy thật trên Mac (tự động bằng launchd), đã kiểm thử trên máy Windows thật |
| Ngày chốt báo cáo | 23/11/2026 |
| Repo | `cherrylinh01/ai-usage-monitor` (private) |
| macOS | Python 3.14 – phát triển + chạy tự động (launchd) |
| Windows | Python 3.13 – chạy hằng ngày (Task Scheduler), hướng dẫn: [HUONG_DAN_WINDOWS.md](HUONG_DAN_WINDOWS.md) |
| Thẻ | Alibaba Cloud / SoluM `AESL029FC`, chip Nordic nRF52810, màn 2.9" đen-trắng-đỏ, tên BLE `NRF_EPD_5119` |

---

## 0. Tóm tắt

| Thành phần | Trạng thái | Bằng chứng |
|---|---|---|
| Lấy % Claude (5H + 7D + tên gói) | ✅ | Khớp `/usage`; tự làm mới token hết hạn |
| Lấy % Gemini (5H + 7D + tên gói) | ✅ | Khớp trang Hạn mức sử dụng; tự cập nhật 30 phút/lần |
| Vẽ giao diện 296×128, 3 màu | ✅ | Đúng 3 màu, hiển thị rõ trên thẻ thật |
| Tách lớp đen/đỏ | ✅ | Khớp **từng byte** với phần mềm của shop |
| Gửi Bluetooth lên thẻ | ✅ | 7 lần gửi thành công trên thẻ thật ngày 23/11 |
| Tiết kiệm pin (ngưỡng 5 điểm) | ✅ | 15 tình huống kiểm thử bằng thẻ giả |
| Chạy tự động macOS (launchd) | ✅ | Đã cài trên Mac, gửi thành công lúc 12:24 qua tác vụ nền |
| Chạy tự động Windows (Task Scheduler) | ✅ | Kiểm thử trên máy Windows thật của GitHub (mục 4.2) |
| Công cụ quản lý `manage.py` | ✅ | setup / status / switch-account / new-key / install-tasks / uninstall-tasks / run-now |
| Tài liệu | ✅ | README, hướng dẫn Windows 12 bước, báo cáo này |

---

## 1. Tiến trình dự án

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| 0. Tổng quan | Sơ đồ luồng, lý thuyết E-ink 2 lớp màu, BLE GATT, khác biệt macOS/Windows, chạy nền | Chốt kiến trúc 3 khối: lấy dữ liệu → vẽ → gửi |
| 2A. Dữ liệu Claude | Đọc token Claude Code, gọi endpoint usage, cache dự phòng | `fetch_claude.py` |
| 2B. Dữ liệu Gemini | 4 vòng trinh sát DevTools → phát hiện giới hạn theo compute + GraphQL `executeQuery` → userscript ghi & phát lại | `gemini_userscript.js` v0.4 + `gemini_receiver.py` |
| 3. Giao diện | Font pixel, khử răng cưa, bố cục 2 cột, nhãn gói, tách lớp + đóng gói bit, kiểm tra khứ hồi | `render.py`, `planes.py` |
| 4A. Chuẩn bị chạy nền | `main.py`, log, khoá tách ra `config.toml`, `.gitignore` | Chạy được không cần cửa sổ |
| GitHub & công cụ | Repo private, `manage.py`/`manage.cmd`, hướng dẫn Windows | Đổi tài khoản/máy bằng 1 lệnh |
| 1. Phần cứng | Thẻ về; đọc giao thức từ phần mềm của shop; gửi ảnh qua Web Bluetooth | Ảnh hiển thị đúng trên thẻ thật |
| 4. BLE | `send_ble.py`, chỉnh `ROTATE=90` + bit đỏ, ngưỡng refresh 5 điểm | Gửi thật thành công từ Python |
| Rà soát | Kiểm thử tự động, kiểm thử Windows thật (GitHub Actions), launchd cho Mac | Mục 4 |

---

## 2. Kiến trúc

```
                     ┌────────────── máy tính (macOS: launchd · Windows: Task Scheduler) ──────────────┐
Claude Code login ──► fetch_claude.py ── API /api/oauth/usage ──► cache/claude.json ─┐                  │
                                                                                     ├─► main.py        │
Chrome + Tampermonkey ─ userscript bắt/phát lại executeQuery ─► gemini_receiver.py ──► cache/gemini.json ┘ (30 phút) │
  (tab Gemini đang mở)        POST 127.0.0.1:8765 + khoá                                   │                 │
                                                          render.py ─► planes.py ─► send_ble.py ────────────┘
                                                          (ảnh 3 màu)  (2 lớp bit)   │ Bluetooth LE (khi đổi đáng kể)
                                                                                     ▼
                                                                      Thẻ E-ink NRF_EPD (296×128)
```

Mỗi khối làm **một việc** và trao đổi với khối sau qua **file** (`cache/*.json`, `out/*.bin`, `out/last_sent.json`)
→ kiểm thử được từng khối riêng; hỏng khối nào thì thẻ vẫn hiện số cũ kèm dấu `!` đỏ thay vì tắt hẳn.

| File | Vai trò |
|---|---|
| `fetch_claude.py` | Token Claude Code → API usage → `cache/claude.json`; tự làm mới token |
| `gemini_userscript.js` | Userscript Tampermonkey: bắt & phát lại `executeQuery`, gửi số liệu về máy |
| `gemini_receiver.py` | Server `127.0.0.1:8765` có khoá → `cache/gemini.json` |
| `render.py` | Vẽ ảnh 296×128 (Pillow, font pixel) |
| `planes.py` | Tách 2 lớp 1 bit/pixel theo đúng quy ước của thẻ |
| `send_ble.py` | Tìm thẻ theo tên, gửi 2 lớp, refresh |
| `main.py` | Chạy cả chuỗi, ghi log, quyết định có cần refresh thẻ không |
| `manage.py` / `manage.cmd` | Cài đặt, kiểm tra, đổi tài khoản, cài/gỡ chạy tự động |
| `tests/smoke_test.py` | Kiểm thử tự động 16 hạng mục (không cần thẻ, không cần đăng nhập) |
| `.github/workflows/windows-test.yml` | Kiểm thử trên máy Windows thật của GitHub (bấm tay) |

---

## 3. Chi tiết các kết nối (từ đầu)

### 3.1 Claude – lấy % qua tài khoản Claude Code

| Mục | Chi tiết |
|---|---|
| Nguồn dữ liệu | `GET https://api.anthropic.com/api/oauth/usage` – endpoint mà lệnh `/usage` của Claude Code dùng (**không công khai**) |
| Xác thực | Header `Authorization: Bearer <accessToken>` + `anthropic-beta: oauth-2025-04-20` |
| Token nằm ở đâu | macOS: **Keychain**, mục `Claude Code-credentials` (đọc bằng `security find-generic-password`) · Windows: `%USERPROFILE%\.claude\.credentials.json` |
| Trường dùng | `five_hour.utilization` / `resets_at` (phiên 5 giờ), `seven_day.*` (tuần); gói từ `subscriptionType` + `rateLimitTier` (`pro` → `PRO`, `max`+`20x` → `MAX20`) |
| Token hết hạn | Access token sống ~8 giờ. Khi còn < 5 phút, `fetch_claude.py` chạy **`claude doctor`** để chính Claude Code tự làm mới (không gọi model → **không tốn hạn mức**, không mở phiên 5 giờ mới). Code **không bao giờ** tự ghi vào Keychain/file đăng nhập |
| Khi lỗi | Dùng `cache/claude.json` lần trước, đánh dấu `stale` → thẻ hiện `!` |
| **Kết nối tài khoản** | Cài Claude Code → chạy `claude` → chọn *Claude account with subscription* → đăng nhập claude.ai trên trình duyệt → `/exit`. Kiểm tra: `fetch_claude.py` in `Gói: PRO` |

### 3.2 Gemini – lấy % qua trang "Hạn mức sử dụng"

Gemini Apps dùng **giới hạn theo lượng tính toán** (cửa sổ 5 giờ + tuần), hiển thị ở
**Settings → Hạn mức sử dụng** (`gemini.google.com/usage`). Không có API công khai, nên:

| Bước | Chi tiết |
|---|---|
| Nguồn dữ liệu | Trang Hạn mức gọi GraphQL `…/_/BardChatUi/graphql/schemas/GEMINI_WEB_GRAPHQL/executeQuery?query_signature=…` (persisted query, GET) |
| Dữ liệu | `getUsageInfo.subscriptionTier` (`TIER1` = Pro, `TIER2` ≈ Ultra – suy luận) và `pools[]` gồm `poolType` (`GXU_FIVE_HOURLY` / `GXU_WEEKLY`), `percentageUsed` (0–1), `gxu.windowRefreshesAt` |
| Bắt dữ liệu | **Userscript Tampermonkey** bọc `fetch` của trang, đọc **bản sao** response. Thay "dây huỷ" `AbortController` của thư viện Relay để bản sao không bị huỷ giữa chừng |
| Tự cập nhật | Lần đầu mở trang Hạn mức → userscript **ghi lại mẫu request** (`GM_setValue`). Sau đó cứ 30 phút, ở **bất kỳ tab Gemini nào**, nó **phát lại** mẫu đó (cookie đăng nhập tự đính kèm vì cùng nguồn). Khoá `replayLock` tránh nhiều tab gọi trùng |
| Gửi về máy | `POST http://127.0.0.1:8765/gemini` kèm header `X-Monitor-Key` (khoá trong `config.toml`) bằng `GM_xmlhttpRequest`. Server chỉ nghe `127.0.0.1`; header tuỳ chỉnh khiến trang web khác bị CORS chặn. **Chỉ gửi con số %**, không bao giờ gửi cookie/headers |
| Lưu | `gemini_receiver.py` chuẩn hoá theo `poolType` → `cache/gemini.json` (ghi file tạm rồi đổi tên – không bao giờ để file ghi dở) |
| Điều kiện | Chrome có **ít nhất 1 tab Gemini mở**; Tampermonkey bật *Allow User Scripts*; server đang chạy |
| **Kết nối tài khoản** | Chrome profile riêng, đăng nhập đúng 1 tài khoản Google → cài Tampermonkey (`chrome://extensions` → Developer mode → Details → *Allow User Scripts*) → dán `gemini_userscript.js`, thay `SECRET` bằng khoá trong `config.toml` → mở **Settings → Hạn mức sử dụng** 1 lần. Kiểm tra: Console có `đã lưu mẫu request` + `server trả lời: 200 ok` |

### 3.3 Vẽ & đóng gói ảnh

| Bước | Chi tiết |
|---|---|
| `render.py` | Pillow, canvas 296×128, **chỉ 3 màu** trắng/đen/đỏ, font pixel *Press Start 2P* cỡ 8/24 (bội số của 8), tắt khử răng cưa (`fontmode="1"`) |
| Quy tắc hiển thị | Đỏ khi ≥ 80%; cửa sổ đã reset → 0% và `--:--`; giờ reset **làm tròn phút** (API "rung" ±0,5 giây); dấu `!` khi dữ liệu cũ > 2 giờ; nhãn gói chữ trắng nền đen |
| `planes.py` | Tách 2 lớp 1 bit/pixel, mỗi lớp **4736 byte**. Thẻ này: **xoay 90°** (firmware lưu theo cột từ phải sang), lớp đen bit 0 = đen, lớp đỏ **bit 0 = đỏ**. Đã so khớp **từng byte** với code trang web của shop |

### 3.4 Bluetooth LE – gửi lên thẻ

| Mục | Giá trị |
|---|---|
| Service / Characteristic | `62750001-d828-918d-fb46-b6c11c675aec` / `62750002-…` (ghi lệnh + nhận notification) |
| Tìm thẻ | Quét theo **tên** (`NRF_EPD…`/`NRF EPD…`), chọn RSSI mạnh nhất – không gán cứng MAC (Windows) hay UUID (macOS). Chọn 1 thẻ cụ thể: `[ble] name_prefix` trong `config.toml` |
| Trình tự | `SET_TIME(0x20, mode 0)` → `INIT (0x01)` → **chờ notification `t=…`** → lớp đen: gói `[0x30, 0x00/0xF0 \| 0x0F, ≤128 byte]` → lớp đỏ: `[0x30, 0x00/0xF0 \| 0x00, …]` → `SET_TIME(mode 3)` → `REFRESH (0x05)` → giữ kết nối 30 giây |
| Kiểu ghi | Write **with response** (chắc chắn, không mất gói) |
| Thời gian | ~15 giây truyền + ~30 giây màn vẽ |
| Tiết kiệm pin | Chỉ gửi khi **thay đổi đáng kể** so với ảnh đang trên thẻ (`out/last_sent.json`): % đổi ≥ 5 điểm (cộng dồn), qua ngưỡng đỏ 80%, giờ reset đổi, gói đổi, dấu `!` bật/tắt |
| Quyền | **Không** *Pair* thẻ trong cài đặt hệ điều hành; thẻ nhận **1 kết nối/lần** (đóng trang web shop trước). macOS: cấp quyền Bluetooth ở **Privacy & Security → Bluetooth** (không phải trang Bluetooth thường) |
| **Kết nối thẻ** | Bật Bluetooth → `send_ble.py --scan` phải thấy `NRF_EPD_xxxx <== thẻ E-ink` → `main.py --force` (hoặc `manage.py run-now`) |

### 3.5 Chạy tự động

| | Windows (Task Scheduler) | macOS (launchd) |
|---|---|---|
| Server Gemini | Tác vụ **`Gemini receiver`**: chạy khi đăng nhập, nền (`pythonw.exe`), tự bật lại khi chết | LaunchAgent **`com.aiusagemonitor.receiver`**: chạy khi đăng nhập, `KeepAlive` tự bật lại |
| Cập nhật thẻ | Tác vụ **`Update display`**: 2 phút sau đăng nhập rồi mỗi 30 phút | LaunchAgent **`com.aiusagemonitor.update`**: khi đăng nhập + mỗi 30 phút, chạy qua app `mac/AIUsageMonitor.app` |
| Vì sao cần thêm | `pythonw.exe` để không hiện cửa sổ đen | App bọc ngoài có khai báo `NSBluetoothAlwaysUsageDescription` – Python Homebrew không có nên macOS chặn Bluetooth khi chạy nền |
| Cài / gỡ | `manage.cmd install-tasks` / `uninstall-tasks` (không cần Administrator) | `python manage.py install-tasks` / `uninstall-tasks` |
| Chạy ngay | `manage.cmd run-now` | `python manage.py run-now` |
| Log | `logs\monitor.log`, `logs\receiver.log`, `logs\stdout.log` | `logs/monitor.log`, `logs/receiver.log`, `logs/launchd-update.log` |

---

## 4. Quy trình cài đặt

### 4.1 macOS
```bash
git clone https://github.com/cherrylinh01/ai-usage-monitor.git ~/ai-usage-monitor
cd ~/ai-usage-monitor
python3 manage.py setup                          # .venv + thư viện + config.toml (in khoá)
curl -fsSL https://claude.ai/install.sh | bash   # thêm ~/.local/bin vào PATH, chạy `claude` để đăng nhập
```
1. Chrome: Tampermonkey → *Allow User Scripts* → dán `gemini_userscript.js` + khoá → mở trang Hạn mức 1 lần.
2. `source .venv/bin/activate && python manage.py install-tasks` (tắt server chạy tay trước nếu có).
3. Lần đầu macOS hỏi **"AIUsageMonitor" muốn dùng Bluetooth** → *Allow*.
4. `python manage.py status` → mọi dòng `[OK]`.

### 4.2 Windows
Làm theo **[HUONG_DAN_WINDOWS.md](HUONG_DAN_WINDOWS.md)** – 12 bước có kiểm tra sau mỗi bước:
`winget` cài Python 3.13/Git/gh → `gh repo clone` → `manage.cmd setup` → đăng nhập Claude Code →
Chrome profile + Tampermonkey + userscript → `manage.cmd install-tasks` → `send_ble.py --scan`.

### 4.3 Đổi tài khoản / đổi máy
| Việc | Lệnh |
|---|---|
| Đổi tài khoản Claude | `manage.py switch-account claude` (logout → login, xoá cache) |
| Đổi tài khoản Gemini | `manage.py switch-account gemini` → đổi tài khoản trong Chrome profile → mở trang Hạn mức 1 lần |
| Đổi khoá bí mật | `manage.py new-key` → dán khoá mới vào Tampermonkey → `uninstall-tasks` + `install-tasks` |
| Máy mới | Làm lại 4.1/4.2 – mỗi máy có **khoá riêng** và Tampermonkey riêng; máy cũ chạy `uninstall-tasks` |
| Nhận code mới | `git pull` → `manage.py setup` |

---

## 5. Kết quả kiểm thử

Bài kiểm thử tự động `tests/smoke_test.py` chạy trong **bản sao tạm** của dự án (không đụng cấu hình/cache/thẻ thật),
dùng **thẻ giả** thay Bluetooth và **dữ liệu cố định**.

### 5.1 macOS – máy thật (Python 3.14.5)

| Hạng mục | Kết quả |
|---|---|
| `manage.py status` | Mọi mục `[OK]`: môi trường, đăng nhập Claude (PRO), server Gemini, 2 cache, **2 LaunchAgent** |
| `tests/smoke_test.py` | **16/16 đạt** |
| Lấy % Claude thật | ✅ khớp `/usage`, kể cả nhánh token hết hạn → `claude doctor` |
| Lấy % Gemini thật | ✅ khớp trang Hạn mức (bắt khi mở trang + phát lại tự động) |
| Gửi BLE lên thẻ thật `NRF_EPD_5119` | ✅ **7 lần thành công** ngày 23/11; ~15 giây truyền, ảnh đúng chiều, đúng màu đỏ |
| Chạy nền bằng launchd | ✅ server Gemini `running`; tác vụ cập nhật gửi thành công lúc 12:24 (2 lần trước đó thất bại do **chưa cấp quyền Bluetooth** – log ghi rõ) |
| Ngưỡng 5 điểm / bỏ qua khi không đổi | ✅ 9 tình huống thủ công + 6 tình huống trong smoke test |

### 5.2 Windows – máy Windows thật của GitHub Actions (`windows-latest`)

Workflow `.github/workflows/windows-test.yml`, chạy trên **commit `cfa7de6`** (code mới nhất, sau khi thêm launchd)
– **thành công 8/8 bước**. `manage.cmd` tự chọn Python mới nhất có trên máy (lần này 3.15.2) → chạy tốt cả 3.13 lẫn 3.15.

| Bước | Kết quả trên Windows |
|---|---|
| 1. `manage.cmd setup` | ✅ tạo `.venv`, cài Pillow 13 + **bleak (import được trên Windows)**, tạo `config.toml` + in khoá |
| 2. `tests\smoke_test.py` | ✅ **16/16 đạt** – gồm `pythonw.exe main.py` ghi log khi chạy nền, `config.toml` có BOM vẫn đọc được |
| 3. `send_ble` khi máy không có Bluetooth | ✅ báo `No Bluetooth adapter found`, trả `False`, **không crash** |
| 4. `manage.cmd install-tasks` | ✅ đăng ký 2 tác vụ **không cần Administrator** |
| 5. Soát cấu hình tác vụ | ✅ `Gemini receiver`: Running bằng `pythonw.exe`, trigger khi đăng nhập · `Update display`: Delay **PT2M**, lặp **PT30M**, thời hạn **Indefinitely** |
| 6. Server chạy nền qua Task Scheduler | ✅ POST thật → `HTTP 200`, `cache\gemini.json` cập nhật, `logs\receiver.log` có đủ dòng |
| 7. `run-now` + `status` | ✅ tác vụ chạy; log ghi rõ "chưa đăng nhập Claude → dùng cache" và "không có Bluetooth → sẽ thử lại"; `status` báo đúng `[!!]` cho tác vụ cập nhật (máy kiểm thử không có Bluetooth – **đúng mong đợi**) |
| 8. `manage.cmd uninstall-tasks` | ✅ gỡ sạch (`REMOVED OK`) |

### 5.3 Chưa kiểm thử được tự động
| Hạng mục | Lý do | Cách tự kiểm tra |
|---|---|---|
| Đăng nhập Claude Code thật trên Windows | Máy kiểm thử không có tài khoản | Hướng dẫn Windows bước 4 (`fetch_claude.py` → `Gói: PRO`) |
| Tampermonkey + Gemini trên Chrome Windows | Cần trình duyệt + tài khoản Google | Bước 5.6 (server in `[gemini] PRO …`) |
| Bluetooth thật trên Windows | Máy kiểm thử không có Bluetooth | Bước 12 (`send_ble.py --scan`, `main.py --force`) |
| Tự chạy lại sau khi **khởi động lại máy** (Windows & Mac) | Chưa khởi động lại máy trong lúc kiểm thử | Khởi động lại → đăng nhập → đợi ~3 phút → `manage.py status` |

---

## 6. Hạn chế đã biết

| Hạn chế | Ảnh hưởng | Cách giảm thiểu hiện có |
|---|---|---|
| Endpoint Claude & GraphQL Gemini **không công khai** | Có thể đổi bất cứ lúc nào | Lỗi → dùng cache + dấu `!`; `fetch_claude.py --raw` và DevTools để trinh sát lại |
| `claude doctor` làm mới token là **hành vi phụ** không có tài liệu | Bản Claude Code sau có thể bỏ | Khi đó cần mở Claude Code thường xuyên; thẻ báo `!` |
| Gemini cần **tab Chrome mở** | Đóng Chrome lâu → số Gemini cũ | `chrome://settings/onStartup` mở sẵn Gemini; dấu `!` sau 2 giờ |
| `TIER2 = Ultra` là **suy luận** | Gói lạ hiện nguyên văn (vd `TIER3`) | Bổ sung vào `TIER_NAMES` trong `gemini_receiver.py` |
| macOS: quyền Bluetooth gắn với `mac/AIUsageMonitor.app` (ký ad-hoc) | Di chuyển thư mục / cài lại có thể khiến macOS hỏi lại | Bấm *Allow* lại; log ghi rõ trạng thái quyền khi không thấy thẻ |
| launchd luôn báo mã thoát 0 cho tác vụ cập nhật (`open -W`) | `status` không thấy lỗi qua mã thoát | Đọc `logs/monitor.log` (status in 3 dòng cuối) |
| Ngưỡng 5 điểm | Số trên thẻ có thể chậm ≤ 4 điểm | Đổi `CHANGE_THRESHOLD` trong `main.py` |

---

## 7. Sự cố đã gặp & bài học

| Sự cố | Nguyên nhân | Cách xử lý |
|---|---|---|
| `zsh: command not found: claude` | `~/.local/bin` chưa có trong PATH | Thêm vào `~/.zshrc`, mở Terminal mới |
| Lệnh trong ô nhập của app không thấy `.venv` | Mỗi lệnh chạy shell mới | Dùng Terminal thật hoặc gọi thẳng `.venv/bin/python` |
| Không tìm thấy request `StreamGenerate` | Gemini chuyển sang WebChannel | Bỏ đếm prompt; phát hiện trang Hạn mức (compute-based) |
| `AbortError` khi đọc response | Relay huỷ `AbortController` sau khi đọc xong | Thay "dây huỷ" riêng cho `executeQuery` |
| `tìm thấy 0 cửa sổ` | `windowRefreshesAt` nằm trong object con `gxu` | Đọc JSON thật rồi viết parser theo cấu trúc thật |
| iframe ẩn bị chặn | `X-Frame-Options: DENY` (chống clickjacking) | Ghi & phát lại request thay vì iframe |
| Phát lại "im lặng" | Khoá không mở sau khi thành công, không có log | Mở khoá khi thành công + log mọi nhánh bỏ qua |
| `401 Unauthorized` (Claude) | Access token hết hạn sau ~8 giờ | `claude doctor` tự làm mới |
| `Address already in use` | Server cũ còn chạy ở cửa sổ khác | `lsof -iTCP:8765` tìm và dùng tiếp / tắt |
| Lớp đỏ sai quy ước (dự đoán ban đầu) | Firmware dùng bit 0 = đỏ, lưu theo cột | Đọc code trang shop, so khớp từng byte |
| Thẻ refresh thừa | Giờ reset API rung quanh mốc phút | Làm tròn phút + ngưỡng 5 điểm |
| Số Gemini không cập nhật | Server Gemini trên Mac không chạy | `manage.py status` chỉ ra ngay → thêm launchd |
| Chạy nền trên Mac không thấy thẻ | Python Homebrew không khai báo quyền Bluetooth (TCC) | App bọc `AIUsageMonitor.app` có khai báo, cấp quyền 1 lần |
| Kiểm thử Windows: chữ Việt vỡ trong PowerShell 5.1 | Script không BOM bị đọc theo ANSI | Kịch bản kiểm thử dùng `pwsh`; `manage.py` vốn đã dùng `-EncodedCommand` nên không bị |
| Kiểm thử Windows: lệnh sau `manage.cmd` không chạy | `.cmd` gọi `.cmd` phải có `call` | Sửa kịch bản kiểm thử (người dùng không bị ảnh hưởng) |
| Log bị ghi trùng khi chạy nền | `stdout.log` + `monitor.log` cùng nhận | Chạy nền chỉ ghi `monitor.log` |

---

## 8. Lệnh nhanh

| Việc | macOS (`source .venv/bin/activate` trước) | Windows |
|---|---|---|
| Kiểm tra tổng thể | `python manage.py status` | nhấp đúp `manage.cmd` |
| Cập nhật thẻ ngay | `python manage.py run-now` | `.\manage.cmd run-now` |
| Cài / gỡ chạy tự động | `python manage.py install-tasks` / `uninstall-tasks` | `.\manage.cmd install-tasks` / `uninstall-tasks` |
| Quét thẻ | `python send_ble.py --scan` | `.venv\Scripts\python send_ble.py --scan` |
| Gửi bất kể ngưỡng | `python main.py --force` | `.venv\Scripts\python main.py --force` |
| Kiểm thử tự động | `python tests/smoke_test.py` | `.venv\Scripts\python tests\smoke_test.py` |
| Xem log | `tail logs/monitor.log` | `Get-Content logs\monitor.log -Tail 20` |

---

## 9. Kiểm thử trên Windows bằng GitHub Actions (bấm tay)

Đây là **máy ảo Windows trên cloud của GitHub**, dùng để kiểm tra code sau khi sửa – **không phải** máy Windows
chạy thẻ của bạn (máy đó tự chạy nhờ Task Scheduler sau `manage.cmd install-tasks`).
Để **bấm tay** vì repo private có 2.000 phút Actions miễn phí/tháng, máy Windows tính ×2 (~10 phút mỗi lần chạy).

**Trên web:** repo → tab **Actions** → cột trái **Windows test** → nút **Run workflow** → branch `main` →
**Run workflow** (xanh) → bấm vào lần chạy để xem từng bước (✅ = đạt; bấm vào bước để đọc log).

**Bằng Terminal:**
```bash
gh workflow run windows-test.yml
gh run watch
```
