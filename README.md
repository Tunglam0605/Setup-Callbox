# Setup CallBox

**AUBOT Setup CallBox** là công cụ sản xuất, nạp firmware và cấu hình thiết bị CallBox SEWS (ESP32-S3) dành cho nhà máy và kỹ thuật viên vận hành.

---

## 1. Thông tin bản phát hành xuất xưởng (Production Release)

- **Phiên bản Tool (Setup-CallBox):** **`v1.3.6`**
- **Phiên bản Firmware nhúng sẵn:** **`v1.5.6`** (`callbox_sews`)
- **Phần cứng hỗ trợ:** **Waveshare ESP32-S3-POE-ETH-8DI-8DO** (ESP32-S3, 16 MB Flash)
- **File chạy độc lập Windows:** `Setup-CallBox.exe`
- **Mã băm SHA-256 (`Setup-CallBox.exe`):** `d53398a172f0c62c5a68b0a237556c34db9b4b2b35fdf0593a5b965a4ede0ea3`

---

## 2. Cấu trúc thư mục bàn giao cho nhà máy

```text
Setup-Callbox/
├── Setup-CallBox.exe                 # Ứng dụng chạy trực tiếp trên Windows (1 click nạp máy)
├── Setup-CallBox.exe.sha256          # Checksum kiểm tra toàn vẹn file chạy
├── release-manifest.json             # Manifest thông tin phát hành chính thức
├── firmware/                         # Thư mục chứa firmware và mã nguồn theo kèm
│   ├── v1.5.6/                       # Bộ ảnh nhị phân cơ sở (Bootloader, Partition Table, App, Otadata)
│   ├── callbox_sews_v1.5.6_OTA.bin   # File binary dùng để cập nhật từ xa qua Web Portal
│   ├── callbox_sews.bin              # File binary nạp trực tiếp
│   └── Code_Callbox_SEWS_v1.5.6_Tool_v1.3.6_20260914.zip # Mã nguồn đầy đủ của dự án
└── tools/
    └── callbox_flasher/              # Toàn bộ mã nguồn Python và bộ test của Tool
        ├── HUONG_DAN_SAN_XUAT.md     # Quy trình thao tác chuẩn (SOP) cho công nhân nhà xưởng
        ├── src/                      # Mã nguồn Python (Controller, UI, ESPTool, NVS, MQTT)
        ├── assets/                   # Ảnh nhị phân nạp xuất xưởng
        └── tests/                    # 121 bài kiểm thử tự động (Unit tests)
```

---

## 3. Hướng dẫn nhanh cho nhà máy

1. Tải về hoặc mở trực tiếp file `Setup-CallBox.exe`.
2. Cắm bo mạch Callbox qua cáp Type-C vào cổng USB máy tính.
3. Chọn cổng COM tương ứng (ví dụ: `COM5`, `COM15`).
4. Nhập Callbox ID (ví dụ: `001`, `002`), thông số Wi-Fi và MQTT.
5. Bấm nút **`NẠP TOÀN BỘ BOARD (FULL)`** để hoàn tất nạp và cấu hình trong 1 bước.
6. Xem hướng dẫn chi tiết tại [tools/callbox_flasher/HUONG_DAN_SAN_XUAT.md](tools/callbox_flasher/HUONG_DAN_SAN_XUAT.md).

---

## 4. Kiểm thử tự động (Verification)

Chạy kiểm thử bộ mã nguồn Tool:
```bash
python -m unittest discover tools/callbox_flasher/tests
# 121/121 tests PASS
```
