import pathlib
import re
import sys
import tkinter as tk
from tkinter import filedialog, ttk

from tools.callbox_flasher.src.image_validator import ImageValidationError, validate_application
from tools.callbox_flasher.src.models import DeviceConfig, ProvisionState
from tools.callbox_flasher.src.ports import automatic_port, discover_ports
from tools.callbox_flasher.src.resources import resource_path
from tools.callbox_flasher.src.ui_state import STATE_COPY, can_flash, can_flash_baseline, can_flash_bundle, can_flash_config
from tools.callbox_flasher.src.ui_theme import COLORS


class ProductionUiMixin:
    def _build_connection_card(self, tab_usb: tk.Frame) -> None:
        bg_canvas = COLORS.canvas
        card_bg = COLORS.white
        border_color = COLORS.border
        # ==================== CARD 1: CỔNG COM ====================
        card_conn = tk.Frame(
            tab_usb,
            bg=card_bg,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        card_conn.pack(fill=tk.X, pady=4)
        self.device_connection_card = card_conn

        tk.Label(
            card_conn,
            text="1. KẾT NỐI BOARD ESP32-S3",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        ).pack(anchor=tk.W)

        port_row = tk.Frame(card_conn, bg=card_bg)
        port_row.pack(fill=tk.X, pady=(6, 2))

        tk.Label(
            port_row,
            text="Cổng COM:",
            font=("Segoe UI", 10),
            fg=COLORS.text_secondary,
            bg=card_bg,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.port_combo = ttk.Combobox(port_row, state="readonly", width=18, font=("Segoe UI", 10))
        self.port_combo.pack(side=tk.LEFT, padx=5)
        self.port_combo.bind("<<ComboboxSelected>>", self._on_port_selected)

        self.btn_refresh = ttk.Button(
            port_row,
            text="Làm mới cổng",
            command=self._refresh_ports,
            style="Secondary.TButton",
        )
        # Auto-refresh runs in the background; keep widget for state compatibility but do not show it.

        self.btn_check_status = ttk.Button(
            port_row,
            text="Kiểm tra trạng thái (COM)",
            command=self._on_check_status_click,
            style="Secondary.TButton",
        )
        self.btn_check_status.pack(side=tk.LEFT, padx=4)

        self.btn_read_config = ttk.Button(
            port_row,
            text="Đọc cấu hình từ chip",
            command=self._on_read_config_click,
            style="Secondary.TButton",
        )
        self.btn_read_config.pack(side=tk.LEFT, padx=4)

        self.port_desc_label = tk.Label(
            card_conn,
            text="Chưa chọn thiết bị",
            font=("Segoe UI", 9),
            fg=COLORS.muted,
            bg=card_bg,
        )
        self.port_desc_label.pack(anchor=tk.W, pady=(3, 0))

        self.live_status_label = tk.Label(
            card_conn,
            text="Trạng thái ESP32: Chưa kiểm tra (Nhấn 'Kiểm tra trạng thái (COM)' để đọc qua Serial)",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.muted,
            bg=card_bg,
        )
        self.live_status_label.pack(anchor=tk.W, pady=(2, 0))

    def _build_firmware_card(self, tab_usb: tk.Frame) -> None:
        bg_canvas = COLORS.canvas
        card_bg = COLORS.white
        border_color = COLORS.border
        # ==================== CARD 2: FIRMWARE ỨNG DỤNG ====================
        card_fw = tk.Frame(
            tab_usb,
            bg=card_bg,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        card_fw.pack(fill=tk.X, pady=4)
        self.device_firmware_card = card_fw

        tk.Label(
            card_fw,
            text="2. FIRMWARE ỨNG DỤNG (.BIN)",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        ).pack(anchor=tk.W)

        fw_row = tk.Frame(card_fw, bg=card_bg)
        fw_row.pack(fill=tk.X, pady=(6, 2))

        self.fw_path_var = tk.StringVar()
        self.fw_entry = ttk.Entry(
            fw_row,
            textvariable=self.fw_path_var,
            state="readonly",
            font=("Segoe UI", 9),
        )
        self.fw_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self.btn_browse = ttk.Button(
            fw_row,
            text="Chọn file .bin...",
            command=self._on_browse,
            style="Secondary.TButton",
        )
        self.btn_browse.pack(side=tk.RIGHT)

        self.fw_meta_label = tk.Label(
            card_fw,
            text="Chưa chọn file firmware (Chỉ bắt buộc khi Cập nhật App hoặc Nạp toàn bộ board)",
            font=("Segoe UI", 9),
            fg=COLORS.muted,
            bg=card_bg,
            wraplength=800,
            justify=tk.LEFT,
        )
        self.fw_meta_label.pack(anchor=tk.W, pady=(3, 0))

    def _build_config_card(self, tab_usb: tk.Frame) -> None:
        bg_canvas = COLORS.canvas
        card_bg = COLORS.white
        border_color = COLORS.border
        profile = getattr(self, "factory_profile", None)
        # ==================== CARD 3: CẤU HÌNH THIẾT BỊ NVS ====================
        card_cfg = tk.Frame(
            tab_usb,
            bg=card_bg,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        card_cfg.pack(fill=tk.X, pady=4)
        self.device_config_card = card_cfg

        cfg_header_row = tk.Frame(card_cfg, bg=card_bg)
        cfg_header_row.pack(fill=tk.X)

        tk.Label(
            cfg_header_row,
            text="3. CẤU HÌNH THIẾT BỊ (NVS CONFIG - Phân vùng nvs_cfg 0x214000)",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        ).pack(side=tk.LEFT)

        self.btn_reset_defaults = ttk.Button(
            cfg_header_row,
            text="Dùng mặc định đã lưu",
            command=self._on_reset_defaults_click,
            style="Secondary.TButton",
        )
        self.btn_reset_defaults.pack(side=tk.RIGHT)

        cfg_grid = tk.Frame(card_cfg, bg=card_bg)
        cfg_grid.pack(fill=tk.X, pady=(6, 2))

        # Dòng 0: Callbox ID, WiFi SSID, WiFi Pass, DHCP
        tk.Label(cfg_grid, text="Callbox ID:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_id_var = tk.StringVar(value=(profile.callbox_id if profile else "001"))
        id_frame = tk.Frame(cfg_grid, bg=card_bg)
        id_frame.grid(row=0, column=1, sticky=tk.W, padx=(0, 10), pady=2)
        self.entry_id = ttk.Entry(id_frame, textvariable=self.cfg_id_var, width=7, font=("Segoe UI", 9))
        self.entry_id.pack(side=tk.LEFT)
        self.btn_inc_id = ttk.Button(
            id_frame,
            text="+1",
            width=3,
            style="Secondary.TButton",
            command=self._increment_callbox_id,
        )
        self.btn_inc_id.pack(side=tk.LEFT, padx=(2, 0))

        tk.Label(cfg_grid, text="WiFi SSID:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_ssid_var = tk.StringVar(value=(profile.wifi_ssid if profile else ""))
        self.entry_ssid = ttk.Entry(cfg_grid, textvariable=self.cfg_ssid_var, width=16, font=("Segoe UI", 9))
        self.entry_ssid.grid(row=0, column=3, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="WiFi Pass:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_pass_var = tk.StringVar(value=(profile.wifi_pass if profile else ""))
        self.entry_pass = ttk.Entry(cfg_grid, textvariable=self.cfg_pass_var, width=16, font=("Segoe UI", 9), show="*")
        self.entry_pass.grid(row=0, column=5, sticky=tk.W, padx=(0, 10), pady=2)

        self.cfg_dhcp_var = tk.BooleanVar(value=True)
        self.chk_dhcp = ttk.Checkbutton(cfg_grid, text="DHCP", variable=self.cfg_dhcp_var)
        self.chk_dhcp.grid(row=0, column=6, sticky=tk.W, pady=2)

        # Dòng 1: MQTT Broker, Cổng, MQTT User, MQTT Pass
        tk.Label(cfg_grid, text="MQTT Broker:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_broker_var = tk.StringVar(value=(profile.mqtt_broker if profile else ""))
        self.entry_broker = ttk.Entry(cfg_grid, textvariable=self.cfg_broker_var, width=18, font=("Segoe UI", 9))
        self.entry_broker.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="Port:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=1, column=2, sticky=tk.E, padx=(0, 4), pady=2)
        self.cfg_port_var = tk.StringVar(value=str(profile.mqtt_port if profile else 1883))
        self.entry_port = ttk.Entry(cfg_grid, textvariable=self.cfg_port_var, width=6, font=("Segoe UI", 9))
        self.entry_port.grid(row=1, column=3, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="User:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=1, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_user_var = tk.StringVar(value=(profile.mqtt_user if profile else ""))
        self.entry_user = ttk.Entry(cfg_grid, textvariable=self.cfg_user_var, width=10, font=("Segoe UI", 9))
        self.entry_user.grid(row=1, column=5, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="Pass:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=1, column=6, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_mqtt_pass_var = tk.StringVar(value=(profile.mqtt_pass if profile else ""))
        self.entry_mqtt_pass = ttk.Entry(cfg_grid, textvariable=self.cfg_mqtt_pass_var, width=10, font=("Segoe UI", 9), show="*")
        self.entry_mqtt_pass.grid(row=1, column=7, sticky=tk.W, pady=2)

        # Dòng 2: Phiên bản vận hành (Điểm Nguồn/Đích bỏ — đội WCS/IT tự điều phối theo ID+Version)
        tk.Label(cfg_grid, text="Phiên bản:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_ver_var = tk.StringVar(value=(profile.operating_version if profile else "2.0"))
        self.combo_ver = ttk.Combobox(cfg_grid, textvariable=self.cfg_ver_var, values=["No version", "1.0", "2.0"], width=10, state="readonly", font=("Segoe UI", 9))
        self.combo_ver.grid(row=2, column=1, sticky=tk.W, padx=(0, 10), pady=2)

        # Ghi chú chế độ phiên bản (chỉ đọc)
        self.lbl_ver_note = tk.Label(
            cfg_grid,
            text="",
            font=("Segoe UI", 8),
            fg=COLORS.muted,
            bg=card_bg,
        )
        self.lbl_ver_note.grid(row=2, column=2, columnspan=4, sticky=tk.W, pady=2)

        self.combo_ver.bind("<<ComboboxSelected>>", self._on_version_changed)
        self._on_version_changed()

    def _build_action_card(self, tab_usb: tk.Frame) -> None:
        bg_canvas = COLORS.canvas
        card_bg = COLORS.white
        border_color = COLORS.border
        # ==================== CARD 4: TIẾN TRÌNH & THAO TÁC NẠP ====================
        card_action = tk.Frame(
            tab_usb,
            bg=card_bg,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        card_action.pack(fill=tk.X, pady=4)
        self.device_action_card = card_action

        tk.Label(
            card_action,
            text="4. TIẾN TRÌNH & THAO TÁC NẠP",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        ).pack(anchor=tk.W)

        self.phase_label = tk.Label(
            card_action,
            text=STATE_COPY[ProvisionState.READY],
            font=("Segoe UI", 11, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        )
        self.phase_label.pack(anchor=tk.W, pady=(4, 2))

        self.progress_bar = ttk.Progressbar(
            card_action,
            orient=tk.HORIZONTAL,
            length=100,
            mode="determinate",
            style="Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill=tk.X, pady=(2, 4))

        self.banner_label = tk.Label(
            card_action,
            text="",
            font=("Segoe UI", 11, "bold"),
            fg=COLORS.success,
            bg=card_bg,
            wraplength=800,
            justify=tk.LEFT,
        )
        self.banner_label.pack(anchor=tk.W)

        self.result_details_label = tk.Label(
            card_action,
            text="",
            font=("Segoe UI", 9),
            fg=COLORS.text_secondary,
            bg=card_bg,
            wraplength=800,
            justify=tk.LEFT,
        )
        self.result_details_label.pack(anchor=tk.W, pady=(1, 4))

        self.action_hint_label = tk.Label(
            card_action,
            text="Vui lòng kết nối cổng COM để thao tác.",
            font=("Segoe UI", 9),
            fg=COLORS.muted,
            bg=card_bg,
        )
        self.action_hint_label.pack(anchor=tk.W, pady=(2, 6))

        self.btn_flash_factory = ttk.Button(
            card_action,
            text="NẠP CALLBOX • NẠP XƯỞNG\nBootloader + Partition + OTA data + Application + NVS",
            style="Primary.TButton",
            command=self._on_flash_full_click,
        )
        self.btn_flash_factory.pack(fill=tk.X, ipady=8, pady=(2, 6))
        self.btn_advanced_flash_toggle = ttk.Button(
            card_action, text="CHI TIẾT BẢO TRÌ  ▾", style="Secondary.TButton",
            command=self._toggle_advanced_flash_actions,
        )
        self.btn_advanced_flash_toggle.pack(anchor=tk.W, pady=(0, 3))

        buttons_row = tk.Frame(card_action, bg=card_bg)
        self.advanced_flash_frame = buttons_row

        self.btn_flash_config = ttk.Button(
            buttons_row,
            text="NẠP CẤU HÌNH\n(Chỉ nạp NVS 0x214000, ~2s)",
            style="ConfigOnly.TButton",
            command=self._on_flash_config_click,
        )
        self.btn_flash_config.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3), ipady=6)

        self.btn_flash_bundle = ttk.Button(
            buttons_row,
            text="CẬP NHẬT FIRMWARE\n(Boot + Partition + OTA + App | Giữ NVS)",
            style="Primary.TButton",
            command=self._on_flash_bundle_click,
        )
        self.btn_flash_bundle.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3, ipady=6)

        self.btn_flash_app = ttk.Button(
            buttons_row,
            text="CẬP NHẬT APP\n(Chỉ nạp Code 0x10000, Giữ NVS)",
            style="AppOnly.TButton",
            command=self._on_flash_app_click,
        )
        self.btn_flash_app.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3, ipady=6)

        self.btn_flash_baseline = ttk.Button(
            buttons_row,
            text="NẠP BOOTLOADER / SETUP\n(Cơ sở 3 phân vùng, không app)",
            style="Baseline.TButton",
            command=self._on_flash_baseline_click,
        )
        self.btn_flash_baseline.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0), ipady=6)

    def _toggle_advanced_flash_actions(self) -> None:
        visible = not bool(getattr(self, "_device_maintenance_visible", False))
        self._set_device_maintenance_visible(visible)

    def _set_device_maintenance_visible(self, visible: bool) -> None:
        self._device_maintenance_visible = visible
        frame = getattr(self, "advanced_flash_frame", None)
        details = [
            getattr(self, "device_firmware_card", None),
            getattr(self, "device_config_card", None),
            getattr(self, "device_log_card", None),
        ]
        if visible:
            if frame is not None and not frame.winfo_ismapped():
                frame.pack(fill=tk.X, pady=(2, 4))
            for detail in details:
                if detail is not None and not detail.winfo_ismapped():
                    detail.pack(fill=tk.X, pady=4)
            self.btn_advanced_flash_toggle.config(text="CHI TIẾT BẢO TRÌ  ▴")
        else:
            if frame is not None:
                frame.pack_forget()
            for detail in details:
                if detail is not None:
                    detail.pack_forget()
            self.btn_advanced_flash_toggle.config(text="CHI TIẾT BẢO TRÌ  ▾")

    def _build_log_card(self, tab_usb: tk.Frame) -> None:
        bg_canvas = COLORS.canvas
        card_bg = COLORS.white
        border_color = COLORS.border
        # ==================== CARD 4: NHẬT KÝ KỸ THUẬT (CONSOLE) ====================
        log_card = tk.Frame(
            tab_usb,
            bg=bg_canvas,
            bd=0,
            pady=4,
        )
        log_card.pack(fill=tk.BOTH, expand=True)
        self.device_log_card = log_card

        log_header = tk.Frame(log_card, bg=bg_canvas)
        log_header.pack(fill=tk.X, pady=(2, 4))

        tk.Label(
            log_header,
            text="NHẬT KÝ KỸ THUẬT (LOG CONSOLE)",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.muted_dark,
            bg=bg_canvas,
        ).pack(side=tk.LEFT)

        self.btn_clear_log = ttk.Button(
            log_header,
            text="Xóa nhật ký",
            command=self._clear_log,
            style="Secondary.TButton",
        )
        self.btn_clear_log.pack(side=tk.RIGHT)

        log_container = tk.Frame(
            log_card,
            bg=COLORS.text,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            bd=0,
        )
        log_container.pack(fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(log_container)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(
            log_container,
            height=6,
            font=("Consolas", 9),
            bg=COLORS.text,
            fg=COLORS.border,
            insertbackground=COLORS.white,
            relief="flat",
            padx=8,
            pady=6,
            yscrollcommand=log_scroll.set,
            wrap=tk.WORD,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

    def _clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)
    def _append_log(self, text: str) -> None:
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
    def _refresh_ports(self) -> None:
        selected_before = self.port_combo.get()
        self.ports = discover_ports()
        device_names = [p.device for p in self.ports]
        self.port_combo["values"] = device_names

        auto = automatic_port(self.ports)
        if selected_before in device_names:
            self.port_combo.set(selected_before)
        elif auto:
            self.port_combo.set(auto)
        elif device_names:
            self.port_combo.set(device_names[0])
        else:
            self.port_combo.set("")

        if hasattr(self, "worker_port_combo"):
            self._worker_sync_ports()

        self._on_port_selected(None)
    def _on_port_selected(self, event=None) -> None:
        device = self.port_combo.get()
        match = next((p for p in self.ports if p.device == device), None)
        if match:
            vid_pid = f" (VID:PID = {hex(match.vid or 0)}:{hex(match.pid or 0)})" if match.vid else ""
            self.port_desc_label.config(
                text=f"{match.description}{vid_pid}",
                fg=COLORS.info,
            )
        else:
            self.port_desc_label.config(
                text="Chưa chọn hoặc không tìm thấy cổng COM phù hợp",
                fg=COLORS.danger_text,
            )
        self._update_flash_button()
        self._worker_update_button_state()
    def _auto_detect_firmware(self) -> None:
        """Tự động tìm và nạp firmware ứng dụng mặc định để xưởng có thể nạp ngay lập tức."""
        exe_dir = pathlib.Path(sys.executable).parent if getattr(sys, "frozen", False) else pathlib.Path.cwd()
        candidates = [
            # 1. Nhúng trong assets của ứng dụng (khi đóng gói EXE độc lập)
            resource_path("assets") / "callbox_sews.bin",
            # 2. Cùng thư mục với file EXE
            exe_dir / "callbox_sews.bin",
            exe_dir / "callbox-aubot.bin",
            # 3. Thư mục con firmware/ bên cạnh EXE
            exe_dir / "firmware" / "callbox_sews.bin",
            # 4. Thư mục build trong repository phát triển
            pathlib.Path(__file__).resolve().parents[3] / "build" / "callbox_sews.bin",
        ]

        for p in candidates:
            if p.is_file():
                try:
                    info = validate_application(p)
                    self.app_info = info
                    self.fw_path_var.set(str(p))
                    self.fw_meta_label.config(
                        text=(
                            f"Dự án: {info.project} | Version: {info.version} | "
                            f"Kích thước: {info.size:,} bytes | SHA-256: {info.sha256[:16]}... (Sẵn sàng xuất xưởng)"
                        ),
                        fg=COLORS.success,
                    )
                    self._append_log(f"Đã tự động tải firmware xuất xưởng: {p.name} ({info.version})")
                    self._update_flash_button()
                    return
                except Exception:
                    continue
    def _on_browse(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Chọn file application .bin",
            filetypes=[("ESP Firmware (.bin)", "*.bin"), ("All files", "*.*")],
        )
        if not chosen:
            return

        target_path = pathlib.Path(chosen)
        self.fw_path_var.set(str(target_path))
        try:
            info = validate_application(target_path)
            self.app_info = info
            self.fw_meta_label.config(
                text=(
                    f"Dự án: {info.project} | Version: {info.version} | "
                    f"Kích thước: {info.size:,} bytes | SHA-256: {info.sha256[:16]}..."
                ),
                fg=COLORS.success,
            )
        except ImageValidationError as error:
            self.app_info = None
            self.fw_meta_label.config(
                text=f"LỖI: {error}",
                fg=COLORS.danger,
            )
        except Exception as error:
            self.app_info = None
            self.fw_meta_label.config(
                text=f"Lỗi không xác định: {error}",
                fg=COLORS.danger,
            )
        self._update_flash_button()
    def _update_flash_button(self) -> None:
        port = self.port_combo.get().strip()
        valid = self.app_info is not None
        busy = self.controller.busy

        config_ready = can_flash_config(port, busy)
        baseline_ready = can_flash_baseline(port, busy)
        app_ready = can_flash(port, valid, busy)
        bundle_ready = can_flash_bundle(port, self.bundle_info is not None, busy)

        self.btn_flash_factory["state"] = tk.NORMAL if bundle_ready else tk.DISABLED
        self.btn_flash_config["state"] = tk.NORMAL if config_ready else tk.DISABLED
        self.btn_flash_baseline["state"] = tk.NORMAL if baseline_ready else tk.DISABLED
        self.btn_flash_app["state"] = tk.NORMAL if app_ready else tk.DISABLED
        self.btn_flash_bundle["state"] = tk.NORMAL if bundle_ready else tk.DISABLED

        # Update dynamic guidance hint
        if busy:
            self.action_hint_label.config(
                text="⏳ Đang thực hiện tiến trình nạp, vui lòng không ngắt kết nối...",
                fg="#ea580c",
            )
        elif not port:
            self.action_hint_label.config(
                text="⚠️ Vui lòng kết nối cáp USB và chọn cổng COM của board ESP32-S3.",
                fg="#b45309",
            )
        elif not valid:
            self.action_hint_label.config(
                text="Cổng COM đã sẵn sàng. NẠP CALLBOX sẽ dùng gói firmware đã xác minh đi kèm Tool.",
                fg="#7c3aed",
            )
        else:
            self.action_hint_label.config(
                text="NẠP CALLBOX là luồng nạp xưởng đầy đủ; Công cụ bảo trì chỉ dùng khi sửa chữa/cập nhật.",
                fg=COLORS.success,
            )
    def _set_inputs_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.port_combo["state"] = "readonly" if enabled else tk.DISABLED
        self.btn_refresh["state"] = state
        self.btn_check_status["state"] = state
        self.btn_read_config["state"] = state
        self.btn_browse["state"] = state
        self.btn_reset_defaults["state"] = state

        # Form entries
        self.entry_id["state"] = state
        self.entry_ssid["state"] = state
        self.entry_pass["state"] = state
        self.chk_dhcp["state"] = state
        self.entry_broker["state"] = state
        self.entry_port["state"] = state
        self.entry_user["state"] = state
        self.entry_mqtt_pass["state"] = state
        self.combo_ver["state"] = "readonly" if enabled else tk.DISABLED
        self._update_flash_button()
    def _on_version_changed(self, *_) -> None:
        """Cập nhật ghi chú chế độ vận hành theo Operating Version đã chọn."""
        ver = self.cfg_ver_var.get().strip()
        if hasattr(self, "lbl_ver_note"):
            if ver == "1.0":
                self.lbl_ver_note.config(text="Chế độ: 1 nút", fg="#7c3aed")
            else:
                self.lbl_ver_note.config(text="Chế độ: 2 nút", fg=COLORS.info)
    def _get_device_config_from_ui(self) -> DeviceConfig:
        """Thu thập đối tượng DeviceConfig từ các trường nhập liệu trên giao diện.

        Điểm Nguồn/Đích không còn được cấu hình tại đây — đội IT/WCS tự điều phối
        dựa theo Operating Version + Callbox ID. listpoints luôn để rỗng.
        """
        ver = self.cfg_ver_var.get().strip() or "No version"
        # list_pub luôn OFF — WCS tự điều phối, không publish danh sách điểm
        return DeviceConfig(
            callbox_id=self.cfg_id_var.get().strip() or "001",
            wifi_ssid=self.cfg_ssid_var.get().strip(),
            wifi_pass=self.cfg_pass_var.get().strip(),
            wifi_dhcp=bool(self.cfg_dhcp_var.get()),
            mqtt_broker=self.cfg_broker_var.get().strip(),
            mqtt_port=int(self.cfg_port_var.get().strip() or "1883"),
            mqtt_user=self.cfg_user_var.get().strip(),
            mqtt_pass=self.cfg_mqtt_pass_var.get().strip(),
            operating_version=ver,
            listpoints_source="",
            listpoints_dest="",
            listpoint_publish_enabled=False,
        )
    def _increment_callbox_id(self) -> None:
        """Tăng nhanh số thứ tự Callbox ID phục vụ nạp hàng loạt trong dây chuyền sản xuất."""
        curr = self.cfg_id_var.get().strip()
        match = re.search(r"(\d+)$", curr)
        if match:
            digits = match.group(1)
            prefix = curr[:match.start(1)]
            width = len(digits)
            next_num = int(digits) + 1
            new_id = f"{prefix}{next_num:0{width}d}"
            self.cfg_id_var.set(new_id)
        else:
            self.cfg_id_var.set(curr + "1")
        self._append_log(f"Đã tăng nhanh Callbox ID: {self.cfg_id_var.get()}")
    def _on_reset_defaults_click(self) -> None:
        """Khôi phục form kỹ thuật về cấu hình xưởng mặc định đã lưu trên máy."""
        profile = getattr(self, "factory_profile", None)
        if profile is None:
            messagebox.showwarning(
                "Chưa có cấu hình mặc định",
                "Máy này chưa có cấu hình xưởng mặc định. Vào Hệ thống → Cấu hình xưởng để lưu một lần.",
                parent=self.root,
            )
            return
        self._apply_factory_profile_to_form(profile)
        self._append_log("Đã khôi phục form về cấu hình xưởng mặc định đã lưu.")

    def _apply_factory_profile_to_form(self, profile: DeviceConfig) -> None:
        """Apply a saved factory profile to editable UI fields without changing the Callbox workflow."""
        self.cfg_ssid_var.set(profile.wifi_ssid)
        self.cfg_pass_var.set(profile.wifi_pass)
        self.cfg_dhcp_var.set(profile.wifi_dhcp)
        self.cfg_broker_var.set(profile.mqtt_broker)
        self.cfg_port_var.set(str(profile.mqtt_port))
        self.cfg_user_var.set(profile.mqtt_user)
        self.cfg_mqtt_pass_var.set(profile.mqtt_pass)
        self.cfg_ver_var.set(profile.operating_version)
        self._on_version_changed()
