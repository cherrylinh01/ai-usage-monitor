# Hướng dẫn cài đặt & chạy trên Windows

Làm lần lượt từ trên xuống. Mỗi bước có phần **✅ Kiểm tra** – chỉ sang bước sau khi kiểm tra đạt.
Thời gian: khoảng 30–45 phút cho lần đầu.

```
Claude Code (đăng nhập tài khoản Claude của bạn) ─► fetch_claude.py ─┐
Chrome + Tampermonkey (tài khoản Google của bạn) ─► gemini_receiver.py ─► cache\ ─┤
                                                                     ├─► main.py ─► preview.png ─► (thẻ E-ink qua Bluetooth)
Task Scheduler: chạy gemini_receiver.py khi đăng nhập + main.py mỗi 30 phút ─┘
```

> Mọi lệnh dưới đây gõ trong **PowerShell** (bấm Start → gõ `PowerShell` → Enter), **không cần quyền Administrator**.
> Trong PowerShell, chạy file ở thư mục hiện tại phải có `.\` phía trước, ví dụ `.\manage.cmd`.

---

## 0. Bạn cần có

| Thứ cần | Ghi chú |
|---|---|
| Windows 10 (bản 21H2 trở lên) hoặc Windows 11 | Có sẵn `winget` (nếu thiếu: cài **App Installer** từ Microsoft Store) |
| Tài khoản GitHub có quyền xem repo `cherrylinh01/ai-usage-monitor` | Repo đang để **private** |
| Tài khoản **Claude** có gói Pro/Max | Dùng để đăng nhập Claude Code |
| Tài khoản **Google** có gói Gemini (Google AI Pro/Ultra…) | Dùng trong Chrome |
| Google Chrome | Edge không dùng được Tampermonkey theo cách trong hướng dẫn này |

---

## 1. Cài công cụ

```powershell
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
winget install -e --id GitHub.cli
```

Sau đó **đóng PowerShell và mở cửa sổ mới** (để Windows nạp lại PATH).

✅ **Kiểm tra** – cả 3 lệnh đều in ra số phiên bản:
```powershell
py --version
git --version
gh --version
```
> `py` báo lỗi? Cài lại Python từ <https://www.python.org/downloads/windows/>, khi cài **tick "Add python.exe to PATH"** và giữ tick **"py launcher"**.

---

## 2. Tải code về máy

```powershell
gh auth login
```
Chọn lần lượt: **GitHub.com** → **HTTPS** → **Yes** → **Login with a web browser**.
Terminal hiện mã `XXXX-XXXX` → nhấn Enter → dán mã vào trang GitHub → **Authorize**.
(Chỉ dùng mã hiện trong PowerShell của chính bạn, không đưa mã cho ai.)

```powershell
cd $HOME
gh repo clone cherrylinh01/ai-usage-monitor
cd ai-usage-monitor
```

> ⚠️ Để dự án ở `C:\Users\<tên bạn>\ai-usage-monitor` như trên. **Đừng** để trong Desktop/Documents –
> trên nhiều máy hai thư mục này được OneDrive đồng bộ và có thể khoá file khi chương trình đang ghi.

✅ **Kiểm tra**: `dir` thấy các file `main.py`, `manage.cmd`, `README.md`…

---

## 3. Cài môi trường Python

```powershell
.\manage.cmd setup
```

Lệnh này tự: tạo môi trường ảo `.venv`, cài thư viện (`requirements.txt`), tạo `config.toml`
với **khoá bí mật mới của máy này**, rồi **in khoá ra màn hình**.

✅ **Kiểm tra**: cuối màn hình có dòng
`Khoá bí mật của MÁY NÀY (dán vào dòng SECRET của userscript trong Tampermonkey):` và một chuỗi 32 ký tự.
**Giữ cửa sổ này** hoặc copy khoá ra Notepad – bước 5 sẽ cần. (Xem lại bất cứ lúc nào: `type config.toml`.)

---

## 4. Kết nối Claude (tài khoản cá nhân)

```powershell
irm https://claude.ai/install.ps1 | iex
```
**Đóng PowerShell, mở cửa sổ mới**, rồi:
```powershell
claude
```
- Chọn giao diện tuỳ ý → chọn **Claude account with subscription** (KHÔNG chọn Anthropic Console).
- Trình duyệt mở ra → đăng nhập claude.ai bằng tài khoản Pro/Max của bạn → **Authorize**.
- Nếu được hỏi *Do you trust the files in this folder?* → **Yes**.
- Gõ `/exit` để thoát.

✅ **Kiểm tra**:
```powershell
cd $HOME\ai-usage-monitor
.venv\Scripts\python fetch_claude.py
```
Cuối kết quả phải có `Gói : PRO` (hoặc MAX…) và `(dữ liệu mới)`.

> Thông tin đăng nhập nằm ở `C:\Users\<bạn>\.claude\.credentials.json` – **không chia sẻ file này**.
> Token tự hết hạn sau vài giờ; chương trình tự gọi `claude doctor` để Claude Code làm mới (không tốn hạn mức).

---

## 5. Kết nối Gemini (tài khoản Google cá nhân)

### 5.1 Tạo Chrome profile riêng (khuyên dùng)
Chrome → bấm ảnh đại diện góc trên phải → **Thêm** → đăng nhập **đúng 1** tài khoản Google có gói Gemini.
Làm mọi bước còn lại **trong profile này**. (Nhiều tài khoản Google trong cùng profile dễ làm userscript lấy nhầm tài khoản.)

### 5.2 Cài Tampermonkey
1. Chrome Web Store → tìm **Tampermonkey** → **Add to Chrome**.
2. Mở `chrome://extensions` → bật **Developer mode** (góc trên phải).
3. Tampermonkey → **Details** → bật **Allow User Scripts** → mục **Site access** chọn **On all sites**.

### 5.3 Cài userscript
1. Mở file userscript bằng Notepad:
   ```powershell
   notepad gemini_userscript.js
   ```
   `Ctrl+A` → `Ctrl+C`.
2. Bấm biểu tượng Tampermonkey → **Create a new script** → `Ctrl+A` → `Ctrl+V`.
3. Tìm dòng `const SECRET = 'DAN-KHOA-BI-MAT-CUA-BAN-VAO-DAY';` → thay chuỗi trong nháy bằng **khoá ở bước 3**.
4. `Ctrl+S` để lưu.

### 5.4 Giữ tab Gemini luôn hoạt động
Userscript chỉ cập nhật khi **có ít nhất 1 tab Gemini đang mở** trong profile này.
1. `chrome://settings/performance` → **Always keep these sites active** → **Add** → `gemini.google.com`.
2. `chrome://settings/onStartup` → **Open a specific page** → thêm `https://gemini.google.com/app`.
3. (Tuỳ chọn) Chuột phải vào tab Gemini → **Pin**.

### 5.5 Chạy thử server nhận dữ liệu
```powershell
.venv\Scripts\python gemini_receiver.py
```
Thấy `Đang lắng nghe http://127.0.0.1:8765/gemini` → **để nguyên cửa sổ này**.
Nếu Windows Firewall hỏi → chọn **Cancel** (server chỉ dùng trong máy, không cần mở ra mạng).

### 5.6 Ghi mẫu request lần đầu
1. Trong Chrome (profile ở 5.1) mở `https://gemini.google.com/app`.
2. Bấm **Settings (Cài đặt)** → **Hạn mức sử dụng (Usage limits)**.

✅ **Kiểm tra**:
- Cửa sổ server in thêm dòng dạng `[gemini] PRO | 5H 0% | 7D 5%`.
- (Nếu không thấy) `F12` → tab **Console** → ô lọc gõ `usage-monitor` → phải có `đã lưu mẫu request` và `server trả lời: 200 ok`.
  Lỗi `403` = khoá trong userscript khác `config.toml`; lỗi `không gửi được` = server chưa chạy.

### 5.7 Tắt server chạy tay
Ở cửa sổ server bấm `Ctrl+C`. (Bước 7 sẽ cho Task Scheduler chạy nó ở chế độ nền.)

---

## 6. Chạy thử một vòng đầy đủ

```powershell
.venv\Scripts\python main.py --no-ble
start preview.png
```
✅ **Kiểm tra**: ảnh 2 cột CLAUDE | GEMINI, có nhãn gói, % và giờ reset. Dấu `!` đỏ ở góc cột = dữ liệu cột đó đã cũ.

---

## 7. Cài chạy tự động (Task Scheduler)

```powershell
.\manage.cmd install-tasks
```
Lệnh tạo thư mục **AIUsageMonitor** trong Task Scheduler với 2 tác vụ và chạy thử ngay:

| Tác vụ | Khi nào chạy | Làm gì | Log |
|---|---|---|---|
| `Gemini receiver` | Khi bạn đăng nhập Windows, chạy nền liên tục, tự bật lại nếu bị tắt | Nhận số liệu từ userscript | `logs\receiver.log` |
| `Update display` | 2 phút sau đăng nhập, rồi **mỗi 30 phút** | Lấy số liệu → vẽ → gửi thẻ | `logs\monitor.log` |

Cả hai chạy bằng `pythonw.exe` nên **không hiện cửa sổ đen**.

✅ **Kiểm tra** (đợi ~20 giây):
```powershell
.\manage.cmd status
```
Tất cả các dòng là `[OK]`, cuối cùng in `Mọi thứ ổn.`
(Hoặc nhấp đúp `manage.cmd` trong File Explorer – mở ra màn hình status.)

Muốn xem bằng giao diện: Start → `Task Scheduler` → **Task Scheduler Library → AIUsageMonitor** →
chọn `Update display` → tab **Triggers** phải ghi *"…repeat every 30 minutes indefinitely"*.

---

## 8. Kiểm tra sau khi khởi động lại máy

1. Restart Windows, đăng nhập.
2. Mở Chrome (profile Gemini) – tab Gemini tự mở nhờ bước 5.4.
3. Đợi ~3 phút → `.\manage.cmd status` → mọi dòng `[OK]`.

Xong – từ giờ máy tự cập nhật mỗi 30 phút mỗi khi bạn dùng máy.

---

## 9. Thao tác thường ngày

| Việc | Lệnh (trong `C:\Users\<bạn>\ai-usage-monitor`) |
|---|---|
| Kiểm tra mọi thứ | `.\manage.cmd status` (hoặc nhấp đúp `manage.cmd`) |
| Cập nhật ngay, không chờ 30 phút | `.\manage.cmd run-now` |
| Xem log | `Get-Content logs\monitor.log -Tail 20` |
| Lấy code mới từ GitHub | `git pull` rồi `.\manage.cmd setup` (cài thư viện mới nếu có) |
| Đổi tài khoản **Claude** | `.\manage.cmd switch-account claude` (tự đăng xuất → đăng nhập) |
| Đổi tài khoản **Gemini** | `.\manage.cmd switch-account gemini` → làm theo hướng dẫn in ra (đổi tài khoản trong Chrome profile, mở lại trang Hạn mức sử dụng 1 lần) |
| Đổi khoá bí mật | `.\manage.cmd new-key` → dán khoá mới vào Tampermonkey → `.\manage.cmd uninstall-tasks` → `.\manage.cmd install-tasks` |
| Tắt hẳn chạy tự động | `.\manage.cmd uninstall-tasks` |

---

## 10. Chuyển sang máy Windows khác

Làm lại toàn bộ hướng dẫn này trên máy mới. Máy mới sẽ có **khoá bí mật riêng** (bước 3) và
**Tampermonkey riêng** (bước 5) – không cần copy gì từ máy cũ.
Trên máy cũ (nếu không dùng nữa): `.\manage.cmd uninstall-tasks`.

---

## 11. Xử lý sự cố

| Hiện tượng | Nguyên nhân / Cách sửa |
|---|---|
| `py` / `git` / `gh` "is not recognized" | Chưa mở PowerShell mới sau khi cài, hoặc cài thiếu PATH (xem bước 1) |
| `.\manage.cmd setup` lỗi khi cài thư viện | Kiểm tra mạng; chạy lại. Vẫn lỗi → `py -3.13 manage.py setup` |
| `fetch_claude.py` báo `FileNotFoundError` | Chưa đăng nhập Claude Code (bước 4) |
| `fetch_claude.py` báo `401 Unauthorized` liên tục | `claude` → `/logout` → đăng nhập lại; hoặc `.\manage.cmd switch-account claude` |
| Server Gemini: `Address already in use` | Đã có server chạy (cửa sổ khác hoặc Task Scheduler). Không cần chạy thêm |
| Console Gemini: `server trả lời: 403` | Khoá trong Tampermonkey ≠ khoá trong `config.toml` |
| Console Gemini: `không gửi được` | Server không chạy → `.\manage.cmd status`, mục Gemini |
| Console Gemini: `mẫu có thể đã hết hạn` | Mở lại Settings → Hạn mức sử dụng 1 lần |
| Không thấy dòng `usage-monitor` nào trong Console | Chưa bật *Allow User Scripts* (bước 5.2) hoặc script chưa lưu |
| Cột GEMINI có `!` đỏ | Không có tab Gemini nào mở > 2 giờ → mở Chrome profile Gemini |
| `install-tasks`: *Access is denied* | Mở PowerShell bằng **Run as administrator**, `cd` vào thư mục dự án, chạy lại |
| `install-tasks`: *Cổng 8765 đang bận* | Đóng cửa sổ server chạy tay (`Ctrl+C`) rồi chạy lại |
| Tác vụ báo `lỗi (xem log)` | Đọc `logs\monitor.log` / `logs\stdout.log` / `logs\receiver.log` – dòng cuối thường ghi rõ lỗi |

---

## 12. Gửi ảnh lên thẻ E-ink (khi có thẻ)

Phần gửi Bluetooth (`send_ble.py`) sẽ được thêm sau khi có thẻ để kiểm tra giao thức. Khi đó chỉ cần
`git pull` – các tác vụ ở bước 7 tự dùng code mới. Lưu ý trước:
- Bật Bluetooth của Windows, **không Pair** thẻ trong Settings (chương trình tự tìm thẻ theo tên `NRF EPD`).
- Thẻ chỉ nhận 1 kết nối một lúc – đóng các trang Web Bluetooth đang kết nối tới thẻ.
