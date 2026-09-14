import tkinter as tk
from tkinter import messagebox, ttk

from tools.callbox_flasher.src.mqtt_remote_config import (
    RemoteConfigPayload,
    io_state_topic,
    remote_button_topics,
    service_config_topics,
)
from tools.callbox_flasher.src.ui_state import can_monitor_io, can_remote_control
from tools.callbox_flasher.src.ui_theme import COLORS


class RemoteMqttUiMixin:
    def _setup_mqtt_tab(self, parent: tk.Frame, card_bg: str, border_color: str, bg_canvas: str) -> None:
        """Xây dựng giao diện cho tab Cấu hình từ xa qua MQTT."""
        # ==================== CARD M1: KẾT NỐI BROKER MQTT ====================
        card_broker = tk.Frame(
            parent,
            bg=card_bg,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        card_broker.pack(fill=tk.X, pady=4)

        header_b = tk.Frame(card_broker, bg=card_bg)
        header_b.pack(fill=tk.X)
        tk.Label(
            header_b,
            text="1. KẾT NỐI BROKER MQTT (WCS / FLEET SERVER)",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        ).pack(side=tk.LEFT)

        self.lbl_rc_broker_status = tk.Label(
            header_b,
            text="● Chưa kết nối",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.muted,
            bg=card_bg,
        )
        self.lbl_rc_broker_status.pack(side=tk.RIGHT)

        b_grid = tk.Frame(card_broker, bg=card_bg)
        b_grid.pack(fill=tk.X, pady=(6, 2))

        # Row 0: Broker Host, Port, User, Pass
        tk.Label(b_grid, text="Broker:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_broker_var = tk.StringVar(value=(self.factory_profile.mqtt_broker if getattr(self, "factory_profile", None) else ""))
        self.entry_rc_broker = ttk.Entry(b_grid, textvariable=self.rc_broker_var, width=18, font=("Segoe UI", 9))
        self.entry_rc_broker.grid(row=0, column=1, sticky=tk.W, padx=(0, 8), pady=2)

        tk.Label(b_grid, text="Cổng:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_port_var = tk.StringVar(value=str(self.factory_profile.mqtt_port if getattr(self, "factory_profile", None) else 1883))
        self.entry_rc_port = ttk.Entry(b_grid, textvariable=self.rc_port_var, width=6, font=("Segoe UI", 9))
        self.entry_rc_port.grid(row=0, column=3, sticky=tk.W, padx=(0, 8), pady=2)

        tk.Label(b_grid, text="Tài khoản:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_user_var = tk.StringVar(value=(self.factory_profile.mqtt_user if getattr(self, "factory_profile", None) else ""))
        self.entry_rc_user = ttk.Entry(b_grid, textvariable=self.rc_user_var, width=10, font=("Segoe UI", 9))
        self.entry_rc_user.grid(row=0, column=5, sticky=tk.W, padx=(0, 8), pady=2)

        tk.Label(b_grid, text="Mật khẩu:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=6, sticky=tk.W, padx=(0, 4), pady=2)
        # Reuse the factory MQTT credential already configured in the USB/production tab.
        # This avoids an accidental blank-password connect/reconnect loop.
        default_mqtt_password = self.cfg_mqtt_pass_var.get() if hasattr(self, "cfg_mqtt_pass_var") else ""
        self.rc_pass_var = tk.StringVar(value=default_mqtt_password)
        self.entry_rc_pass = ttk.Entry(b_grid, textvariable=self.rc_pass_var, width=10, font=("Segoe UI", 9), show="*")
        self.entry_rc_pass.grid(row=0, column=7, sticky=tk.W, padx=(0, 10), pady=2)

        self.btn_rc_connect = ttk.Button(
            b_grid,
            text="Kết nối Broker",
            style="Secondary.TButton",
            command=self._on_mqtt_connect_click,
        )
        self.btn_rc_connect.grid(row=0, column=8, sticky=tk.W, padx=(0, 4), pady=2)

        self.btn_rc_disconnect = ttk.Button(
            b_grid,
            text="Ngắt kết nối",
            style="Secondary.TButton",
            command=self._on_mqtt_disconnect_click,
            state=tk.DISABLED,
        )
        self.btn_rc_disconnect.grid(row=0, column=9, sticky=tk.W, pady=2)

        # ==================== CARD M2: THAM SỐ CẤU HÌNH TỪ XA ====================
        card_params = tk.Frame(
            parent,
            bg=card_bg,
            highlightbackground=border_color,
            highlightthickness=1,
            bd=0,
            padx=12,
            pady=8,
        )
        card_params.pack(fill=tk.X, pady=4)
        self.remote_config_card = card_params

        header_p = tk.Frame(card_params, bg=card_bg)
        header_p.pack(fill=tk.X)
        tk.Label(
            header_p,
            text="2. THIẾT LẬP THAM SỐ GỬI ĐẾN CALLBOX (PARTIAL UPDATE)",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.text,
            bg=card_bg,
        ).pack(side=tk.LEFT)

        tk.Label(
            header_p,
            text="Chỉ gửi các trường có nhập giá trị · Trường để trống sẽ giữ nguyên trên chip",
            font=("Segoe UI", 8),
            fg=COLORS.muted,
            bg=card_bg,
        ).pack(side=tk.RIGHT)

        p_grid = tk.Frame(card_params, bg=card_bg)
        p_grid.pack(fill=tk.X, pady=(6, 2))

        # Row 0: Target Callbox ID & Version
        tk.Label(p_grid, text="Callbox ID mục tiêu (*):", font=("Segoe UI", 9, "bold"), fg=COLORS.danger_text, bg=card_bg).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_target_id_var = tk.StringVar(value="001")
        self.entry_rc_target_id = ttk.Entry(p_grid, textvariable=self.rc_target_id_var, width=12, font=("Segoe UI", 9, "bold"))
        self.entry_rc_target_id.grid(row=0, column=1, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Phiên bản vận hành:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_ver_var = tk.StringVar(value="(Giữ nguyên)")
        self.combo_rc_ver = ttk.Combobox(p_grid, textvariable=self.rc_ver_var, values=["(Giữ nguyên)", "2.0", "1.0", "No version"], width=13, state="readonly", font=("Segoe UI", 9))
        self.combo_rc_ver.grid(row=0, column=3, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Đổi Callbox ID mới:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_new_id_var = tk.StringVar(value="")
        self.entry_rc_new_id = ttk.Entry(p_grid, textvariable=self.rc_new_id_var, width=12, font=("Segoe UI", 9))
        self.entry_rc_new_id.grid(row=0, column=5, sticky=tk.W, padx=(0, 4), pady=3)

        # Row 1: New WiFi SSID & Pass
        tk.Label(p_grid, text="Wi-Fi SSID mới:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_wifi_ssid_var = tk.StringVar(value="")
        self.entry_rc_wifi_ssid = ttk.Entry(p_grid, textvariable=self.rc_wifi_ssid_var, width=16, font=("Segoe UI", 9))
        self.entry_rc_wifi_ssid.grid(row=1, column=1, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Mật khẩu Wi-Fi mới:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=1, column=2, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_wifi_pass_var = tk.StringVar(value="")
        self.entry_rc_wifi_pass = ttk.Entry(p_grid, textvariable=self.rc_wifi_pass_var, width=16, font=("Segoe UI", 9), show="*")
        self.entry_rc_wifi_pass.grid(row=1, column=3, sticky=tk.W, padx=(0, 14), pady=3)

        self.rc_reboot_var = tk.BooleanVar(value=True)
        self.chk_rc_reboot = tk.Checkbutton(
            p_grid,
            text="Khởi động lại sau khi lưu (Reboot)",
            variable=self.rc_reboot_var,
            font=("Segoe UI", 9),
            fg=COLORS.info,
            bg=card_bg,
            activebackground=card_bg,
        )
        self.chk_rc_reboot.grid(row=1, column=4, columnspan=2, sticky=tk.W, pady=3)

        # Row 2: New MQTT Broker & Port
        tk.Label(p_grid, text="MQTT Broker mới:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_new_broker_var = tk.StringVar(value="")
        self.entry_rc_new_broker = ttk.Entry(p_grid, textvariable=self.rc_new_broker_var, width=16, font=("Segoe UI", 9))
        self.entry_rc_new_broker.grid(row=2, column=1, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Cổng MQTT mới:", font=("Segoe UI", 9), fg=COLORS.text_secondary, bg=card_bg).grid(row=2, column=2, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_new_port_var = tk.StringVar(value="")
        self.entry_rc_new_port = ttk.Entry(p_grid, textvariable=self.rc_new_port_var, width=8, font=("Segoe UI", 9))
        self.entry_rc_new_port.grid(row=2, column=3, sticky=tk.W, padx=(0, 14), pady=3)

        # Action send button row
        action_row = tk.Frame(card_params, bg=card_bg)
        action_row.pack(fill=tk.X, pady=(8, 2))

        config_topic_template, _ = service_config_topics("<ID>")
        self.btn_rc_send = ttk.Button(
            action_row,
            text=f"🚀 GỬI CẤU HÌNH QUA MQTT ({config_topic_template})",
            style="ConfigOnly.TButton",
            command=self._on_mqtt_send_config_click,
        )
        self.btn_rc_send.pack(side=tk.LEFT, ipady=6, ipadx=14)

        self.lbl_rc_ack_status = tk.Label(
            action_row,
            text="Trạng thái lệnh: Sẵn sàng gửi",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.muted,
            bg=card_bg,
        )
        self.lbl_rc_ack_status.pack(side=tk.LEFT, padx=(14, 0))

        # ==================== CARD M3: ĐIỀU KHIỂN CALLBOX TỪ XA ====================
        card_remote = tk.Frame(parent, bg=card_bg, highlightbackground=border_color, highlightthickness=1, bd=0, padx=12, pady=8)
        card_remote.pack(fill=tk.X, pady=4)
        self.remote_control_card = card_remote
        remote_header = tk.Frame(card_remote, bg=card_bg)
        remote_header.pack(fill=tk.X)
        tk.Label(remote_header, text="3. ĐIỀU KHIỂN CALLBOX TỪ XA", font=("Segoe UI", 9, "bold"), fg=COLORS.text, bg=card_bg).pack(side=tk.LEFT)
        self.btn_remote_advanced = ttk.Button(remote_header, text="CẤU HÌNH NÂNG CAO  ▾", style="Secondary.TButton", command=self._toggle_remote_advanced)
        self.btn_remote_advanced.pack(side=tk.RIGHT)
        tk.Label(remote_header, text="Nút vật lý luôn được ưu tiên", font=("Segoe UI", 8), fg=COLORS.muted, bg=card_bg).pack(side=tk.RIGHT, padx=(0, 8))
        remote_row = tk.Frame(card_remote, bg=card_bg)
        remote_row.pack(fill=tk.X, pady=(7, 2))
        self.lbl_remote_target = tk.Label(remote_row, text="Target điều khiển: --", font=("Segoe UI", 9, "bold"), fg=COLORS.text_secondary, bg=card_bg)
        self.lbl_remote_target.pack(side=tk.LEFT, padx=(0, 12))
        self.btn_remote_call1 = ttk.Button(remote_row, text="CALL 1", style="Primary.TButton", command=lambda: self._on_mqtt_remote_button_click(1), state=tk.DISABLED)
        self.btn_remote_call1.pack(side=tk.LEFT, ipadx=12, ipady=4, padx=(0, 6))
        self.btn_remote_call2 = ttk.Button(remote_row, text="CALL 2", style="AppOnly.TButton", command=lambda: self._on_mqtt_remote_button_click(2), state=tk.DISABLED)
        self.btn_remote_call2.pack(side=tk.LEFT, ipadx=12, ipady=4, padx=(0, 6))
        self.btn_remote_cancel = ttk.Button(remote_row, text="CANCEL", style="Danger.TButton", command=lambda: self._on_mqtt_remote_button_click(3), state=tk.DISABLED)
        self.btn_remote_cancel.pack(side=tk.LEFT, ipadx=12, ipady=4)
        self.lbl_remote_button_status = tk.Label(card_remote, text="Chưa sẵn sàng: MQTT chưa kết nối.", font=("Segoe UI", 9, "bold"), fg=COLORS.muted, bg=card_bg, anchor="w")
        self.lbl_remote_button_status.pack(fill=tk.X, pady=(6, 0))

        monitor = tk.Frame(card_remote, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1, padx=8, pady=7)
        monitor.pack(fill=tk.X, pady=(8, 0))
        self.remote_io_monitor = monitor
        monitor_header = tk.Frame(monitor, bg=COLORS.surface_alt)
        monitor_header.pack(fill=tk.X)
        tk.Label(monitor_header, text="TRẠNG THÁI THỰC TẾ TỪ CALLBOX", font=("Segoe UI", 8, "bold"), fg=COLORS.muted_dark, bg=COLORS.surface_alt).pack(side=tk.LEFT)
        monitor_target = tk.Frame(monitor_header, bg=COLORS.surface_alt)
        monitor_target.pack(side=tk.RIGHT)
        tk.Label(monitor_target, text="ID theo dõi I/O:", font=("Segoe UI", 8, "bold"), fg=COLORS.text_secondary, bg=COLORS.surface_alt).pack(side=tk.LEFT, padx=(0, 4))
        self.rc_monitor_id_var = tk.StringVar(value=self.rc_target_id_var.get().strip() or "001")
        self.entry_rc_monitor_id = ttk.Entry(monitor_target, textvariable=self.rc_monitor_id_var, width=10, font=("Segoe UI", 9, "bold"))
        self.entry_rc_monitor_id.pack(side=tk.LEFT, padx=(0, 5))
        self.btn_monitor_io = ttk.Button(monitor_target, text="THEO DÕI", command=self._subscribe_remote_io_state)
        self.btn_monitor_io.pack(side=tk.LEFT)

        io_row1 = tk.Frame(monitor, bg=COLORS.surface_alt)
        io_row1.pack(fill=tk.X, pady=(5, 3))
        self.lbl_io_btn1 = tk.Label(io_row1, text="BTN 1: --", width=14, font=("Segoe UI", 9, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=6, pady=4)
        self.lbl_io_btn2 = tk.Label(io_row1, text="BTN 2: --", width=14, font=("Segoe UI", 9, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=6, pady=4)
        self.lbl_io_btn3 = tk.Label(io_row1, text="CANCEL: --", width=14, font=("Segoe UI", 9, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=6, pady=4)
        self.lbl_io_btn1.pack(side=tk.LEFT, padx=(0, 5))
        self.lbl_io_btn2.pack(side=tk.LEFT, padx=(0, 5))
        self.lbl_io_btn3.pack(side=tk.LEFT, padx=(0, 12))

        self.lbl_io_led1 = tk.Label(io_row1, text="LED 1: --", width=11, font=("Segoe UI", 8, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=4, pady=4)
        self.lbl_io_led2 = tk.Label(io_row1, text="LED 2: --", width=11, font=("Segoe UI", 8, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=4, pady=4)
        self.lbl_io_led3 = tk.Label(io_row1, text="LED 3: --", width=11, font=("Segoe UI", 8, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=4, pady=4)
        self.lbl_io_led1.pack(side=tk.LEFT, padx=(0, 4))
        self.lbl_io_led2.pack(side=tk.LEFT, padx=(0, 4))
        self.lbl_io_led3.pack(side=tk.LEFT)

        io_row2 = tk.Frame(monitor, bg=COLORS.surface_alt)
        io_row2.pack(fill=tk.X, pady=(2, 0))
        tk.Label(io_row2, text="Đèn tháp:", font=("Segoe UI", 8, "bold"), fg=COLORS.muted_dark, bg=COLORS.surface_alt).pack(side=tk.LEFT, padx=(0, 5))
        self.lbl_io_tower_red = tk.Label(io_row2, text="ĐỎ: --", width=9, font=("Segoe UI", 8, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=4, pady=3)
        self.lbl_io_tower_yellow = tk.Label(io_row2, text="VÀNG: --", width=9, font=("Segoe UI", 8, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=4, pady=3)
        self.lbl_io_tower_green = tk.Label(io_row2, text="XANH: --", width=9, font=("Segoe UI", 8, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=4, pady=3)
        self.lbl_io_tower_red.pack(side=tk.LEFT, padx=(0, 4))
        self.lbl_io_tower_yellow.pack(side=tk.LEFT, padx=(0, 4))
        self.lbl_io_tower_green.pack(side=tk.LEFT, padx=(0, 10))
        self.lbl_io_summary = tk.Label(io_row2, text="Chưa nhận dữ liệu I/O", font=("Segoe UI", 8), fg=COLORS.muted, bg=COLORS.surface_alt, anchor="w")
        self.lbl_io_summary.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._io_subscribe_after_id = None
        self.rc_target_id_var.trace_add("write", lambda *_: self._on_remote_target_changed())
        self.rc_monitor_id_var.trace_add("write", lambda *_: self._on_monitor_target_changed())
        self._reset_remote_io_display()
        self._update_remote_button_state()

        # ==================== CARD M4: NHẬT KÝ MQTT CONSOLE ====================
        card_log = tk.Frame(parent, bg=bg_canvas, bd=0, pady=4)
        card_log.pack(fill=tk.BOTH, expand=True)
        self.remote_log_card = card_log

        m_log_header = tk.Frame(card_log, bg=bg_canvas)
        m_log_header.pack(fill=tk.X, pady=(2, 4))

        tk.Label(
            m_log_header,
            text="NHẬT KÝ BẢN TIN MQTT & PHẢN HỒI ACK TỪ CALLBOX",
            font=("Segoe UI", 9, "bold"),
            fg=COLORS.muted_dark,
            bg=bg_canvas,
        ).pack(side=tk.LEFT)

        btn_clear_m_log = ttk.Button(
            m_log_header,
            text="Xóa nhật ký MQTT",
            command=self._clear_mqtt_log,
            style="Secondary.TButton",
        )
        btn_clear_m_log.pack(side=tk.RIGHT)

        m_log_container = tk.Frame(
            card_log,
            bg=COLORS.text,
            highlightbackground="#cbd5e1",
            highlightthickness=1,
            bd=0,
        )
        m_log_container.pack(fill=tk.BOTH, expand=True)

        m_log_scroll = ttk.Scrollbar(m_log_container)
        m_log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.rc_log_text = tk.Text(
            m_log_container,
            height=8,
            font=("Consolas", 9),
            bg=COLORS.text,
            fg=COLORS.border,
            insertbackground=COLORS.white,
            relief="flat",
            padx=8,
            pady=6,
            yscrollcommand=m_log_scroll.set,
            wrap=tk.WORD,
        )
        self.rc_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        m_log_scroll.config(command=self.rc_log_text.yview)
        self._set_remote_advanced_visible(False)
    def _set_remote_advanced_visible(self, visible: bool) -> None:
        self._remote_advanced_visible = visible
        for widget in (getattr(self, "remote_config_card", None), getattr(self, "remote_log_card", None)):
            if widget is None:
                continue
            if visible:
                if not widget.winfo_ismapped():
                    widget.pack(fill=tk.X if widget is getattr(self, "remote_config_card", None) else tk.BOTH, expand=widget is getattr(self, "remote_log_card", None), pady=4)
            else:
                widget.pack_forget()
        monitor = getattr(self, "remote_io_monitor", None)
        if monitor is not None:
            monitor.pack_forget()
        if hasattr(self, "btn_remote_advanced"):
            self.btn_remote_advanced.config(text="CẤU HÌNH NÂNG CAO  ▴" if visible else "CẤU HÌNH NÂNG CAO  ▾")

    def _toggle_remote_advanced(self) -> None:
        self._set_remote_advanced_visible(not bool(getattr(self, "_remote_advanced_visible", False)))

    def _on_remote_target_changed(self) -> None:
        # ID mục tiêu chỉ phục vụ cấu hình/điều khiển. Monitor I/O dùng ID riêng.
        self._update_remote_button_state()
    def _on_monitor_target_changed(self) -> None:
        self._reset_remote_io_display()
        if self._io_subscribe_after_id is not None:
            try:
                self.root.after_cancel(self._io_subscribe_after_id)
            except Exception:
                pass
        self._io_subscribe_after_id = self.root.after(300, self._subscribe_remote_io_state)
    def _subscribe_remote_io_state(self) -> None:
        self._io_subscribe_after_id = None
        monitor_id = self.rc_monitor_id_var.get().strip() if hasattr(self, "rc_monitor_id_var") else ""
        if not monitor_id:
            self.lbl_io_summary.config(text="Nhập ID theo dõi I/O", fg=COLORS.warning)
            return
        if not can_monitor_io(self.mqtt_is_connected, monitor_id) or not self.mqtt_client:
            self.lbl_io_summary.config(text=f"Chưa kết nối MQTT - chờ theo dõi Callbox {monitor_id}", fg=COLORS.muted)
            return
        monitor_topic = io_state_topic(monitor_id)
        if not self.mqtt_client.subscribe_io_state(monitor_id):
            self.lbl_io_summary.config(text=f"Không subscribe được {monitor_topic}", fg=COLORS.danger)
            return
        self.lbl_io_summary.config(text=f"Đang theo dõi {monitor_topic} - chờ dữ liệu...", fg=COLORS.info)
    def _reset_remote_io_display(self) -> None:
        if not hasattr(self, "lbl_io_btn1"):
            return
        for label, text in (
            (self.lbl_io_btn1, "BTN 1: --"),
            (self.lbl_io_btn2, "BTN 2: --"),
            (self.lbl_io_btn3, "CANCEL: --"),
            (self.lbl_io_led1, "LED 1: --"),
            (self.lbl_io_led2, "LED 2: --"),
            (self.lbl_io_led3, "LED 3: --"),
            (self.lbl_io_tower_red, "ĐỎ: --"),
            (self.lbl_io_tower_yellow, "VÀNG: --"),
            (self.lbl_io_tower_green, "XANH: --"),
        ):
            label.config(text=text, bg=COLORS.border, fg=COLORS.muted)
        self.lbl_io_summary.config(text="Chưa nhận dữ liệu I/O", fg=COLORS.muted)
    def _set_io_indicator(label: tk.Label, prefix: str, active: bool, active_bg: str, active_fg: str = COLORS.white) -> None:
        if active:
            label.config(text=f"{prefix}: ON", bg=active_bg, fg=active_fg)
        else:
            label.config(text=f"{prefix}: OFF", bg=COLORS.border, fg=COLORS.muted)
    def _on_mqtt_io_state(self, callbox_id: str, state: dict) -> None:
        monitor_id = self.rc_monitor_id_var.get().strip() if hasattr(self, "rc_monitor_id_var") else ""
        if callbox_id != monitor_id:
            return
        buttons = state["buttons"]
        button_leds = state["button_leds"]
        tower = state["tower"]

        for label, prefix, pressed in (
            (self.lbl_io_btn1, "BTN 1", buttons[0]),
            (self.lbl_io_btn2, "BTN 2", buttons[1]),
            (self.lbl_io_btn3, "CANCEL", buttons[2]),
        ):
            if pressed:
                label.config(text=f"{prefix}: NHẤN", bg=COLORS.success, fg=COLORS.white)
            else:
                label.config(text=f"{prefix}: THẢ", bg=COLORS.border, fg=COLORS.muted_dark)

        self._set_io_indicator(self.lbl_io_led1, "LED 1", button_leds[0], COLORS.success)
        self._set_io_indicator(self.lbl_io_led2, "LED 2", button_leds[1], "#0284c7")
        self._set_io_indicator(self.lbl_io_led3, "LED 3", button_leds[2], COLORS.danger)
        self._set_io_indicator(self.lbl_io_tower_red, "ĐỎ", tower[0], COLORS.danger)
        self._set_io_indicator(self.lbl_io_tower_yellow, "VÀNG", tower[1], "#eab308", "#422006")
        self._set_io_indicator(self.lbl_io_tower_green, "XANH", tower[2], COLORS.success)

        self.lbl_io_summary.config(
            text=(f"ID {callbox_id} | Comm: {state['comm'] or '-'} | Task1: {state['task1'] or '-'} | "
                  f"Task2: {state['task2'] or '-'} | Warning: {state['warning'] or '-'} | FW: {state['fw'] or '-'}"),
            fg=COLORS.text if state.get("online") else COLORS.danger,
        )
    def _update_remote_button_state(self) -> None:
        if not hasattr(self, "btn_remote_call1"):
            return
        target_id = self.rc_target_id_var.get().strip() if hasattr(self, "rc_target_id_var") else ""
        connected = bool(
            self.mqtt_is_connected
            and self.mqtt_client
            and self.mqtt_client.connected
        )
        enabled = can_remote_control(connected, target_id)
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (self.btn_remote_call1, self.btn_remote_call2, self.btn_remote_cancel):
            button.config(state=state)

        if hasattr(self, "lbl_remote_target"):
            self.lbl_remote_target.config(
                text=f"Target điều khiển: {target_id or '--'}",
                fg=COLORS.text if target_id else COLORS.muted,
            )
        if not hasattr(self, "lbl_remote_button_status"):
            return
        if not connected:
            self.lbl_remote_button_status.config(
                text="Chưa sẵn sàng: MQTT chưa kết nối.",
                fg=COLORS.muted,
            )
        elif not target_id:
            self.lbl_remote_button_status.config(
                text="Chưa sẵn sàng: nhập Callbox ID mục tiêu ở mục 2.",
                fg=COLORS.warning,
            )
        else:
            control_topic, _ = remote_button_topics(target_id)
            self.lbl_remote_button_status.config(
                text=f"Sẵn sàng điều khiển Callbox {target_id}  →  {control_topic}",
                fg=COLORS.success,
            )
    def _on_mqtt_remote_button_click(self, button: int) -> None:
        target_id = self.rc_target_id_var.get().strip()
        if not can_remote_control(self.mqtt_is_connected, target_id) or not self.mqtt_client:
            self.lbl_remote_button_status.config(text="Không thể gửi: MQTT chưa kết nối hoặc Target Callbox ID đang trống.", fg=COLORS.danger)
            self._update_remote_button_state()
            return
        if button == 3:
            if not messagebox.askyesno("Xác nhận CANCEL từ xa", f"Gửi một lần nhấn CANCEL tới Callbox {target_id}?", icon="warning", parent=self.root):
                return
        # ID theo dõi I/O độc lập với ID điều khiển; không đổi subscription tại đây.
        ok, request_id = self.mqtt_client.send_remote_button(target_id, button)
        button_name = {1: "CALL 1", 2: "CALL 2", 3: "CANCEL"}.get(button, str(button))
        if ok:
            self.lbl_remote_button_status.config(text=f"Đã gửi {button_name} tới {target_id} | request_id={request_id} | chờ ACK...", fg=COLORS.warning)
        else:
            self.lbl_remote_button_status.config(text=f"Publish {button_name} thất bại | request_id={request_id or '-'}", fg=COLORS.danger)
    def _on_mqtt_button_ack_result(self, callbox_id: str, button: int, request_id: int, status: str, reason: str) -> None:
        button_name = {1: "CALL 1", 2: "CALL 2", 3: "CANCEL"}.get(button, f"BUTTON {button}")
        reason_text = reason or "no_reason"
        self.lbl_remote_button_status.config(text=f"ACK {button_name} từ {callbox_id} | request_id={request_id} | status={status} | reason={reason_text}", fg=COLORS.success if status == "ok" else COLORS.danger)
        self._mqtt_log_append(f"Remote button ACK: Callbox={callbox_id} button={button} request_id={request_id} status={status} reason={reason_text}")
    def _on_mqtt_send_config_click(self) -> None:
        if not self.mqtt_is_connected or not self.mqtt_client:
            messagebox.showwarning(
                "Chưa kết nối",
                "Vui lòng bấm 'Kết nối Broker' trước khi gửi lệnh cấu hình từ xa!",
                parent=self.root,
            )
            return

        target_id = self.rc_target_id_var.get().strip()
        if not target_id:
            messagebox.showwarning("Lỗi nhập liệu", "Vui lòng nhập Callbox ID mục tiêu!", parent=self.root)
            return

        ver_choice = self.rc_ver_var.get().strip()
        op_ver = "" if ver_choice == "(Giữ nguyên)" else ver_choice

        port_val = 0
        p_str = self.rc_new_port_var.get().strip()
        if p_str:
            try:
                port_val = int(p_str)
            except ValueError:
                messagebox.showwarning("Lỗi nhập liệu", "Cổng MQTT mới phải là số nguyên!", parent=self.root)
                return

        payload = RemoteConfigPayload(
            callbox_id=self.rc_new_id_var.get().strip(),
            operating_version=op_ver,
            wifi_ssid=self.rc_wifi_ssid_var.get().strip(),
            wifi_pass=self.rc_wifi_pass_var.get().strip(),
            mqtt_broker=self.rc_new_broker_var.get().strip(),
            mqtt_port=port_val,
            reboot=self.rc_reboot_var.get(),
        )

        config_topic, _ = service_config_topics(target_id)
        confirm = messagebox.askyesno(
            "Xác nhận gửi cấu hình từ xa",
            f"Gửi lệnh remote_config đến Callbox ID: {target_id} qua MQTT?\n\n"
            f"• Topic: {config_topic}\n"
            f"• Phiên bản: {op_ver or '(Giữ nguyên)'}\n"
            f"• Đổi ID mới: {payload.callbox_id or '(Không đổi)'}\n"
            f"• Wi-Fi mới: {payload.wifi_ssid or '(Không đổi)'}\n"
            f"• Khởi động lại chip: {'CÓ' if payload.reboot else 'KHÔNG'}\n\n"
            "Callbox đang online sẽ lưu cấu hình vào NVS và phản hồi ACK.",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self.lbl_rc_ack_status.config(text=f"Đang gửi đến Callbox {target_id} và chờ ACK...", fg=COLORS.warning)
        ok = self.mqtt_client.send_remote_config(target_id, payload)
        if not ok:
            self.lbl_rc_ack_status.config(text="Lỗi publish MQTT!", fg=COLORS.danger)
    def _on_mqtt_ack_result(self, callbox_id: str, ok: bool) -> None:
        if ok:
            msg = f"✅ THÀNH CÔNG: Callbox {callbox_id} đã nhận và lưu cấu hình vào NVS!"
            self.lbl_rc_ack_status.config(text=msg, fg=COLORS.success)
            self._mqtt_log_append(f"★ {msg}")
        else:
            msg = f"❌ THẤT BẠI: Callbox {callbox_id} báo lỗi khi lưu cấu hình!"
            self.lbl_rc_ack_status.config(text=msg, fg=COLORS.danger)
            self._mqtt_log_append(f"★ {msg}")
