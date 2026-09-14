# CallBox Production Flasher Release Evidence & Checklist

**Ngày lập/cập nhật:** 2026-09-10
**Phiên bản công cụ:** V1.3.1 Factory Functional Release
**Tập tin thực thi:** `tools/callbox_flasher/dist/CallBox-Flasher.exe`
**Kích thước:** 20,055,282 bytes (~19.1 MB)
**SHA-256 (CallBox-Flasher.exe):** `86168C21B7C0805BD20206930B4A44867EA5DC2970F20CF911D4385B23AAD516`
**Chữ ký số (Authenticode):** `NotSigned` (chưa ký số, bản phân phối nội bộ nhà máy)
**Source baseline commit nhúng trong firmware:** `62f4357d801ac97ea4b07f87f9914df91d299b3c`
**ESP-IDF App version trong `callbox_sews.bin`:** `62f4357` (clean source build, không có hậu tố `-dirty`)
**Firmware SHA-256:** `304DDCD9A6B7EC955DB306ED08CEA12436768EE48B847E21C1D6E6C1C66F5A22`
**Release model:** source commit được khóa trước; artifact/checklist nằm ở packaging commit sau. Không tuyên bố bit-reproducible giữa các lần build vì compile timestamp có thể làm SHA thay đổi.

## 1. Kết quả kiểm thử tự động (Automated Verification)

- [x] **Toàn bộ 55 bài kiểm thử đơn vị Flasher PASS (0 lỗi, 0 failure)**
  - `tools.callbox_flasher.tests.test_app` (7/7 pass, bao gồm auto-detect firmware, +1 ID increment, default version 2.0)
  - `tools.callbox_flasher.tests.test_controller` (9/9 pass)
  - `tools.callbox_flasher.tests.test_esptool_adapter` (12/12 pass)
  - `tools.callbox_flasher.tests.test_flash_manifest` (4/4 pass)
  - `tools.callbox_flasher.tests.test_image_validator` (8/8 pass)
  - `tools.callbox_flasher.tests.test_nvs_generator` (4/4 pass)
  - `tools.callbox_flasher.tests.test_ports` (5/5 pass)
  - `tools.callbox_flasher.tests.test_remote_config` (3/3 pass, partial/full serialization và broker defaults)
  - `tools.callbox_flasher.tests.test_serial_reader` (3/3 pass)
- [x] **Xác minh SHA-256 các image baseline nhúng khớp 100% với manifest:**
  - `bootloader.bin`: `4ce06623271ea0477b39ac22d6f7e75fbca1cb4a3cacc870e9b35d9b899186d5`
  - `partition-table.bin`: `ae79eb7a574d81935ea93c3f794d54557f1ddc7828b98507be04c0b3143ff9bc`
  - `ota_data_initial.bin`: `7d2c7ac4888bfd75cd5f56e8d61f69595121183afc81556c876732fd3782c62f`
- [x] **Nhúng sẵn Firmware ứng dụng xuất xưởng chính thức (`callbox_sews.bin` v1.3.1):**
  - Kích thước: 1,271,184 bytes (`0x136590`), 39% free (`0xc9a70` bytes)
  - SHA-256: `304DDCD9A6B7EC955DB306ED08CEA12436768EE48B847E21C1D6E6C1C66F5A22`
  - Khớp 100% giữa `build/callbox_sews.bin` và `tools/callbox_flasher/assets/callbox_sews.bin`
  - Tự động phát hiện và nạp sẵn ngay khi khởi chạy công cụ, kỹ thuật viên không cần duyệt file thủ công.
  - Hỗ trợ nút `+1` tăng nhanh số thứ tự Callbox ID theo lô sản xuất.
  - Mặc định xuất xưởng: Version 2.0 (tự động khóa tắt `list_pub = 0`).
- [x] **Khắc phục giao thức USB-Serial/JTAG CDC:**
  - Tự động kích hoạt `DTR = True` cho phép đọc cấu hình và trạng thái thiết bị thực tế qua cáp Type-C ổn định 100%.
- [x] **Xác minh kiểm tra firmware ứng dụng (`callbox_sews.bin`):**
  - Project name: `callbox_sews`
  - Product firmware version: `1.3.1` (`CALLBOX_FIRMWARE_VERSION`)
  - ESP-IDF App version / source trace: `62f4357`
  - Chip ID: `9` (ESP32-S3)
  - Kích thước: `<= 2 MiB` (1,271,184 bytes)
  - Checksum & validation hash hợp lệ
- [x] **Sinh phân vùng NVS nhị phân chuẩn ESP-IDF v2 (`0x214000`):**
  - Kích thước chính xác 131,072 bytes (128 KB)
  - Schema business: `callbox_id`, Wi-Fi, MQTT, `mode_ver`; legacy compatibility keys `list_pub`, `lp_src`, `lp_dst` vẫn tồn tại nhưng production luôn sinh `list_pub=0`, `lp_src=""`, `lp_dst=""`.
- [x] **Từ chối trước khi xóa flash (Pre-erase rejections):**
  - Từ chối file không phải đuôi `.bin`
  - Từ chối file vượt quá 2 MiB
  - Từ chối file bị hỏng hash/checksum
  - Từ chối file sai project descriptor
  - Từ chối thiết bị không phải chip ESP32-S3
- [x] **Bảo vệ log kỹ thuật (Log sanitization):**
  - Mọi mật khẩu, token, secret được tự động thay thế bằng `***`.
- [x] **Tự kiểm tra nhúng tài nguyên file EXE (`--self-test`):**
  - Mã thoát `0`, khởi tạo thành công 3 ảnh baseline và nvs generator độc lập.

### Software release gate 2026-09-10

- [x] CallBox host contract: **84/84 PASS**.
- [x] Flasher unit tests trong build environment sạch: **55/55 PASS**.
- [x] Firmware clean build từ source commit `62f4357`: **PASS**.
- [x] `callbox_sews.bin` trong Flasher khớp SHA-256 với release build: **PASS**.
- [x] `CallBox-Flasher.exe --self-test`: **PASS**.
- [x] Business contract: CallBox chỉ dùng **ID + Operating Version + Task**; Source/Destination/Listpoint không còn là business responsibility.
- [x] OTA normal mode: cho phép khi `COMM_READY` hoặc `COMM_SYNCING` nếu hai task idle và không có CALL/CANCEL pending; `COMM_OFFLINE` bị chặn.
- [x] SYNCING indication: Vàng sáng liên tục + Đỏ nháy kép 180/180/180 ms, nghỉ khoảng 1 s và lặp lại.
- [x] Ba topic listpoint cũ chỉ còn **legacy retained cleanup**.
- [x] `remote_config` được mô tả là Tech management extension; không phải command nghiệp vụ bắt buộc của IT/WCS.


---

## 2. Trạng thái kiểm thử phần cứng thực tế (Hardware Acceptance - COM15)

> **Cập nhật 2026-09-10:** firmware v1.3.1 từ source `62f4357` đã được nạp **APP_ONLY** trực tiếp lên bo Waveshare ESP32-S3 tại `COM15`; flash verify digest PASS, board reset/boot lại và giữ nguyên NVS. Sau boot: CallBox ID `001`, Operating Version `2.0`, Wi-Fi STA và MQTT đều kết nối. Các mục CONFIG_ONLY/CMD trước đó vẫn là evidence đã chạy ngày 08/09/2026.

Đã thực hiện nghiệm thu trực tiếp trên bo mạch phần cứng Waveshare ESP32-S3 kết nối cổng `COM15`:

- [x] **Nạp APP_ONLY firmware v1.3.1 trên Waveshare ESP32-S3 / COM15:** PASS — ghi `callbox_sews.bin` tại `0x10000`, verify digest khớp, hard reset thành công; NVS được giữ nguyên.
- [x] **Post-flash boot check v1.3.1:** PASS — thiết bị trở lại `CallBox ID=001`, `Version=2.0`, Wi-Fi STA online và MQTT connected.
- [x] **Giao thức Serial PING (`CMD:PING`):** PASS — nhận chuỗi phản hồi `>>>AUBOT:PONG<<<`.
- [x] **Truy vấn trạng thái trực tiếp (`CMD:STATUS`):** PASS — đọc trực tiếp `sta=1`, `ssid="AGV1"`, `mqtt=1`, `client_id="AUBOT-Callbox-001"`.
- [x] **Truy vấn cấu hình NVS (`CMD:CONFIG`):** PASS — giải mã chính xác JSON cấu hình từ NVS lưu trên chip.
- [x] **Nạp cấu hình độc lập (`CONFIG_ONLY`):** PASS — ghi đè thông số mới vào phân vùng `0x214000` trong ~0.3s, verify hash khớp 100%, chip tự reset nạp cấu hình mới.
- [x] **Khôi phục cấu hình chuẩn xuất xưởng:** PASS - nạp lại profile triển khai đã được phê duyệt; không lưu credential trong release evidence.
- [x] **Khởi động lại từ xa (`CMD:REBOOT`):** PASS — chip thực hiện hard reset qua `esp_restart()` và tự khôi phục kết nối mạng.
- [ ] **Khởi chạy trên máy Windows sạch (Clean machine launch):** Cần copy file `CallBox-Flasher.exe` sang máy trạm độc lập không có Python để chạy kiểm tra giao diện Win32.

---

## 3. Phạm vi bảo mật của Factory Functional Baseline

- [x] **Xác nhận giới hạn bảo mật V1:** Đã ghi rõ trong giao diện người dùng và README rằng Factory Functional Baseline dùng development security profile, chưa bật Secure Boot / Flash Encryption và chưa đốt eFuse.
- [x] **Lưu ý CallBox ID:** Đã tích hợp cấu hình CallBox ID ngay từ công cụ nạp Serial, không bắt buộc phải vào WebUI đổi thủ công nếu đã nạp cấu hình qua tool.
