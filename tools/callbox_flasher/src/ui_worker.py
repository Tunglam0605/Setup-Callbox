from __future__ import annotations

import copy
import re
import tkinter as tk
from tkinter import messagebox, ttk

from tools.callbox_flasher.src.models import ProvisionMode, ProvisionState
from tools.callbox_flasher.src.ui_theme import COLORS

CALLBOX_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
PORT_POLL_MS = 1000


class WorkerUiMixin:
    """Factory-floor workflow: auto-detect USB, enter ID, press one flash button."""

    def _setup_worker_tab(self, parent: tk.Frame) -> None:
        shell = tk.Frame(parent, bg=COLORS.canvas, padx=18, pady=14)
        shell.pack(fill=tk.BOTH, expand=True)

        title_row = tk.Frame(shell, bg=COLORS.canvas)
        title_row.pack(fill=tk.X, pady=(2, 10))
        tk.Label(title_row, text="NẠP CALLBOX", font=("Segoe UI", 17, "bold"), fg=COLORS.text, bg=COLORS.canvas).pack(side=tk.LEFT)
        tk.Label(title_row, text="Nạp xưởng tự động • Bootloader + Application + NVS", font=("Segoe UI", 9), fg=COLORS.muted, bg=COLORS.canvas).pack(side=tk.LEFT, padx=(12, 0), pady=(5, 0))

        readiness = tk.Frame(shell, bg=COLORS.canvas)
        readiness.pack(fill=tk.X, pady=(0, 8))
        for col in range(3):
            readiness.grid_columnconfigure(col, weight=1)

        def status_tile(column: int, title: str) -> tuple[tk.Frame, tk.Label]:
            tile = tk.Frame(readiness, bg=COLORS.white, highlightbackground=COLORS.border, highlightthickness=1, padx=12, pady=9)
            tile.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 4, 0))
            tk.Label(tile, text=title, font=("Segoe UI", 8, "bold"), fg=COLORS.muted, bg=COLORS.white).pack(anchor="w")
            value = tk.Label(tile, text="ĐANG KIỂM TRA...", font=("Segoe UI", 10, "bold"), fg=COLORS.info, bg=COLORS.white, anchor="w", justify=tk.LEFT, wraplength=300)
            value.pack(fill=tk.X, pady=(3, 0))
            return tile, value

        device_tile, self.worker_device_label = status_tile(0, "THIẾT BỊ USB")
        _firmware_tile, self.worker_release_label = status_tile(1, "FIRMWARE")
        _profile_tile, self.worker_profile_label = status_tile(2, "CẤU HÌNH XƯỞNG")
        self.worker_profile_action = ttk.Button(_profile_tile, text="CẤU HÌNH", style="Secondary.TButton", command=self._open_factory_setup)

        self.worker_port_var = tk.StringVar(value="")
        self.worker_port_combo = ttk.Combobox(device_tile, textvariable=self.worker_port_var, state="readonly", font=("Segoe UI", 9))
        self.worker_port_combo.bind("<<ComboboxSelected>>", self._worker_on_port_changed)

        action = tk.Frame(shell, bg=COLORS.white, highlightbackground=COLORS.border, highlightthickness=1, padx=16, pady=14)
        action.pack(fill=tk.X, pady=4)
        action.grid_columnconfigure(1, weight=1)
        tk.Label(action, text="Callbox ID", font=("Segoe UI", 9, "bold"), fg=COLORS.text_secondary, bg=COLORS.white).grid(row=0, column=0, sticky="w", padx=(0, 10))
        default_id = getattr(getattr(self, "factory_profile", None), "callbox_id", "001")
        self.worker_id_var = tk.StringVar(value=default_id)
        self.worker_id_entry = ttk.Entry(action, textvariable=self.worker_id_var, width=18, font=("Segoe UI", 14, "bold"))
        self.worker_id_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), ipady=4)
        self.worker_id_var.trace_add("write", lambda *_: self._worker_update_button_state())
        self.worker_flash_button = ttk.Button(action, text="NẠP CALLBOX", style="WorkerPrimary.TButton", command=self._on_worker_flash_click, state=tk.DISABLED)
        self.worker_flash_button.grid(row=0, column=2, sticky="ew", ipadx=24, ipady=6)

        self.worker_progress = ttk.Progressbar(action, mode="determinate", maximum=100)
        self.worker_progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(14, 5))
        status_row = tk.Frame(action, bg=COLORS.white)
        status_row.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.worker_phase_label = tk.Label(status_row, text="Sẵn sàng", font=("Segoe UI", 9, "bold"), fg=COLORS.muted, bg=COLORS.white)
        self.worker_phase_label.pack(side=tk.LEFT)
        self.worker_result_label = tk.Label(status_row, text="", font=("Segoe UI", 9, "bold"), fg=COLORS.success, bg=COLORS.white, justify=tk.RIGHT)
        self.worker_result_label.pack(side=tk.RIGHT)

        footer = tk.Frame(shell, bg=COLORS.canvas)
        footer.pack(fill=tk.X, pady=(6, 0))
        tk.Label(footer, text="AUBOT • Production mode", font=("Segoe UI", 8), fg=COLORS.muted, bg=COLORS.canvas).pack(side=tk.LEFT)
        self.worker_update_button = ttk.Button(footer, text="CẬP NHẬT TOOL", command=self._on_tool_update_click)
        # Hidden unless a verified tool update is available.

        self._worker_refresh_profile_summary()
        self._worker_refresh_release_summary()
        self._worker_sync_ports()
        self._worker_update_button_state()
        self.root.after(PORT_POLL_MS, self._worker_poll_ports)

    def _worker_poll_ports(self) -> None:
        try:
            if not self.controller.busy:
                self._refresh_ports()
            self.root.after(PORT_POLL_MS, self._worker_poll_ports)
        except tk.TclError:
            pass

    def _worker_sync_ports(self) -> None:
        if not hasattr(self, "worker_port_combo"):
            return
        devices = [p.device for p in getattr(self, "ports", ())]
        selected = self.worker_port_var.get().strip()
        self.worker_port_combo["values"] = devices

        if len(devices) == 0:
            self.worker_port_var.set("")
            self.worker_port_combo.pack_forget()
            self.worker_device_label.config(text="CHƯA KẾT NỐI CALLBOX", fg=COLORS.warning)
        elif len(devices) == 1:
            self.worker_port_var.set(devices[0])
            self.worker_port_combo.pack_forget()
            info = next((p for p in self.ports if p.device == devices[0]), None)
            desc = f" • {info.description}" if info and info.description else ""
            self.worker_device_label.config(
                text=f"ĐÃ KẾT NỐI  •  {devices[0]}{desc}",
                fg=COLORS.success,
            )
        else:
            if selected not in devices:
                self.worker_port_var.set("")
            self.worker_device_label.config(
                text=f"PHÁT HIỆN {len(devices)} THIẾT BỊ  •  Chọn cổng cần nạp",
                fg=COLORS.warning,
            )
            if not self.worker_port_combo.winfo_ismapped():
                self.worker_port_combo.pack(fill=tk.X, pady=(8, 0))
        self._worker_update_button_state()

    def _worker_refresh_profile_summary(self) -> None:
        profile = getattr(self, "factory_profile", None)
        if profile is None:
            text = "CHƯA CẤU HÌNH  •  Kỹ thuật → Hệ thống"
            fg = COLORS.danger
        else:
            text = "SẴN SÀNG"
            fg = COLORS.success
        if hasattr(self, "worker_profile_label"):
            self.worker_profile_label.config(text=text, fg=fg)
        if hasattr(self, "worker_profile_action"):
            if profile is None:
                if not self.worker_profile_action.winfo_ismapped():
                    self.worker_profile_action.pack(anchor="w", pady=(6, 0))
            else:
                self.worker_profile_action.pack_forget()

    def _open_factory_setup(self) -> None:
        self._show_engineer_mode()
        self._show_engineer_page("system")

    def _worker_refresh_release_summary(self) -> None:
        if not hasattr(self, "worker_release_label"):
            return
        try:
            manifest = self.release_manager.load_active_firmware_manifest()
            version = self.release_manager.active_firmware_version()
            source = "đã đồng bộ" if manifest.baseline_version.startswith("release-") else "đi kèm tool"
            self.worker_release_label.config(
                text=f"v{version}  •  SHA-256 OK",
                fg=COLORS.success,
            )
        except Exception as error:
            self.worker_release_label.config(text="CHƯA SẴN SÀNG", fg=COLORS.danger)
        self._worker_update_button_state()

    def _worker_on_port_changed(self, _event=None) -> None:
        self._worker_update_button_state()

    def _worker_update_button_state(self) -> None:
        if not hasattr(self, "worker_flash_button"):
            return
        port = self.worker_port_var.get().strip() if hasattr(self, "worker_port_var") else ""
        callbox_id = self.worker_id_var.get().strip() if hasattr(self, "worker_id_var") else ""
        ready = bool(
            port
            and CALLBOX_ID_RE.fullmatch(callbox_id)
            and not self.controller.busy
            and getattr(self, "bundle_info", None) is not None
            and getattr(self, "factory_profile", None) is not None
        )
        self.worker_flash_button.config(state=tk.NORMAL if ready else tk.DISABLED)

    def _on_worker_flash_click(self) -> None:
        port = self.worker_port_var.get().strip()
        callbox_id = self.worker_id_var.get().strip()
        if not port:
            messagebox.showwarning("Chưa có thiết bị", "Hãy cắm Callbox vào USB.", parent=self.root)
            return
        if not CALLBOX_ID_RE.fullmatch(callbox_id):
            messagebox.showwarning(
                "Callbox ID không hợp lệ",
                "ID chỉ được dùng chữ, số, dấu _ hoặc -, tối đa 16 ký tự.",
                parent=self.root,
            )
            return
        if self.controller.busy:
            return

        try:
            manifest = self.release_manager.load_active_firmware_manifest()
            manifest.verify_assets()
            config = copy.deepcopy(self.factory_profile)
            config.callbox_id = callbox_id
            config.sanitize()
        except Exception as error:
            messagebox.showerror("Không thể nạp", str(error), parent=self.root)
            return

        self._worker_job_active = True
        self.worker_progress["value"] = 0
        self.worker_phase_label.config(text="Đang bắt đầu...", fg=COLORS.info)
        self.worker_result_label.config(text="", fg=COLORS.success)
        self.worker_flash_button.config(state=tk.DISABLED)
        self._set_inputs_enabled(False)
        self._append_log(f"--- NẠP XƯỞNG Callbox {callbox_id} vào {port}: Boot + Partition + OTA + App + NVS ---")
        self.controller.start(
            port=port,
            application=manifest.application.path,
            emit=self.event_queue.put,
            mode=ProvisionMode.FACTORY,
            config=config,
        )

    def _worker_render_event(self, event) -> None:
        if not hasattr(self, "worker_progress"):
            return
        self.worker_progress["value"] = event.progress
        self.worker_phase_label.config(text=event.message, fg=COLORS.info)
        if event.state == ProvisionState.SUCCEEDED:
            result = event.result
            version = result.version if result else ""
            mac = result.mac.upper() if result and result.mac else "N/A"
            finished_id = self.worker_id_var.get().strip()
            self.worker_phase_label.config(text="HOÀN THÀNH", fg=COLORS.success)
            self.worker_result_label.config(
                text=f"✓ Callbox {finished_id}  •  FW {version}  •  MAC {mac}",
                fg=COLORS.success,
            )
            if self._worker_job_active:
                self._worker_increment_id()
            self._worker_job_active = False
        elif event.state == ProvisionState.FAILED:
            self.worker_phase_label.config(text="NẠP THẤT BẠI", fg=COLORS.danger)
            self.worker_result_label.config(text=event.message, fg=COLORS.danger)
            self._worker_job_active = False
        self._worker_update_button_state()

    def _worker_increment_id(self) -> None:
        value = self.worker_id_var.get().strip()
        if value.isdigit():
            self.worker_id_var.set(str(int(value) + 1).zfill(len(value)))
