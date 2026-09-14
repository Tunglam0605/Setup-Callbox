from __future__ import annotations

import datetime as _dt
import tkinter as tk

from tools.callbox_flasher.src.ui_theme import COLORS


_CODE_LABELS = {
    "wcs_call_rejected": "CALL bị WCS từ chối",
    "wcs_task_failed": "Nhiệm vụ bị WCS kết thúc lỗi",
    "wcs_cancel_rejected": "CANCEL bị WCS từ chối",
    "wcs_overdue": "WCS báo nhiệm vụ quá hạn",
    "call_ack_timeout": "CALL không nhận ACK đúng hạn",
    "cancel_ack_timeout": "CANCEL không nhận ACK đúng hạn",
    "none": "Không có lỗi",
}

_REASON_LABELS = {
    "locked": "WCS đang khóa nhiệm vụ",
    "duplicate": "WCS phát hiện giao dịch trùng",
    "no_task": "WCS không tìm thấy nhiệm vụ tương ứng",
    "wcs_busy": "WCS đang bận",
    "overdue": "Nhiệm vụ đã quá thời hạn",
    "qos1_sent_no_wcs_ack": "MQTT đã nhận bản tin QoS1 nhưng chưa có ACK từ WCS",
    "mqtt_tx_still_queued": "Bản tin còn nằm trong hàng đợi MQTT khi hết thời gian chờ",
    "mqtt_tx_dropped": "Bản tin MQTT bị loại trước khi hoàn tất gửi",
    "wcs_ack_timeout": "Không nhận phản hồi WCS trước thời hạn",
    "wcs_cancel_ack_timeout": "Không nhận phản hồi CANCEL từ WCS trước thời hạn",
}

_SOURCE_LABELS = {
    "wcs": "WCS",
    "mqtt": "MQTT",
    "network": "NETWORK",
    "io": "I/O",
    "system": "SYSTEM",
}


def diagnostic_event_title(event: dict) -> str:
    return _CODE_LABELS.get(str(event.get("code", "none")), str(event.get("code", "none")))


def diagnostic_reason_text(reason: str) -> str:
    reason = str(reason or "")
    return _REASON_LABELS.get(reason, reason or "Không có mô tả bổ sung")


def diagnostic_event_meta(event: dict) -> str:
    task = int(event.get("task", 0) or 0)
    seq = int(event.get("seq", 0) or 0)
    ts = int(event.get("ts", 0) or 0)
    source = _SOURCE_LABELS.get(str(event.get("source", "system")), str(event.get("source", "system")).upper())
    parts = [f"Nguồn {source}"]
    if task:
        parts.append(f"Task {task}")
    if seq:
        parts.append(f"Seq {seq}")
    if ts:
        try:
            parts.append(_dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S %d/%m/%Y"))
        except Exception:
            parts.append(str(ts))
    return "  •  ".join(parts)


class ManagementDiagnosticUiMixin:
    """Read-only presentation of retained diagnostic cause telemetry."""

    def _build_management_diagnostic_card(self, right, card_bg: str, border_color: str) -> None:
        card = self._management_card(right, "NGUYÊN NHÂN & CHẨN ĐOÁN", card_bg, border_color)
        self.mgmt_diag_badge = tk.Label(
            card, text="CURRENT: --", font=("Segoe UI", 8, "bold"),
            bg=COLORS.border, fg=COLORS.muted, padx=8, pady=3,
        )
        self.mgmt_diag_badge.grid(row=0, column=9, sticky="e")

        self.mgmt_diag_current_title = tk.Label(
            card, text="Chờ dữ liệu /diagnostic", anchor="w",
            font=("Segoe UI", 10, "bold"), bg=card_bg, fg=COLORS.text,
        )
        self.mgmt_diag_current_title.grid(row=1, column=0, columnspan=10, sticky="ew", pady=(1, 1))
        self.mgmt_diag_current_reason = tk.Label(
            card, text="Firmware cũ vẫn giám sát được status/io/health nhưng chưa truy nguyên được nguyên nhân lỗi.",
            anchor="w", justify=tk.LEFT, wraplength=760,
            font=("Segoe UI", 9), bg=card_bg, fg=COLORS.text_secondary,
        )
        self.mgmt_diag_current_reason.grid(row=2, column=0, columnspan=10, sticky="ew")
        self.mgmt_diag_current_meta = tk.Label(
            card, text="READ-ONLY • Tool chỉ subscribe telemetry", anchor="w",
            font=("Segoe UI", 8), bg=card_bg, fg=COLORS.muted,
        )
        self.mgmt_diag_current_meta.grid(row=3, column=0, columnspan=10, sticky="ew", pady=(2, 5))

        self.mgmt_diag_last = tk.Label(
            card, text="Lỗi gần nhất: --", anchor="w", justify=tk.LEFT, wraplength=760,
            font=("Segoe UI", 8), bg=card_bg, fg=COLORS.text_secondary,
        )
        self.mgmt_diag_last.grid(row=4, column=0, columnspan=10, sticky="ew", pady=(1, 0))
        self.mgmt_diag_previous = tk.Label(
            card, text="Lỗi trước đó: --", anchor="w", justify=tk.LEFT, wraplength=760,
            font=("Segoe UI", 8), bg=card_bg, fg=COLORS.muted,
        )
        self.mgmt_diag_previous.grid(row=5, column=0, columnspan=10, sticky="ew", pady=(1, 0))
        card.grid_columnconfigure(0, weight=1)

    def _reset_management_diagnostic(self) -> None:
        if not hasattr(self, "mgmt_diag_badge"):
            return
        self.mgmt_diag_badge.config(text="CURRENT: --", bg=COLORS.border, fg=COLORS.muted)
        self.mgmt_diag_current_title.config(text="Chờ dữ liệu /diagnostic", fg=COLORS.text)
        self.mgmt_diag_current_reason.config(
            text="Firmware cũ vẫn giám sát được status/io/health nhưng chưa truy nguyên được nguyên nhân lỗi."
        )
        self.mgmt_diag_current_meta.config(text="READ-ONLY • Tool chỉ subscribe telemetry")
        self.mgmt_diag_last.config(text="Lỗi gần nhất: --")
        self.mgmt_diag_previous.config(text="Lỗi trước đó: --")

    def _diagnostic_event_line(self, prefix: str, event: dict | None) -> str:
        if not event or int(event.get("id", 0) or 0) == 0:
            return f"{prefix}: --"
        return (
            f"{prefix}: {diagnostic_event_title(event)} • "
            f"{diagnostic_reason_text(event.get('reason', ''))} • {diagnostic_event_meta(event)}"
        )

    def _on_mqtt_diagnostic_state(self, callbox_id: str, state: dict) -> None:
        import time

        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        record["diagnostic"] = state
        record["diagnostic_rx"] = now
        self._management_update_fleet_row(callbox_id, record)
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return

        self._mgmt_last_diagnostic_rx = now
        current = state.get("current") or {}
        last = state.get("last") or {}
        previous = state.get("previous")

        if bool(current.get("active")) and str(current.get("code", "none")) != "none":
            severity = str(current.get("severity", "warning")).lower()
            if severity == "fault":
                bg, fg, badge = COLORS.danger_bg, COLORS.danger_text, "CURRENT: FAULT"
            else:
                bg, fg, badge = COLORS.warning_bg, COLORS.warning_text, "CURRENT: WARN"
            self.mgmt_diag_badge.config(text=badge, bg=bg, fg=fg)
            self.mgmt_diag_current_title.config(text=diagnostic_event_title(current), fg=fg)
            self.mgmt_diag_current_reason.config(text=diagnostic_reason_text(current.get("reason", "")))
            self.mgmt_diag_current_meta.config(text=diagnostic_event_meta(current) + "  •  READ-ONLY")
        else:
            self.mgmt_diag_badge.config(text="CURRENT: NONE", bg=COLORS.success_bg, fg=COLORS.success_text)
            self.mgmt_diag_current_title.config(text="Không có lỗi chẩn đoán đang hoạt động", fg=COLORS.success_text)
            self.mgmt_diag_current_reason.config(text="Thiết bị không báo current fault trong snapshot diagnostic.")
            self.mgmt_diag_current_meta.config(text="READ-ONLY • Tool chỉ subscribe telemetry")

        self.mgmt_diag_last.config(text=self._diagnostic_event_line("Lỗi gần nhất", last))
        self.mgmt_diag_previous.config(text=self._diagnostic_event_line("Lỗi trước đó", previous))
        last_id = int(last.get("id", 0) or 0)
        if last_id:
            self._management_note_change(
                "diagnostic_last_id", last_id,
                f"Diagnostic → {diagnostic_event_title(last)} • {diagnostic_reason_text(last.get('reason', ''))}",
            )

    def _on_mqtt_trace_event(self, callbox_id: str, event: dict) -> None:
        import time

        now = time.monotonic()
        if not self._management_detail_is_live(callbox_id, now):
            return
        record = self._fleet_devices.setdefault(callbox_id, {})
        traces = record.setdefault("trace", [])
        traces.append(event)
        del traces[:-50]
        record.update(trace_rx=now, management_supported=True)
        if callbox_id != self.mgmt_target_id_var.get().strip():
            return
        self._mgmt_last_trace_rx = now
        reason = f" ({event.get('reason')})" if event.get("reason") else ""
        self._management_log_event(
            f"TRACE task={event.get('task', 0)} seq={event.get('seq', 0)} → {event.get('stage') or '-'}{reason}"
        )
