import time
import tkinter as tk
from tkinter import ttk

from tools.callbox_flasher.src.ui_theme import COLORS
from tools.callbox_flasher.src.ui_management_logic import (
    age_text, alarm_state, device_is_online, format_uptime, health_level, telemetry_state,
)

class ManagementUiMixin:
    """Remote fleet dashboard focused on fast diagnosis instead of raw MQTT payloads."""

    def _setup_management_tab(self, parent: tk.Frame, card_bg: str, border_color: str, bg_canvas: str) -> None:
        self._fleet_devices: dict[str, dict] = {}
        self._mgmt_last_status_rx = 0.0
        self._mgmt_last_io_rx = 0.0
        self._mgmt_last_internet_rx = 0.0
        self._mgmt_last_health_rx = 0.0
        self._mgmt_last_diagnostic_rx = 0.0
        self._mgmt_last_info_rx = 0.0
        self._mgmt_last_network_rx = 0.0
        self._mgmt_last_trace_rx = 0.0
        self._mgmt_subscribe_after_id = None
        self._mgmt_event_values: dict[str, object] = {}
        self._mgmt_io_count = 0
        self._mgmt_io_rate = 0.0
        self._mgmt_snapshot_visible = False
        self._mgmt_io_window_start = time.monotonic()
        self.mgmt_fleet_enabled = True

        header = tk.Frame(parent, bg=card_bg, highlightbackground=border_color, highlightthickness=1, padx=12, pady=8)
        header.pack(fill=tk.X, pady=(4, 3))
        tk.Label(header, text="QUẢN LÝ & CHẨN ĐOÁN CALLBOX", font=("Segoe UI", 11, "bold"), fg=COLORS.text, bg=card_bg).pack(side=tk.LEFT)
        self.mgmt_mqtt_badge = tk.Label(header, text="MQTT: CHƯA KẾT NỐI", font=("Segoe UI", 9, "bold"), fg=COLORS.muted, bg=card_bg)
        self.mgmt_mqtt_badge.pack(side=tk.RIGHT, padx=(8, 0))
        self.btn_mgmt_disconnect = ttk.Button(header, text="NGẮT", style="Secondary.TButton", command=self._on_mqtt_disconnect_click, state=tk.DISABLED)
        self.btn_mgmt_disconnect.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_mgmt_connect = ttk.Button(header, text="KẾT NỐI MQTT", style="Primary.TButton", command=self._on_mqtt_connect_click)
        self.btn_mgmt_connect.pack(side=tk.RIGHT, padx=(10, 0))

        toolbar = tk.Frame(parent, bg=card_bg, highlightbackground=border_color, highlightthickness=1, padx=10, pady=7)
        toolbar.pack(fill=tk.X, pady=3)
        tk.Label(toolbar, text="Callbox ID", font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text_secondary).pack(side=tk.LEFT)
        default_id = self.rc_target_id_var.get().strip() if hasattr(self, "rc_target_id_var") else "001"
        self.mgmt_target_id_var = self.rc_target_id_var if hasattr(self, "rc_target_id_var") else tk.StringVar(value=default_id or "001")
        ttk.Entry(toolbar, textvariable=self.mgmt_target_id_var, width=11, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(toolbar, text="COPY", style="Secondary.TButton", command=self._management_copy_snapshot).pack(side=tk.LEFT)
        self.btn_mgmt_log_toggle = ttk.Button(toolbar, text="NHẬT KÝ  ▾", style="Secondary.TButton", command=self._management_toggle_log)
        self.btn_mgmt_log_toggle.pack(side=tk.LEFT, padx=(6, 0))
        self.btn_mgmt_reset_task = ttk.Button(toolbar, text="🔄 RESET TASK VỀ IDLE", style="Secondary.TButton", command=self._management_reset_target_task)
        self.btn_mgmt_reset_task.pack(side=tk.LEFT, padx=(8, 0))
        self.mgmt_health_badge = tk.Label(toolbar, text="HEALTH: --", font=("Segoe UI", 9, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=10, pady=4)
        self.mgmt_health_badge.pack(side=tk.RIGHT, padx=(6, 0))
        self.mgmt_online_badge = tk.Label(toolbar, text="UNKNOWN", font=("Segoe UI", 9, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=10, pady=4)
        self.mgmt_online_badge.pack(side=tk.RIGHT)

        self.mgmt_alarm_label = tk.Label(parent, text="Chưa có dữ liệu chẩn đoán", anchor="w", font=("Segoe UI", 9, "bold"), bg=COLORS.border, fg=COLORS.muted, padx=10, pady=6)
        self.mgmt_alarm_label.pack(fill=tk.X, pady=3)

        body = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg=bg_canvas, sashwidth=6, bd=0, relief=tk.FLAT)
        body.pack(fill=tk.X, pady=3)
        left = tk.Frame(body, bg=card_bg, highlightbackground=border_color, highlightthickness=1, padx=8, pady=8)
        right = tk.Frame(body, bg=bg_canvas)
        body.add(left, minsize=390, width=470)
        body.add(right, minsize=700)
        self._mgmt_body = body
        self._mgmt_left_pane = left
        self._mgmt_right_pane = right

        fleet_head = tk.Frame(left, bg=card_bg)
        fleet_head.pack(fill=tk.X, pady=(0, 5))
        tk.Label(fleet_head, text="THIẾT BỊ PHÁT HIỆN", font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).pack(side=tk.LEFT)
        self.btn_mgmt_fleet = ttk.Button(fleet_head, text="TẮT FLEET", style="Secondary.TButton", command=self._management_toggle_fleet)
        self.btn_mgmt_fleet.pack(side=tk.RIGHT)
        columns = ("id", "state", "health", "comm", "rssi", "fw", "seen")
        self.mgmt_fleet_tree = ttk.Treeview(left, columns=columns, show="headings", height=20)
        specs = {"id": ("ID", 62), "state": ("State", 62), "health": ("Health", 68), "comm": ("Comm", 72), "rssi": ("RSSI", 55), "fw": ("FW", 58), "seen": ("Seen", 55)}
        for col in columns:
            title, width = specs[col]
            self.mgmt_fleet_tree.heading(col, text=title)
            self.mgmt_fleet_tree.column(col, width=width, anchor=tk.CENTER, stretch=False)
        self.mgmt_fleet_tree.tag_configure("ok", background="#f0fdf4")
        self.mgmt_fleet_tree.tag_configure("warn", background="#fffbeb")
        self.mgmt_fleet_tree.tag_configure("offline", background="#fef2f2")
        self.mgmt_fleet_tree.pack(fill=tk.BOTH, expand=True)
        self.mgmt_fleet_tree.bind("<<TreeviewSelect>>", self._management_select_fleet_device)

        summary = tk.Frame(right, bg=bg_canvas)
        summary.pack(fill=tk.X, pady=(0, 4))
        self.mgmt_vars = {name: tk.StringVar(value="--") for name in (
            "comm", "version", "fw", "task1", "task2", "rssi", "uptime", "time_sync", "warning",
            "call1_pending", "call2_pending", "cancel_pending", "cancel_target", "wifi", "ip", "eth", "ap",
            "free_heap", "min_heap", "largest_block", "reset_reason", "recovery", "mqtt_drop", "mqtt_busy",
            "mqtt_outbox", "cmd_drop", "task_checkins", "io_rate",
            "ram_usage", "ram_used", "ram_total", "ram_free", "ram_min_free",
            "flash_usage", "flash_used", "flash_total", "flash_free",
            "mqtt_transport", "wcs_plane", "mqtt_reconnect", "telemetry_health",
        )}
        self.mgmt_metric_labels: dict[str, tk.Label] = {}
        for index, (title, key) in enumerate((("COMM", "comm"), ("FIRMWARE", "fw"), ("TASK 1", "task1"), ("TASK 2", "task2"))):
            tile = tk.Frame(summary, bg=card_bg, highlightbackground=border_color, highlightthickness=1, padx=10, pady=7)
            tile.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 3, 0))
            summary.grid_columnconfigure(index, weight=1)
            tk.Label(tile, text=title, font=("Segoe UI", 8, "bold"), bg=card_bg, fg=COLORS.muted).pack(anchor="w")
            label = tk.Label(tile, textvariable=self.mgmt_vars[key], font=("Segoe UI", 13, "bold"), bg=card_bg, fg=COLORS.text)
            label.pack(anchor="w", pady=(2, 0))
            self.mgmt_metric_labels[key] = label

        mission = self._management_card(right, "NHIỆM VỤ & TRẠNG THÁI", card_bg, border_color)
        mission_fields = (("Operating", "version"), ("RSSI", "rssi"), ("Uptime", "uptime"), ("Warning", "warning"),
                          ("CALL 1", "call1_pending"), ("CALL 2", "call2_pending"), ("Cancel", "cancel_pending"))
        for index, (label, key) in enumerate(mission_fields):
            self._management_value(mission, index // 4 + 1, (index % 4) * 2, label, key, card_bg)

        self._build_management_diagnostic_card(right, card_bg, border_color)

        io_card = self._management_card(right, "I/O REALTIME", card_bg, border_color)
        self.mgmt_io_indicators: dict[str, tk.Label] = {}
        io_items = (("BTN1", "btn1"), ("BTN2", "btn2"), ("CANCEL", "btn3"), ("LED1", "led1"), ("LED2", "led2"), ("LED3", "led3"), ("RED", "red"), ("YELLOW", "yellow"), ("GREEN", "green"))
        for index, (title, key) in enumerate(io_items):
            label = tk.Label(io_card, text=f"{title}\nOFF", width=10, font=("Segoe UI", 8, "bold"), bg=COLORS.surface_alt, fg=COLORS.muted, padx=4, pady=5)
            label.grid(row=1 + index // 5, column=index % 5, padx=3, pady=3, sticky="ew")
            io_card.grid_columnconfigure(index % 5, weight=1)
            self.mgmt_io_indicators[key] = label
        self.mgmt_io_rate_label = tk.Label(io_card, text="I/O rate: -- Hz", font=("Consolas", 9, "bold"), bg=card_bg, fg=COLORS.info)
        self.mgmt_io_rate_label.grid(row=3, column=0, columnspan=5, sticky="w", padx=3, pady=(5, 0))

        self._build_management_resource_cards(right, card_bg, border_color, bg_canvas)

        telemetry = self._management_card(right, "NHẬT KÝ SỰ KIỆN", card_bg, border_color)
        self.mgmt_telemetry_card = telemetry
        self.mgmt_freshness_label = tk.Label(telemetry, text="Status -- | I/O -- | Internet -- | Health -- | Diagnostic --", font=("Segoe UI", 9), bg=card_bg, fg=COLORS.muted)
        self.mgmt_freshness_label.grid(row=1, column=0, sticky="w", pady=(0, 5))
        self.mgmt_event_text = tk.Text(telemetry, height=5, wrap=tk.WORD, font=("Consolas", 8), bg=COLORS.surface_alt, fg=COLORS.text, relief=tk.FLAT)
        self.mgmt_event_text.grid(row=2, column=0, sticky="nsew")
        telemetry.grid_columnconfigure(0, weight=1)
        telemetry.grid_rowconfigure(2, weight=1)
        self.mgmt_event_text.insert(tk.END, "Event log sẽ chỉ ghi thay đổi quan trọng, không spam telemetry.\n")
        self.mgmt_event_text.config(state=tk.DISABLED)
        self._management_set_log_visible(False)
        right.update_idletasks()
        self._management_sync_body_height()

        self.mgmt_target_id_var.trace_add("write", lambda *_: self._management_target_changed())
        self._mgmt_tick_after_id = self.root.after(500, self._management_tick)

    def _management_sync_body_height(self) -> None:
        body = getattr(self, "_mgmt_body", None)
        left = getattr(self, "_mgmt_left_pane", None)
        right = getattr(self, "_mgmt_right_pane", None)
        if body is None or left is None or right is None:
            return
        body.configure(height=max(left.winfo_reqheight(), right.winfo_reqheight()))

    @staticmethod
    def _management_card(parent, title: str, card_bg: str, border_color: str, side=None) -> tk.Frame:
        frame = tk.Frame(parent, bg=card_bg, highlightbackground=border_color, highlightthickness=1, padx=10, pady=7)
        if side is None:
            frame.pack(fill=tk.X, pady=4)
        else:
            frame.pack(side=side, fill=tk.BOTH, expand=True, padx=(0, 4) if side == tk.LEFT else (4, 0))
        tk.Label(frame, text=title, font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).grid(row=0, column=0, columnspan=10, sticky="w", pady=(0, 5))
        return frame

    def _management_value(self, parent, row: int, col: int, label: str, key: str, card_bg: str, value_col=None) -> None:
        value_col = col + 1 if value_col is None else value_col
        tk.Label(parent, text=label + ":", font=("Segoe UI", 8, "bold"), bg=card_bg, fg=COLORS.muted).grid(row=row, column=col, sticky="e", padx=(3, 3), pady=2)
        tk.Label(parent, textvariable=self.mgmt_vars[key], font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).grid(row=row, column=value_col, sticky="w", padx=(0, 8), pady=2)

    def _management_set_log_visible(self, visible: bool) -> None:
        self._mgmt_log_visible = visible
        card = getattr(self, "mgmt_telemetry_card", None)
        if card is not None:
            if visible:
                if not card.winfo_ismapped():
                    card.pack(fill=tk.X, pady=4)
            else:
                card.pack_forget()
        if hasattr(self, "btn_mgmt_log_toggle"):
            self.btn_mgmt_log_toggle.config(text="NHẬT KÝ  ▴" if visible else "NHẬT KÝ  ▾")
        self.root.after_idle(self._management_sync_body_height)

    def _management_toggle_log(self) -> None:
        self._management_set_log_visible(not bool(getattr(self, "_mgmt_log_visible", False)))

    def _management_use_control_id(self) -> None:
        if hasattr(self, "rc_target_id_var"):
            self.mgmt_target_id_var.set(self.rc_target_id_var.get().strip())

    def _management_target_changed(self) -> None:
        self._mgmt_last_status_rx = self._mgmt_last_io_rx = self._mgmt_last_internet_rx = self._mgmt_last_health_rx = self._mgmt_last_diagnostic_rx = 0.0
        self._mgmt_last_info_rx = self._mgmt_last_network_rx = self._mgmt_last_trace_rx = 0.0
        self._mgmt_event_values.clear()
        self._management_clear_live_snapshot()
        self.mgmt_online_badge.config(text="WAITING", bg=COLORS.warning_bg, fg=COLORS.warning_text)
        if self._mgmt_subscribe_after_id is not None:
            try:
                self.root.after_cancel(self._mgmt_subscribe_after_id)
            except Exception:
                pass
        self._mgmt_subscribe_after_id = self.root.after(300, self._management_resubscribe)

    def _management_detail_is_live(self, callbox_id: str, now: float) -> bool:
        return device_is_online(self._fleet_devices.get(callbox_id, {}), now)

    def _management_resubscribe(self) -> None:
        self._mgmt_subscribe_after_id = None
        target = self.mgmt_target_id_var.get().strip() if hasattr(self, "mgmt_target_id_var") else ""
        if not target:
            return
        if not self.mqtt_is_connected or not self.mqtt_client:
            self.mgmt_mqtt_badge.config(text="MQTT: CHƯA KẾT NỐI", fg=COLORS.danger)
            return
        if self.mqtt_client.subscribe_device_state(target):
            self.mgmt_mqtt_badge.config(text=f"MQTT: THEO DÕI {target}", fg=COLORS.success)
            self._management_log_event(f"Bắt đầu theo dõi Callbox {target}")

    def _management_toggle_fleet(self) -> None:
        self.mgmt_fleet_enabled = not self.mgmt_fleet_enabled
        self.btn_mgmt_fleet.config(text="TẮT FLEET" if self.mgmt_fleet_enabled else "BẬT FLEET")
        if self.mqtt_is_connected and self.mqtt_client:
            self.mqtt_client.subscribe_fleet_status(self.mgmt_fleet_enabled)

    def _management_select_fleet_device(self, _event=None) -> None:
        selected = self.mgmt_fleet_tree.selection()
        if selected:
            self.mgmt_target_id_var.set(str(self.mgmt_fleet_tree.item(selected[0], "values")[0]))

    def _management_note_change(self, key: str, value, text: str) -> None:
        previous = self._mgmt_event_values.get(key, object())
        if previous != value:
            self._mgmt_event_values[key] = value
            self._management_log_event(text)

    def _on_mqtt_status_state(self, callbox_id: str, state: dict) -> None:
        now = time.monotonic()
        record = self._fleet_devices.setdefault(callbox_id, {})
        record.update(state)
        record["status_rx"] = now
        self._management_update_fleet_row(callbox_id, record)
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return
        self._mgmt_last_status_rx = now
        if not device_is_online(record, now):
            self._management_clear_live_snapshot()
            return
        self._mgmt_snapshot_visible = True
        for key in ("comm", "version", "fw", "task1", "task2"):
            self.mgmt_vars[key].set(state.get(key) or "-")
        self.mgmt_vars["rssi"].set(f"{state.get('rssi', 0)} dBm")
        self.mgmt_vars["uptime"].set(format_uptime(state.get("uptime", 0)))
        self.mgmt_vars["time_sync"].set("SYNC" if state.get("time_synced") else "NO")
        self._management_note_change("comm", state.get("comm"), f"COMM → {state.get('comm') or '-'}")
        self._management_note_change("task1", state.get("task1"), f"Task 1 → {state.get('task1') or '-'}")
        self._management_note_change("task2", state.get("task2"), f"Task 2 → {state.get('task2') or '-'}")

    def _on_management_io_state(self, callbox_id: str, state: dict) -> None:
        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        record["io"] = state
        record["io_rx"] = now
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return
        self._mgmt_last_io_rx = now
        self._mgmt_io_count += 1
        self.mgmt_vars["warning"].set(state.get("warning") or "none")
        for key in ("call1_pending", "call2_pending", "cancel_pending"):
            self.mgmt_vars[key].set("YES" if state.get(key) else "NO")
        self.mgmt_vars["cancel_target"].set(str(state.get("cancel_target", 0)))
        buttons = state.get("buttons", (False, False, False)); leds = state.get("button_leds", (False, False, False)); tower = state.get("tower", (False, False, False))
        for key, value in zip(("btn1", "btn2", "btn3", "led1", "led2", "led3", "red", "yellow", "green"), (*buttons, *leds, *tower)):
            self._management_set_indicator(key, bool(value))
        self._management_note_change("warning", state.get("warning"), f"Warning → {state.get('warning') or 'none'}")
        self._management_note_change("pending", (state.get("call1_pending"), state.get("call2_pending"), state.get("cancel_pending")), f"Pending CALL1={int(bool(state.get('call1_pending')))} CALL2={int(bool(state.get('call2_pending')))} CANCEL={int(bool(state.get('cancel_pending')))}")

    def _management_set_indicator(self, key: str, active: bool) -> None:
        label = self.mgmt_io_indicators.get(key)
        if not label:
            return
        title = label.cget("text").split("\n", 1)[0]
        if active:
            bg = COLORS.danger if key == "red" else COLORS.warning if key == "yellow" else COLORS.success
            label.config(text=f"{title}\nON", bg=bg, fg=COLORS.white)
        else:
            label.config(text=f"{title}\nOFF", bg=COLORS.surface_alt, fg=COLORS.muted)

    def _on_mqtt_internet_state(self, callbox_id: str, state: dict) -> None:
        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        record["internet"] = state
        record["internet_rx"] = now
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return
        self._mgmt_last_internet_rx = now
        wifi = "CONNECTED" if state.get("sta_connected") else "DISCONNECTED"
        if state.get("sta_ssid"):
            wifi += f" ({state.get('sta_ssid')})"
        self.mgmt_vars["wifi"].set(wifi)
        self.mgmt_vars["ip"].set(state.get("sta_ip") or "-")
        self.mgmt_vars["eth"].set(("CONNECTED " + (state.get("eth_ip") or "")) if state.get("eth_connected") else "OFF")
        self.mgmt_vars["ap"].set((state.get("ap_ssid") or "ON") if state.get("ap_active") else "OFF")
        self._management_note_change("wifi", (state.get("sta_connected"), state.get("sta_ssid")), f"Wi-Fi → {wifi}")

    def _on_mqtt_health_state(self, callbox_id: str, state: dict) -> None:
        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        record["health"] = state
        record["health_rx"] = now
        self._management_update_fleet_row(callbox_id, record)
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return
        self._mgmt_last_health_rx = now
        drop_total, mqtt = self._update_management_resource_health(state)
        self._management_note_change("recovery", state.get("recovery"), f"Recovery → {'ON' if state.get('recovery') else 'OFF'}")
        self._management_note_change("mqtt_error", (drop_total, mqtt.get("outbox_fail", 0), mqtt.get("cmd_drop", 0)), f"MQTT errors drop={drop_total} outbox={mqtt.get('outbox_fail', 0)} cmd={mqtt.get('cmd_drop', 0)}")

    def _management_update_fleet_row(self, callbox_id: str, record: dict) -> None:
        age = time.monotonic() - record.get("status_rx", 0.0) if record.get("status_rx") else 9999.0
        online = device_is_online(record, time.monotonic())
        level = health_level(record) if online else "OFFLINE"
        values = (callbox_id, "ONLINE" if online else "OFF", level, record.get("comm") or "-", record.get("rssi", 0), record.get("fw") or "-", f"{age:.0f}s" if record.get("status_rx") else "--")
        tag = "offline" if not online else "warn" if level in ("WARN", "FAULT") else "ok"
        if self.mgmt_fleet_tree.exists(callbox_id):
            self.mgmt_fleet_tree.item(callbox_id, values=values, tags=(tag,))
        else:
            self.mgmt_fleet_tree.insert("", tk.END, iid=callbox_id, values=values, tags=(tag,))

    def _management_tick(self) -> None:
        if getattr(self, "_closing", False):
            return
        if not hasattr(self, "mgmt_fleet_tree"):
            return
        now = time.monotonic()
        target = self.mgmt_target_id_var.get().strip()
        record = self._fleet_devices.get(target, {})
        if now - self._mgmt_io_window_start >= 1.0:
            elapsed = max(0.001, now - self._mgmt_io_window_start)
            self._mgmt_io_rate = self._mgmt_io_count / elapsed
            self._mgmt_io_count = 0
            self._mgmt_io_window_start = now
            self.mgmt_vars["io_rate"].set(f"{self._mgmt_io_rate:.1f}")
            self.mgmt_io_rate_label.config(text=f"I/O rate: {self._mgmt_io_rate:.1f} Hz")
        if self.mqtt_is_connected:
            self.mgmt_mqtt_badge.config(text=f"MQTT: CONNECTED | {target or '-'}", fg=COLORS.success)
            online = device_is_online(record, now)
            self.mgmt_online_badge.config(text="ONLINE" if online else "OFFLINE", bg=COLORS.success_bg if online else COLORS.danger_bg, fg=COLORS.success_text if online else COLORS.danger_text)
            level, alarms = alarm_state(record, now)
            palette = {"OK": (COLORS.success_bg, COLORS.success_text), "WARN": (COLORS.warning_bg, COLORS.warning_text), "FAULT": (COLORS.danger_bg, COLORS.danger_text), "OFFLINE": (COLORS.danger_bg, COLORS.danger_text)}
            bg, fg = palette.get(level, (COLORS.border, COLORS.muted))
            self.mgmt_health_badge.config(text=f"HEALTH: {level}", bg=bg, fg=fg)
            self.mgmt_alarm_label.config(text=("✓ Không phát hiện bất thường" if not alarms else "⚠ " + "  •  ".join(alarms[:4])), bg=bg, fg=fg)
        else:
            self.mgmt_mqtt_badge.config(text="MQTT: CHƯA KẾT NỐI", fg=COLORS.muted)
            self.mgmt_online_badge.config(text="OFFLINE", bg=COLORS.border, fg=COLORS.muted)
            self.mgmt_health_badge.config(text="HEALTH: --", bg=COLORS.border, fg=COLORS.muted)
            self.mgmt_alarm_label.config(text="● Chưa kết nối MQTT Broker (Nhấn 'KẾT NỐI MQTT' để quản lý)", bg=COLORS.border, fg=COLORS.muted)
            online = False
        if not online and self._mgmt_snapshot_visible:
            self._management_clear_live_snapshot()
        telemetry = telemetry_state(record, now)
        self.mgmt_vars["telemetry_health"].set("  ".join(f"{key.upper()} {value}" for key, value in telemetry.items()))
        support = "Management Diagnostic" if record.get("management_supported") else "Firmware cũ chưa hỗ trợ Management Diagnostic"
        self.mgmt_freshness_label.config(text=f"{support}  |  {self.mgmt_vars['telemetry_health'].get()}  |  Trace {age_text(self._mgmt_last_trace_rx, now)}")
        for key in ("comm", "fw", "task1", "task2"):
            label = self.mgmt_metric_labels.get(key)
            if label:
                value = self.mgmt_vars[key].get().lower()
                color = COLORS.success if (key == "comm" and value == "ready") or (key.startswith("task") and value == "idle") else COLORS.text
                label.config(fg=color)
        for callbox_id, fleet_record in list(self._fleet_devices.items()):
            self._management_update_fleet_row(callbox_id, fleet_record)
        if not getattr(self, "_closing", False):
            self._mgmt_tick_after_id = self.root.after(500, self._management_tick)
