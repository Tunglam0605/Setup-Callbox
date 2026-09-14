import time
import tkinter as tk
from tkinter import ttk

from tools.callbox_flasher.src.ui_management_logic import format_bytes, reset_reason_text, usage_percent
from tools.callbox_flasher.src.ui_theme import COLORS


class ManagementResourcesUiMixin:
    """Resource/health presentation kept separate from fleet/state management."""

    def _management_clear_live_snapshot(self) -> None:
        for variable in getattr(self, "mgmt_vars", {}).values():
            variable.set("--")
        for label in getattr(self, "mgmt_io_indicators", {}).values():
            title = label.cget("text").split("\n", 1)[0]
            label.config(text=f"{title}\n--", bg=COLORS.surface_alt, fg=COLORS.muted)
        self._mgmt_io_count = 0
        self._mgmt_io_rate = 0.0
        if hasattr(self, "mgmt_io_rate_label"):
            self.mgmt_io_rate_label.config(text="I/O rate: -- Hz")
        for progress_name, label_name in (
            ("mgmt_ram_progress", "mgmt_ram_pct_label"),
            ("mgmt_flash_progress", "mgmt_flash_pct_label"),
        ):
            progress = getattr(self, progress_name, None)
            if progress is not None:
                progress["value"] = 0
            label = getattr(self, label_name, None)
            if label is not None:
                label.config(text="--%")
        self._reset_management_diagnostic()
        self._mgmt_snapshot_visible = False

    def _build_management_resource_cards(self, right, card_bg: str, border_color: str, bg_canvas: str) -> None:
        middle = tk.Frame(right, bg=bg_canvas)
        middle.pack(fill=tk.X, pady=4)
        network = self._management_card(middle, "MẠNG", card_bg, border_color, side=tk.LEFT)
        resources = self._management_card(middle, "TÀI NGUYÊN", card_bg, border_color, side=tk.LEFT)
        for index, (label, key) in enumerate((("Wi-Fi", "wifi"), ("IP", "ip"), ("Ethernet", "eth"),
                                              ("MQTT transport", "mqtt_transport"), ("WCS plane", "wcs_plane"),
                                              ("MQTT reconnect", "mqtt_reconnect"))):
            self._management_value(network, index + 1, 0, label, key, card_bg, value_col=1)

        tk.Label(resources, text="RAM", font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).grid(row=1, column=0, sticky="w", padx=(3, 8))
        self.mgmt_ram_progress = ttk.Progressbar(resources, orient=tk.HORIZONTAL, mode="determinate", maximum=100)
        self.mgmt_ram_progress.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        self.mgmt_ram_pct_label = tk.Label(resources, text="--%", width=6, font=("Segoe UI", 10, "bold"), bg=card_bg, fg=COLORS.text)
        self.mgmt_ram_pct_label.grid(row=1, column=2, sticky="e")
        tk.Label(resources, textvariable=self.mgmt_vars["ram_used"], font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).grid(row=2, column=0, columnspan=3, sticky="w", padx=3, pady=(1, 6))

        tk.Label(resources, text="FLASH APP", font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).grid(row=3, column=0, sticky="w", padx=(3, 8))
        self.mgmt_flash_progress = ttk.Progressbar(resources, orient=tk.HORIZONTAL, mode="determinate", maximum=100)
        self.mgmt_flash_progress.grid(row=3, column=1, sticky="ew", padx=(0, 8))
        self.mgmt_flash_pct_label = tk.Label(resources, text="--%", width=6, font=("Segoe UI", 10, "bold"), bg=card_bg, fg=COLORS.text)
        self.mgmt_flash_pct_label.grid(row=3, column=2, sticky="e")
        tk.Label(resources, textvariable=self.mgmt_vars["flash_used"], font=("Segoe UI", 9, "bold"), bg=card_bg, fg=COLORS.text).grid(row=4, column=0, columnspan=3, sticky="w", padx=3, pady=(1, 0))
        resources.grid_columnconfigure(1, weight=1)

        system_health = self._management_card(right, "HỆ THỐNG & MQTT", card_bg, border_color)
        fields = (("RAM free", "ram_free"), ("RAM min", "ram_min_free"), ("Reset", "reset_reason"),
                  ("Recovery", "recovery"), ("MQTT drop", "mqtt_drop"), ("Cmd drop", "cmd_drop"))
        for index, (label, key) in enumerate(fields):
            self._management_value(system_health, 1 + index // 3, (index % 3) * 2, label, key, card_bg)

    def _update_management_resource_health(self, state: dict) -> tuple[int, dict]:
        mqtt = state.get("mqtt", {})
        memory = state.get("memory", {})
        flash = state.get("flash", {})
        drop_total = int(mqtt.get("queue_drop", 0)) + int(mqtt.get("stale_drop", 0)) + int(mqtt.get("inflight_drop", 0))

        ram_total = int(memory.get("total", 0) or 0)
        ram_used = int(memory.get("used", 0) or 0)
        ram_free = int(memory.get("free", state.get("free_heap", 0)) or 0)
        ram_min = int(memory.get("min_free", state.get("min_free_heap", 0)) or 0)
        ram_pct = usage_percent(ram_used, ram_total)
        self.mgmt_vars["free_heap"].set(format_bytes(ram_free))
        self.mgmt_vars["min_heap"].set(format_bytes(ram_min))
        self.mgmt_vars["largest_block"].set(format_bytes(memory.get("largest_block", state.get("largest_block", 0))))
        self.mgmt_vars["ram_total"].set(format_bytes(ram_total))
        self.mgmt_vars["ram_free"].set(format_bytes(ram_free))
        self.mgmt_vars["ram_min_free"].set(format_bytes(ram_min))
        self.mgmt_vars["ram_usage"].set(f"{ram_pct:.0f}%")
        self.mgmt_vars["ram_used"].set(
            f"{format_bytes(ram_used)} / {format_bytes(ram_total)}"
            if ram_total else f"Free {format_bytes(ram_free)} • firmware cũ chưa báo tổng RAM"
        )
        self.mgmt_ram_progress["value"] = ram_pct
        self.mgmt_ram_pct_label.config(text=f"{ram_pct:.0f}%" if ram_total else "--%")

        flash_total = int(flash.get("app_partition", 0) or 0)
        flash_used = int(flash.get("app_image", 0) or 0)
        flash_free = int(flash.get("app_free", 0) or 0)
        flash_pct = usage_percent(flash_used, flash_total)
        self.mgmt_vars["flash_total"].set(format_bytes(flash_total))
        self.mgmt_vars["flash_free"].set(format_bytes(flash_free))
        self.mgmt_vars["flash_usage"].set(f"{flash_pct:.0f}%")
        self.mgmt_vars["flash_used"].set(
            f"{format_bytes(flash_used)} / {format_bytes(flash_total)}"
            if flash_total else "Cần firmware health mới để đọc dung lượng Flash"
        )
        self.mgmt_flash_progress["value"] = flash_pct
        self.mgmt_flash_pct_label.config(text=f"{flash_pct:.0f}%" if flash_total else "--%")

        self.mgmt_vars["reset_reason"].set(reset_reason_text(state.get("reset_reason", 0)))
        self.mgmt_vars["recovery"].set("ON" if state.get("recovery") else "OFF")
        self.mgmt_vars["mqtt_drop"].set(str(drop_total))
        self.mgmt_vars["mqtt_busy"].set(str(mqtt.get("client_busy", 0)))
        self.mgmt_vars["mqtt_outbox"].set(str(mqtt.get("outbox_fail", 0)))
        self.mgmt_vars["cmd_drop"].set(str(mqtt.get("cmd_drop", 0)))
        self.mgmt_vars["task_checkins"].set("/".join(str(v) for v in state.get("task_checkins", ())))
        return drop_total, mqtt

    def _on_mqtt_info_state(self, callbox_id: str, state: dict) -> None:
        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        record.update(info=state, info_rx=now, management_supported=True)
        record["fw"] = state.get("fw") or record.get("fw", "")
        if callbox_id == self.mgmt_target_id_var.get().strip():
            self._mgmt_last_info_rx = now
            self.mgmt_vars["fw"].set(state.get("fw") or "-")
            self.mgmt_vars["version"].set(state.get("operating_version") or "-")

    def _on_mqtt_network_state(self, callbox_id: str, state: dict) -> None:
        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        record.update(network=state, network_rx=now, management_supported=True)
        record["comm"] = state.get("comm") or record.get("comm", "")
        wifi_state = state.get("wifi") or {}
        mqtt_state = state.get("mqtt") or {}
        record["rssi"] = wifi_state.get("rssi", record.get("rssi", 0))
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return
        self._mgmt_last_network_rx = now
        wifi = "CONNECTED" if wifi_state.get("connected") else "DISCONNECTED"
        if wifi_state.get("ssid"):
            wifi += f" ({wifi_state.get('ssid')})"
        ethernet = state.get("ethernet") or {}
        self.mgmt_vars["wifi"].set(wifi)
        self.mgmt_vars["ip"].set(wifi_state.get("ip") or "-")
        self.mgmt_vars["eth"].set(("CONNECTED " + (ethernet.get("ip") or "")) if ethernet.get("connected") else "OFF")
        self.mgmt_vars["rssi"].set(f"{wifi_state.get('rssi', 0)} dBm")
        self.mgmt_vars["mqtt_transport"].set("CONNECTED" if mqtt_state.get("transport_connected") else "OFFLINE")
        self.mgmt_vars["wcs_plane"].set("READY" if mqtt_state.get("wcs_plane_ready") else "NOT READY")
        self.mgmt_vars["mqtt_reconnect"].set(str(mqtt_state.get("reconnect_count", 0)))
