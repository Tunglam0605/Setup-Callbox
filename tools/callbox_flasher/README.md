# AUBOT CallBox Production Flasher V1

Công cụ nạp firmware độc lập một nút bấm (Windows executable) dành cho đội ngũ sản xuất và kỹ thuật, dùng để nạp toàn diện board mới **Waveshare ESP32-S3-POE-ETH-8DI-8DO**.

Máy trạm người dùng **không cần cài đặt Python, ESP-IDF, trình biên dịch hay driver đặc biệt** (ngoại trừ driver cổng USB-UART nếu máy tính chưa có).

---

## 1. Yêu cầu hệ thống & Thiết bị hỗ trợ

- **Hệ điều hành:** Windows 10/11 x64.
- **Phần cứng mục tiêu:** Waveshare ESP32-S3-POE-ETH-8DI-8DO (ESP32-S3, 16 MB Flash, cổng USB-UART Type-C).
- **Driver USB:** CP210x USB to UART Bridge VCP hoặc CH343/CH9102 VCP driver (Windows Update thường tự cài đặt). Khi cắm board, Device Manager sẽ xuất hiện một cổng COM (ví dụ: `COM5`, `COM7`).

> [!WARNING]
> **Giới hạn bảo mật V1:** Bản V1 sử dụng cấu hình nạp phát triển (**Development provisioning baseline**). Thiết bị sau khi nạp chưa bật Secure Boot, Flash Encryption hay đốt eFuse vĩnh viễn. Không được coi thiết bị nạp bởi V1 là đã khóa bảo mật phần cứng chống trích xuất.

---

## 2. Các chức năng và Quy trình vận hành

Giao diện CallBox Flasher được chia thành 4 khu vực trực quan:

### A. Giám sát Cổng COM & Trạng thái hoạt động (Card 1)
- Tự động quét và phát hiện cổng ESP USB Serial.
- **[Kiểm tra trạng thái (COM)]**: Gửi lệnh `CMD:STATUS` để đọc trực tiếp trạng thái mạng thời gian thực: Wi-Fi STA (kết nối, SSID, IP, RSSI), MQTT Broker, Ethernet, AP và Client ID.
- **[Đọc cấu hình từ chip]**: Gửi lệnh `CMD:CONFIG` để đọc các thông số NVS đang lưu trên chip và tự động điền vào form cấu hình.

### B. Firmware Ứng dụng & Baseline (Card 2)
- Hiển thị thông tin phiên bản baseline nhúng sẵn (Bootloader, Partition Table, Otadata).
- Chọn file `.bin` ứng dụng: Kiểm tra hợp lệ định dạng ESP image, chip ESP32-S3, kích thước <= 2 MiB, project name `callbox_sews`, SHA-256 và application descriptor.

### C. Cấu hình Thiết bị NVS qua Serial (Card 3)
Cho phép cấu hình thiết bị trực tiếp qua cổng COM mà không cần kết nối Wi-Fi hay vào WebUI:
- **Callbox ID**: Mã số thiết bị (mặc định: `001`).
- **Wi-Fi STA**: SSID (mặc định `AGV1`), Mật khẩu (mặc định `123456789`), DHCP hoặc IP tĩnh (IP, Netmask, Gateway, DNS).
- **MQTT Broker**: Địa chỉ (mặc định `wcs.aubot.vn`), Port (mặc định `1883`), TLS, Tài khoản (mặc định `fms`), Mật khẩu (mặc định `Aubot@2025`).
- **Nghiệp vụ WCS**: Phiên bản vận hành (`No version`, `1.0`, `2.0`). Điểm nguồn/đích đã loại bỏ khỏi UI vì server WCS tự động điều phối theo ID và Version.
- **[Mặc định Aubot]**: Khôi phục nhanh tất cả trường về giá trị xuất xưởng chuẩn.

### D. 4 Chế độ nạp độc lập (Card 4)
1. 🟣 **`NẠP CẤU HÌNH`** (`CONFIG_ONLY`):
   - Sinh phân vùng NVS nhị phân `nvs_cfg.bin` 128 KB chuẩn ESP-IDF NVS v2.
   - Nạp trực tiếp vào offset `0x214000` và xác minh mã băm SHA-256 trong **~0.3 giây**!
   - Thiết bị tự động reset và áp dụng cấu hình mới ngay lập tức.
2. 🟢 **`NẠP TOÀN BỘ BOARD`** (`FULL`):
   - Xóa trắng toàn bộ flash SPI trên chip.
   - Nạp Bootloader (`0x000000`), Partition Table (`0x008000`), App (`0x010000`), Otadata (`0x210000`).
   - Ghi đè phân vùng Cấu hình NVS (`0x214000`) với các thông số vừa nhập trên form.
3. 🔵 **`CẬP NHẬT APP`** (`APP_ONLY`):
   - Nạp firmware ứng dụng mới vào `0x010000` mà không làm mất dữ liệu cấu hình đã lưu.
4. 🟡 **`NẠP BOOTLOADER / SETUP`** (`BASELINE_ONLY`):
   - Nạp lại Bootloader, Partition Table và xóa phân vùng Otadata để đưa board về trạng thái xuất xưởng.

### E. Tab Cấu hình từ xa qua MQTT (Không cần cáp USB)
- Kết nối trực tiếp vào MQTT Broker trung tâm (`wcs.aubot.vn` hoặc broker tùy chọn).
- Gửi lệnh cấu hình đặc biệt `remote_config` đến `callbox/<CALLBOX_ID>/cmd`.
- Hỗ trợ **Partial Update** (chỉ cập nhật trường có nhập dữ liệu: Version, Callbox ID, Wi-Fi, MQTT Broker, Reboot).
- **Cơ chế bảo vệ nguyên tử (Atomic Validation):** Firmware tự động ghép mảnh gói tin, kiểm tra tính toàn vẹn cú pháp JSON và xác thực tham số hợp lệ 100% trước khi lưu Flash NVS; tuyệt đối chống lỗi nhận dở dang làm sai lệch cấu hình hoặc mất mạng.
- Lắng nghe và hiển thị phản hồi ACK realtime từ `callbox/<CALLBOX_ID>/event` (`{"type":"config_ack","status":"ok"}`).
- Tích hợp MQTT Console chuyên dụng để giám sát lưu lượng bản tin trao đổi.

---

## 3. Xử lý sự cố & Phục hồi BOOT / RESET

- **Không nhận cổng COM:** Kiểm tra cáp USB (đảm bảo cáp truyền dữ liệu, không phải cáp sạc thuần) và cài đặt driver USB-to-UART.
- **Báo lỗi cổng COM đang bận (Port busy):** Đóng các ứng dụng mở cổng serial như Serial Monitor (Arduino, VS Code, Putty, Mobaxterm, esptool).
- **Lỗi kết nối (Connecting timeout):**
  - Giữ nút **BOOT** trên board, sau đó nhấn nhả nút **RESET**, rồi thả nút **BOOT**.
  - Bấm nút nạp tương ứng để thử lại.
- **Tiến trình bị gián đoạn giữa chừng:** Nếu rút cáp hoặc mất điện trong lúc nạp, flash có thể bị xóa dở. Chỉ cần cắm lại và bấm **NẠP TOÀN BỘ BOARD** để nạp lại từ đầu.

---

## 4. Cấu hình phân vùng cố định & Hash Baseline

Factory Functional Baseline nhúng: `development-a95135d` (development security profile; không đồng nghĩa Security Production Profile)

| Phân vùng | Offset | Kích thước | SHA-256 |
|---|---|---|---|
| `bootloader.bin` | `0x000000` | 21,360 bytes | `4ce06623271ea0477b39ac22d6f7e75fbca1cb4a3cacc870e9b35d9b899186d5` |
| `partition-table.bin` | `0x008000` | 3,072 bytes | `ae79eb7a574d81935ea93c3f794d54557f1ddc7828b98507be04c0b3143ff9bc` |
| `ota_data_initial.bin` | `0x210000` | 8,192 bytes | `7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f` |
| `nvs_cfg` (Cấu hình) | `0x214000` | 131,072 bytes (128 KB) | Sinh động từ form UI theo chuẩn NVS v2 |
| Ứng dụng (`callbox_sews.bin`) | `0x010000` | <= 2 MiB | Được tính toán và xác minh lúc nạp |

---

## 5. Hướng dẫn đóng gói dành cho Maintainer

### Phiên bản phụ thuộc đã ghim:
- `esptool == 5.3.1`
- `pyserial == 3.5`
- `esp-idf-nvs-partition-gen >= 0.1.7`
- `pyinstaller == 6.16.0`

### Quy trình đóng gói tự động:
Chạy script PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File tools/callbox_flasher/build.ps1
```

Script sẽ:
1. Tạo môi trường ảo sạch `.venv-build`.
2. Cài đặt các thư viện phụ thuộc theo `requirements-build.txt`.
3. Chạy toàn bộ bộ kiểm thử tự động `tests` (48 tests).
4. Nhúng biểu tượng icon CallBox Win32 (`assets/app.ico`) vào file thực thi.
5. Đóng gói thành `tools/callbox_flasher/dist/CallBox-Flasher.exe`.
6. Chạy `--self-test` trên file EXE vừa tạo để kiểm tra tính toàn vẹn của asset nhúng.
7. In mã băm SHA-256 của file EXE hoàn chỉnh.


> **Remote config:** Operating Version được áp dụng transaction-safe vào runtime + NVS. Với CallBox ID/Wi-Fi/MQTT, `reboot=false` nghĩa là cấu hình đã lưu NVS nhưng transport/identity đang chạy có thể chỉ áp dụng đầy đủ sau reboot; Production Flasher mặc định `reboot=true`.
