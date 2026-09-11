# Hướng dẫn nhanh – AUBOT Setup CallBox

## 1. Chuẩn bị
- Chạy `Setup-CallBox.exe` trên Windows 10/11 x64.
- Kết nối CallBox ESP32-S3 bằng USB.
- Tool kiểm tra đúng chip ESP32-S3 trước thao tác ghi flash.
- Wi-Fi/MQTT deployment không nhúng trong bản public. Nhập trên GUI hoặc đặt file private `Setup-CallBox.factory.json` cạnh EXE.

Sao chép `factory-profile.example.json`, đổi tên thành `Setup-CallBox.factory.json`, rồi điền thông tin nội bộ trên máy kỹ thuật. File private này không được commit/push.

## 2. Các chế độ nạp
- **CONFIG_ONLY**: ghi/verify NVS tại `0x214000`.
- **APP_ONLY**: ghi application tại `0x10000`, giữ NVS.
- **BASELINE_ONLY**: nạp bootloader, partition table và OTA data baseline.
- **FULL**: erase toàn bộ rồi nạp baseline + application + NVS; dùng cho board mới/factory hoặc khôi phục hoàn toàn.

## 3. Contract CallBox
Tech cấu hình `CallBox ID + Operating Version`; `1.0` = 1 logical button, `2.0` = 2 logical buttons. Source/Destination/Listpoint/route/fleet thuộc IT/WCS.

## 4. Kiểm tra sau nạp
- `CMD:CONFIG`: xác nhận ID + Version + NVS.
- `CMD:STATUS`: xác nhận network/MQTT/client ID.
- Sau reboot có thể cần vài giây để network reconnect.

## 5. Cập nhật Setup CallBox
Nút **Update** kiểm tra GitHub Releases. Tool tải `Setup-CallBox.exe` + `.sha256`, xác minh URL release/kích thước/SHA-256, sau đó helper thay EXE cũ và mở lại. Updater bị khóa khi đang nạp ESP32.
