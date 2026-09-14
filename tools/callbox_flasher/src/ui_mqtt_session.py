import tkinter as tk
from tkinter import messagebox

from tools.callbox_flasher.src.mqtt_remote_config import (
    CallboxRemoteConfigClient, MqttBrokerConfig, PAHO_AVAILABLE,
)
from tools.callbox_flasher.src.ui_theme import COLORS


class MqttSessionMixin:
    def _clear_mqtt_log(self) -> None:
        self.rc_log_text.delete("1.0", tk.END)
    def _mqtt_log_append(self, text: str) -> None:
        self.rc_log_text.insert(tk.END, text + "\n")
        self.rc_log_text.see(tk.END)
    def _on_mqtt_connect_click(self) -> None:
        if not PAHO_AVAILABLE:
            messagebox.showerror(
                "Thiếu thư viện",
                "Chưa cài đặt thư viện paho-mqtt!\nHãy chạy lệnh:\npip install paho-mqtt>=1.6.1",
                parent=self.root,
            )
            return

        broker = self.rc_broker_var.get().strip()
        if not broker:
            messagebox.showwarning("Lỗi nhập liệu", "Vui lòng nhập địa chỉ MQTT Broker!", parent=self.root)
            return

        try:
            port = int(self.rc_port_var.get().strip() or "1883")
        except ValueError:
            messagebox.showwarning("Lỗi nhập liệu", "Cổng MQTT phải là số!", parent=self.root)
            return

        cfg = MqttBrokerConfig(
            host=broker,
            port=port,
            username=self.rc_user_var.get().strip(),
            password=self.rc_pass_var.get().strip(),
        )

        self.lbl_rc_broker_status.config(text="● Đang kết nối...", fg=COLORS.warning)
        self._mqtt_log_append(f"--- Đang kết nối đến broker {cfg.host}:{cfg.port} ---")

        if not self.mqtt_client:
            self.mqtt_client = CallboxRemoteConfigClient()
            self.mqtt_client.on_connect = lambda ok, msg: self.root.after(0, self._on_mqtt_connect_result, ok, msg)
            self.mqtt_client.on_ack = lambda cid, ok: self.root.after(0, self._on_mqtt_ack_result, cid, ok)
            self.mqtt_client.on_button_ack = lambda cid, button, request_id, status, reason: self.root.after(0, self._on_mqtt_button_ack_result, cid, button, request_id, status, reason)
            self.mqtt_client.on_io_state = lambda cid, state: self.root.after(0, self._dispatch_mqtt_io_state, cid, state)
            self.mqtt_client.on_status_state = lambda cid, state: self.root.after(0, self._on_mqtt_status_state, cid, state)
            self.mqtt_client.on_internet_state = lambda cid, state: self.root.after(0, self._on_mqtt_internet_state, cid, state)
            self.mqtt_client.on_health_state = lambda cid, state: self.root.after(0, self._on_mqtt_health_state, cid, state)
            self.mqtt_client.on_diagnostic_state = lambda cid, state: self.root.after(0, self._on_mqtt_diagnostic_state, cid, state)
            self.mqtt_client.on_info_state = lambda cid, state: self.root.after(0, self._on_mqtt_info_state, cid, state)
            self.mqtt_client.on_network_state = lambda cid, state: self.root.after(0, self._on_mqtt_network_state, cid, state)
            self.mqtt_client.on_trace_event = lambda cid, event: self.root.after(0, self._on_mqtt_trace_event, cid, event)
            self.mqtt_client.on_log = lambda m: self.root.after(0, self._mqtt_log_append, m)

        self.mqtt_client.connect(cfg)
    def _on_mqtt_connect_result(self, ok: bool, msg: str) -> None:
        self.mqtt_is_connected = ok
        if ok:
            self.lbl_rc_broker_status.config(text=f"● Đã kết nối: {self.rc_broker_var.get().strip()}", fg=COLORS.success)
            self.btn_rc_connect.config(state=tk.DISABLED)
            self.btn_rc_disconnect.config(state=tk.NORMAL)
            if hasattr(self, "btn_mgmt_connect"):
                self.btn_mgmt_connect.config(state=tk.DISABLED)
                self.btn_mgmt_disconnect.config(state=tk.NORMAL)
            self._mqtt_log_append("KẾT NỐI THÀNH CÔNG: Sẵn sàng gửi cấu hình đến các Callbox online.")
            self._subscribe_remote_io_state()
            self._management_resubscribe()
            if getattr(self, "mgmt_fleet_enabled", False) and self.mqtt_client:
                self.mqtt_client.subscribe_fleet_status(True)
        else:
            self.lbl_rc_broker_status.config(text=f"● Lỗi kết nối ({msg})", fg=COLORS.danger)
            self.btn_rc_connect.config(state=tk.NORMAL)
            self.btn_rc_disconnect.config(state=tk.DISABLED)
            if hasattr(self, "btn_mgmt_connect"):
                self.btn_mgmt_connect.config(state=tk.NORMAL)
                self.btn_mgmt_disconnect.config(state=tk.DISABLED)
        self._update_remote_button_state()
    def _on_mqtt_disconnect_click(self) -> None:
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        self.mqtt_is_connected = False
        self.lbl_rc_broker_status.config(text="● Đã ngắt kết nối", fg=COLORS.muted)
        self.btn_rc_connect.config(state=tk.NORMAL)
        self.btn_rc_disconnect.config(state=tk.DISABLED)
        if hasattr(self, "btn_mgmt_connect"):
            self.btn_mgmt_connect.config(state=tk.NORMAL)
            self.btn_mgmt_disconnect.config(state=tk.DISABLED)
        self._mqtt_log_append("Đã ngắt kết nối khỏi MQTT Broker.")
        self._reset_remote_io_display()
        if hasattr(self, "mgmt_mqtt_badge"):
            self.mgmt_mqtt_badge.config(text="MQTT: OFFLINE", fg=COLORS.danger)
            self.mgmt_online_badge.config(text="UNKNOWN", bg=COLORS.border, fg=COLORS.muted)
            self._reset_management_diagnostic()

        self._update_remote_button_state()

    def _dispatch_mqtt_io_state(self, callbox_id: str, state: dict) -> None:
        for panel_name, handler in (
            ("management", self._on_management_io_state),
            ("remote", self._on_mqtt_io_state),
        ):
            try:
                handler(callbox_id, state)
            except Exception as error:
                self._mqtt_log_append(f"I/O {panel_name} panel error: {error}")
