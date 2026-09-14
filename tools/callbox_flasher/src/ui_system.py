from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from tools.callbox_flasher.src.app_version import __version__
from tools.callbox_flasher.src.factory_profile import save_factory_profile, validate_factory_profile_for_worker
from tools.callbox_flasher.src.ui_theme import COLORS


class SystemUiMixin:
    """Factory defaults and release/update system page."""

    def _build_system_page(self, parent: tk.Frame) -> None:
        shell = tk.Frame(parent, bg=COLORS.canvas, padx=8, pady=8)
        shell.pack(fill=tk.BOTH, expand=True)
        tk.Label(shell, text="HỆ THỐNG", font=("Segoe UI", 15, "bold"), fg=COLORS.text, bg=COLORS.canvas).pack(anchor="w")
        tk.Label(shell, text="Cấu hình xưởng và quản lý phiên bản.", font=("Segoe UI", 9), fg=COLORS.muted, bg=COLORS.canvas).pack(anchor="w", pady=(2, 10))

        factory = tk.Frame(shell, bg=COLORS.white, highlightbackground=COLORS.border, highlightthickness=1, padx=14, pady=12)
        factory.pack(fill=tk.X, pady=(0, 8))
        head = tk.Frame(factory, bg=COLORS.white)
        head.grid(row=0, column=0, columnspan=6, sticky="ew", pady=(0, 8))
        tk.Label(head, text="CẤU HÌNH XƯỞNG", font=("Segoe UI", 10, "bold"), fg=COLORS.text, bg=COLORS.white).pack(side=tk.LEFT)
        self.system_factory_status = tk.Label(head, text="SẴN SÀNG" if getattr(self, "factory_profile", None) else "CHƯA CẤU HÌNH", font=("Segoe UI", 9, "bold"), fg=COLORS.success if getattr(self, "factory_profile", None) else COLORS.danger, bg=COLORS.white)
        self.system_factory_status.pack(side=tk.RIGHT)

        fields = (
            ("Wi-Fi SSID", self.cfg_ssid_var, False),
            ("Wi-Fi Password", self.cfg_pass_var, True),
            ("MQTT Broker", self.cfg_broker_var, False),
            ("MQTT Port", self.cfg_port_var, False),
            ("MQTT User", self.cfg_user_var, False),
            ("MQTT Password", self.cfg_mqtt_pass_var, True),
        )
        for index, (label, variable, secret) in enumerate(fields):
            row = 1 + index // 3
            col = (index % 3) * 2
            tk.Label(factory, text=label, font=("Segoe UI", 8, "bold"), fg=COLORS.muted, bg=COLORS.white).grid(row=row, column=col, sticky="w", padx=(0, 5), pady=4)
            ttk.Entry(factory, textvariable=variable, show="*" if secret else "", width=22).grid(row=row, column=col + 1, sticky="ew", padx=(0, 12), pady=4)
            factory.grid_columnconfigure(col + 1, weight=1)

        tk.Label(factory, text="Operating Version", font=("Segoe UI", 8, "bold"), fg=COLORS.muted, bg=COLORS.white).grid(row=3, column=0, sticky="w", pady=(6, 4))
        ttk.Combobox(factory, textvariable=self.cfg_ver_var, values=["No version", "1.0", "2.0"], state="readonly", width=16).grid(row=3, column=1, sticky="w", pady=(6, 4))
        actions_factory = tk.Frame(factory, bg=COLORS.white)
        actions_factory.grid(row=3, column=3, columnspan=3, sticky="e", pady=(6, 4))
        self.system_use_default_button = ttk.Button(
            actions_factory, text="DÙNG MẶC ĐỊNH ĐÃ LƯU", style="Secondary.TButton", command=self._restore_factory_profile_in_system,
            state=tk.NORMAL if getattr(self, "factory_profile", None) else tk.DISABLED,
        )
        self.system_use_default_button.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(actions_factory, text="LƯU LÀM MẶC ĐỊNH", style="Primary.TButton", command=self._save_factory_profile_from_system).pack(side=tk.LEFT)
        tk.Label(factory, text="Mặc định = cấu hình sẽ dùng nguyên nếu không chỉnh • chỉ lưu cục bộ trên máy này", font=("Segoe UI", 8), fg=COLORS.muted, bg=COLORS.white).grid(row=4, column=0, columnspan=6, sticky="w", pady=(3, 0))

        card = tk.Frame(shell, bg=COLORS.white, highlightbackground=COLORS.border, highlightthickness=1, padx=14, pady=12)
        card.pack(fill=tk.X)
        self.system_tool_var = tk.StringVar(value=f"v{__version__}")
        try:
            firmware_version = self.release_manager.active_firmware_version()
        except Exception:
            firmware_version = "--"
        self.system_firmware_var = tk.StringVar(value=f"v{firmware_version}")
        self.system_release_var = tk.StringVar(value="Đang kiểm tra...")
        tk.Label(card, text="PHIÊN BẢN & CẬP NHẬT", font=("Segoe UI", 10, "bold"), fg=COLORS.text, bg=COLORS.white).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        for row, (label, var) in enumerate((("Tool", self.system_tool_var), ("Firmware", self.system_firmware_var), ("Trạng thái", self.system_release_var)), start=1):
            tk.Label(card, text=label, font=("Segoe UI", 8, "bold"), fg=COLORS.muted, bg=COLORS.white, width=12, anchor="w").grid(row=row, column=0, sticky="w", pady=4)
            tk.Label(card, textvariable=var, font=("Segoe UI", 10, "bold"), fg=COLORS.text, bg=COLORS.white).grid(row=row, column=1, sticky="w", pady=4)
        actions = tk.Frame(card, bg=COLORS.white)
        actions.grid(row=1, column=3, rowspan=3, sticky="e")
        ttk.Button(actions, text="KIỂM TRA CẬP NHẬT", style="Secondary.TButton", command=self._start_release_check).pack(anchor="e")
        self.system_update_button = ttk.Button(actions, text="CẬP NHẬT TOOL", style="Primary.TButton", command=self._on_tool_update_click)
        self.system_update_button.pack(anchor="e", pady=(6, 0))
        self.system_update_button.pack_forget()

    def _restore_factory_profile_in_system(self) -> None:
        profile = getattr(self, "factory_profile", None)
        if profile is None:
            messagebox.showwarning("Chưa có mặc định", "Máy này chưa có cấu hình xưởng mặc định đã lưu.", parent=self.root)
            return
        self._apply_factory_profile_to_form(profile)
        self.system_factory_status.config(text="ĐANG DÙNG MẶC ĐỊNH", fg=COLORS.success)

    def _save_factory_profile_from_system(self) -> None:
        try:
            config = self._get_device_config_from_ui()
            validate_factory_profile_for_worker(config)
            save_factory_profile(config)
            self.factory_profile = config
            self.factory_profile_error = ""
            self.system_factory_status.config(text="ĐÃ LƯU MẶC ĐỊNH", fg=COLORS.success)
            if hasattr(self, "system_use_default_button"):
                self.system_use_default_button.config(state=tk.NORMAL)
            self._worker_refresh_profile_summary()
            self._worker_update_button_state()
            messagebox.showinfo("Đã lưu cấu hình xưởng", "Cấu hình xưởng đã được lưu cục bộ trên máy này.", parent=self.root)
        except Exception as error:
            self.system_factory_status.config(text="CHƯA SẴN SÀNG", fg=COLORS.danger)
            messagebox.showerror("Không thể lưu cấu hình xưởng", str(error), parent=self.root)
