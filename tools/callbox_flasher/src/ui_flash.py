import queue
import threading
from tkinter import messagebox

from tools.callbox_flasher.src.factory_profile import validate_factory_profile_for_worker
from tools.callbox_flasher.src.image_validator import validate_application
from tools.callbox_flasher.src.models import ProvisionEvent, ProvisionMode, ProvisionState
from tools.callbox_flasher.src.serial_reader import query_device_config, query_device_status
from tools.callbox_flasher.src.ui_state import (
    STATE_COPY, can_flash, can_flash_baseline, can_flash_bundle, can_flash_config,
)
from tools.callbox_flasher.src.ui_theme import COLORS


class FlashWorkflowMixin:
    def _on_check_status_click(self) -> None:
        """Gửi lệnh kiểm tra trạng thái ESP32 qua Serial trong luồng nền."""
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showwarning(
                "Chưa chọn cổng",
                "Vui lòng chọn cổng COM trước khi kiểm tra trạng thái.",
                parent=self.root,
            )
            return

        if self.controller.busy:
            return

        self.live_status_label.config(text="Đang đọc trạng thái từ cổng COM...", fg="#2563eb")
        self._append_log(f"--- Đang gửi yêu cầu kiểm tra trạng thái tới {port} ---")

        def worker():
            try:
                status = query_device_status(port)
                def update_ui():
                    sta_icon = "🟢" if status.get("sta") else "⚪"
                    mqtt_icon = "🟢" if status.get("mqtt") else "⚪"
                    sta_txt = f"{sta_icon} WiFi STA: {'Đã kết nối (' + status.get('ssid','') + ', IP: ' + status.get('ip','') + ')' if status.get('sta') else 'Chưa kết nối'}"
                    mqtt_txt = f"{mqtt_icon} MQTT: {'Đã kết nối' if status.get('mqtt') else 'Chưa kết nối'}"
                    client_txt = f"ID: {status.get('client_id', '')}"
                    self.live_status_label.config(
                        text=f"{sta_txt} | {mqtt_txt} | {client_txt}",
                        fg="#15803d" if status.get("sta") else COLORS.muted,
                    )
                    self._append_log(f"Trạng thái nhận được: STA={status.get('sta')}, IP={status.get('ip')}, RSSI={status.get('rssi')}, MQTT={status.get('mqtt')}, ClientID={status.get('client_id')}")
                self.root.after(0, update_ui)
            except Exception as e:
                def on_err():
                    self.live_status_label.config(text=f"Lỗi đọc trạng thái: {e}", fg=COLORS.danger)
                    self._append_log(f"Lỗi kiểm tra trạng thái: {e}")
                self.root.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()
    def _on_read_config_click(self) -> None:
        """Gửi lệnh đọc cấu hình hiện tại từ NVS của ESP32 qua Serial và điền vào form."""
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showwarning(
                "Chưa chọn cổng",
                "Vui lòng chọn cổng COM trước khi đọc cấu hình.",
                parent=self.root,
            )
            return

        if self.controller.busy:
            return

        self.live_status_label.config(text="Đang đọc cấu hình từ ESP32...", fg="#2563eb")
        self._append_log(f"--- Đang đọc cấu hình từ thiết bị trên {port} ---")

        def worker():
            try:
                cfg = query_device_config(port)
                def update_ui():
                    self.cfg_id_var.set(cfg.callbox_id)
                    self.cfg_ssid_var.set(cfg.wifi_ssid)
                    self.cfg_pass_var.set(cfg.wifi_pass)
                    self.cfg_dhcp_var.set(cfg.wifi_dhcp)
                    self.cfg_broker_var.set(cfg.mqtt_broker)
                    self.cfg_port_var.set(str(cfg.mqtt_port))
                    self.cfg_user_var.set(cfg.mqtt_user)
                    self.cfg_mqtt_pass_var.set(cfg.mqtt_pass)
                    self.cfg_ver_var.set(cfg.operating_version if cfg.operating_version in ["No version", "1.0", "2.0"] else "No version")
                    # Không hiển thị listpoints — WCS/IT tự điều phối
                    self._on_version_changed()
                    self.live_status_label.config(text="Đã đọc và đồng bộ cấu hình từ chip thành công.", fg=COLORS.success)
                    self._append_log(f"Cấu hình nhận được: Callbox ID={cfg.callbox_id}, SSID={cfg.wifi_ssid}, Broker={cfg.mqtt_broker}, Version={cfg.operating_version}")
                self.root.after(0, update_ui)
            except Exception as e:
                def on_err():
                    self.live_status_label.config(text=f"Lỗi đọc cấu hình: {e}", fg=COLORS.danger)
                    self._append_log(f"Lỗi đọc cấu hình từ chip: {e}")
                self.root.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()
    def _auto_query_status_after_flash(self) -> None:
        """Tự động kiểm tra lại trạng thái board sau khi nạp xong."""
        if not self.controller.busy:
            self._on_check_status_click()
    def _on_flash_config_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash_config(port, self.controller.busy):
            return

        cfg = self._get_device_config_from_ui()
        confirm = messagebox.askyesno(
            "Xác nhận NẠP CẤU HÌNH",
            f"Nạp cấu hình vào phân vùng NVS (0x214000) cho thiết bị trên cổng {port}?\n\n"
            f"• Cổng COM: {port}\n"
            f"• Callbox ID: {cfg.callbox_id}\n"
            f"• Phiên bản xuất xưởng: Version {cfg.operating_version}\n"
            f"• Wi-Fi SSID: {cfg.wifi_ssid}\n"
            f"• MQTT Broker: {cfg.mqtt_broker}:{cfg.mqtt_port}\n\n"
            "Chỉ nạp phân vùng cấu hình NVS trong ~2 giây (không nạp lại firmware/bootloader).\n"
            "Bạn có muốn tiếp tục?",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.CONFIG_ONLY)
    def _on_flash_baseline_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash_baseline(port, self.controller.busy):
            return

        confirm = messagebox.askyesno(
            "Xác nhận NẠP BOOTLOADER / SETUP",
            f"Nạp cấu hình baseline (Bootloader, Bảng phân vùng 16MB, OTA data) cho thiết bị trên cổng {port}?\n\n"
            "• Khởi tạo phân vùng và bootloader tiêu chuẩn cho board mới\n"
            "• Thao tác này KHÔNG CẦN file firmware ứng dụng\n\n"
            "Bạn có muốn tiếp tục?",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.BASELINE_ONLY)
    def _on_flash_bundle_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash_bundle(port, self.bundle_info is not None, self.controller.busy):
            return
        try:
            manifest = self.release_manager.load_active_firmware_manifest()
            manifest.verify_assets()
            embedded = validate_application(manifest.application.path)
        except Exception as error:
            messagebox.showerror("G\u00f3i firmware kh\u00f4ng h\u1ee3p l\u1ec7", str(error), parent=self.root)
            return
        confirm = messagebox.askyesno(
            "X\u00e1c nh\u1eadn N\u1ea0P FIRMWARE - 1 CLICK",
            f"N\u1ea1p g\u00f3i firmware t\u00edch h\u1ee3p trong EXE v\u00e0o thi\u1ebft b\u1ecb tr\u00ean {port}?\n\n"
            f"Application: {embedded.project} | {embedded.version}\n"
            "Bootloader: 0x0\nPartition table: 0x8000\nApplication: 0x10000\nOTA data: 0x210000\n\n"
            "GI\u1eee NGUY\u00caN nvs_cfg / nvs_runtime: Callbox ID, Wi-Fi, MQTT v\u00e0 d\u1eef li\u1ec7u runtime.\n\n"
            "C\u1ea3 4 image s\u1ebd \u0111\u01b0\u1ee3c verify tr\u01b0\u1edbc khi board kh\u1edfi \u0111\u1ed9ng l\u1ea1i.",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return
        self._start_flashing(port, ProvisionMode.FIRMWARE_BUNDLE)
    def _on_flash_full_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash_bundle(port, self.bundle_info is not None, self.controller.busy):
            return

        try:
            manifest = self.release_manager.load_active_firmware_manifest()
            manifest.verify_assets()
            embedded = validate_application(manifest.application.path)
            cfg = self._get_device_config_from_ui()
            validate_factory_profile_for_worker(cfg)
        except Exception as error:
            messagebox.showerror("Chưa sẵn sàng nạp xưởng", str(error), parent=self.root)
            return

        message = (
            f"Nạp xưởng Callbox trên cổng {port}?\n\n"
            "GÓI NẠP XƯỞNG:\n"
            f"• Firmware: v{embedded.version}\n"
            f"• Callbox ID: {cfg.callbox_id}\n"
            f"• Operating Version: {cfg.operating_version}\n"
            f"• Wi-Fi SSID: {cfg.wifi_ssid}\n"
            f"• MQTT Broker: {cfg.mqtt_broker}:{cfg.mqtt_port}\n\n"
            "TOOL SẼ TỰ ĐỘNG:\n"
            "1. Xóa toàn bộ Flash\n"
            "2. Nạp Bootloader\n"
            "3. Nạp Partition table + OTA data\n"
            "4. Nạp Application\n"
            "5. Nạp NVS cấu hình xưởng\n"
            "6. Verify toàn bộ và khởi động lại\n\n"
            "Đây là luồng NẠP XƯỞNG chuẩn."
        )
        confirm = messagebox.askyesno(
            "Xác nhận NẠP CALLBOX / NẠP XƯỞNG",
            message,
            icon="warning",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.FACTORY)

    def _on_flash_app_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash(port, self.app_info is not None, self.controller.busy):
            return

        confirm = messagebox.askyesno(
            "Xác nhận CẬP NHẬT ỨNG DỤNG",
            f"Cập nhật firmware ứng dụng cho board trên cổng {port}?\n\n"
            f"• Dự án: {self.app_info.project} | Phiên bản: {self.app_info.version}\n"
            "• Ghi đè vào phân vùng 0x10000 (Factory)\n"
            "• Reset trạng thái OTA về Factory\n"
            "• GIỮ NGUYÊN cấu hình WiFi và dữ liệu NVS hiện có\n\n"
            "Bạn có muốn tiếp tục?",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.APP_ONLY)
    def _start_flashing(self, port: str, mode: ProvisionMode) -> None:
        self._set_inputs_enabled(False)
        self.banner_label.config(text="")
        self.result_details_label.config(text="")
        self.progress_bar["value"] = 0

        dev_config = None
        if mode == ProvisionMode.FIRMWARE_BUNDLE:
            mode_str = "CẬP NHẬT FIRMWARE (Boot + Partition + OTA + App, giữ NVS)"
        elif mode == ProvisionMode.FACTORY:
            mode_str = "NẠP CALLBOX / NẠP XƯỞNG"
            dev_config = self._get_device_config_from_ui()
            validate_factory_profile_for_worker(dev_config)
        elif mode == ProvisionMode.CONFIG_ONLY:
            mode_str = "NẠP CẤU HÌNH NVS (0x214000)"
            dev_config = self._get_device_config_from_ui()
        elif mode == ProvisionMode.APP_ONLY:
            mode_str = f"CẬP NHẬT ỨNG DỤNG ({self.app_info.path.name})"
        else:
            mode_str = "NẠP BOOTLOADER / SETUP"
        self._append_log(f"--- Bắt đầu {mode_str} vào {port} ---")

        if mode in (ProvisionMode.FIRMWARE_BUNDLE, ProvisionMode.FACTORY):
            manifest = self.release_manager.load_active_firmware_manifest()
            manifest.verify_assets()
            app_path = manifest.application.path
        else:
            app_path = self.app_info.path if self.app_info else None
        self.controller.start(
            port=port,
            application=app_path,
            emit=self.event_queue.put,
            mode=mode,
            config=dev_config,
        )
    def _drain_events(self) -> None:
        if getattr(self, "_closing", False):
            return
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            if not getattr(self, "_closing", False):
                self._drain_events_after_id = self.root.after(50, self._drain_events)
    def _handle_event(self, event: ProvisionEvent) -> None:
        if getattr(self, "_worker_job_active", False) and hasattr(self, "_worker_render_event"):
            self._worker_render_event(event)
        if event.technical:
            self._append_log(event.technical)

        self.phase_label.config(text=STATE_COPY.get(event.state, event.message))
        self.progress_bar["value"] = event.progress

        if event.state == ProvisionState.SUCCEEDED:
            self._set_inputs_enabled(True)
            res = event.result
            mac_str = res.mac.upper() if res and res.mac else "N/A"
            time_str = f"{res.elapsed_seconds}s" if res else ""
            version_str = res.version if res else ""

            if res and res.mode == ProvisionMode.FIRMWARE_BUNDLE:
                banner_text = "CẬP NHẬT FIRMWARE THÀNH CÔNG"
                detail_note = "Đã ghi và verify Bootloader + Partition + OTA data + Application; NVS được giữ nguyên."
                self.root.after(3500, self._auto_query_status_after_flash)
            elif res and res.mode == ProvisionMode.FACTORY:
                banner_text = "NẠP XƯỞNG THÀNH CÔNG"
                detail_note = (
                    f"Đã nạp Bootloader + Partition + OTA data + Application + NVS (ID: {self.cfg_id_var.get().strip()}). "
                    "Board đang khởi động lại."
                )
                self.root.after(4000, self._auto_query_status_after_flash)
            elif res and res.mode == ProvisionMode.CONFIG_ONLY:
                banner_text = "NẠP CẤU HÌNH THÀNH CÔNG"
                detail_note = (
                    f"Đã nạp cấu hình NVS (ID: {self.cfg_id_var.get().strip()}) vào 0x214000. "
                    "Board đang khởi động lại."
                )
                self.root.after(3500, self._auto_query_status_after_flash)
            elif res and res.mode == ProvisionMode.APP_ONLY:
                banner_text = "CẬP NHẬT APP THÀNH CÔNG"
                detail_note = "Toàn bộ cấu hình WiFi và dữ liệu NVS được giữ nguyên vẹn."
                self.root.after(3500, self._auto_query_status_after_flash)
            else:
                banner_text = "NẠP BOOTLOADER / SETUP THÀNH CÔNG"
                detail_note = (
                    "Bootloader và bảng phân vùng đã sẵn sàng. "
                    "Bạn có thể nạp tiếp firmware hoặc cấu hình bất cứ lúc nào."
                )

            self.banner_label.config(
                text=banner_text,
                fg=COLORS.success,
            )
            self.result_details_label.config(
                text=f"MAC: {mac_str} | Phiên bản: {version_str} | Thời gian: {time_str}\n{detail_note}",
                fg="#15803d",
            )
            self._append_log(f"--- {banner_text} (MAC: {mac_str}, Version: {version_str}) ---")
            self._refresh_ports()

        elif event.state == ProvisionState.FAILED:
            self._set_inputs_enabled(True)
            self.banner_label.config(
                text="THAO TÁC THẤT BẠI",
                fg=COLORS.danger,
            )
            self.result_details_label.config(
                text=f"Nguyên nhân: {event.message}",
                fg=COLORS.danger_text,
            )
            self._append_log(f"--- THẤT BẠI: {event.message} ---")
