from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

from tools.callbox_flasher.src.image_validator import validate_application
from tools.callbox_flasher.src.release_update import launch_update_helper
from tools.callbox_flasher.src.ui_theme import COLORS


class UpdateUiMixin:
    """Background firmware sync and verified self-update for the public release channel."""

    def _set_tool_update_buttons(self, text: str, state=tk.NORMAL, visible: bool = True) -> None:
        for name in ("worker_update_button", "system_update_button"):
            button = getattr(self, name, None)
            if button is None:
                continue
            button.config(text=text, state=state)
            if visible:
                if not button.winfo_ismapped():
                    button.pack(side=tk.LEFT, padx=(8, 0) if name == "system_update_button" else 0)
            else:
                button.pack_forget()

    def _start_release_check(self) -> None:
        if getattr(self, "_release_check_running", False):
            return
        self._release_check_running = True
        if hasattr(self, "worker_release_label"):
            self.worker_release_label.config(text="Đang kiểm tra bản phát hành mới...", fg=COLORS.info)

        def run() -> None:
            try:
                catalog = self.release_manager.fetch_catalog()
                firmware_updated = False
                if self.release_manager.firmware_update_available(catalog):
                    self.release_manager.sync_firmware(catalog)
                    firmware_updated = True
                self.root.after(0, self._on_release_check_success, catalog, firmware_updated)
            except Exception as error:
                self.root.after(0, self._on_release_check_error, error)

        threading.Thread(target=run, daemon=True, name="release-check").start()

    def _on_release_check_success(self, catalog, firmware_updated: bool) -> None:
        self._release_check_running = False
        self.release_catalog = catalog
        try:
            manifest = self.release_manager.load_active_firmware_manifest()
            self.bundle_info = validate_application(manifest.application.path)
        except Exception as error:
            self.bundle_info = None
            if hasattr(self, "worker_release_label"):
                self.worker_release_label.config(text=f"Firmware lỗi: {error}", fg=COLORS.danger)
            self._worker_update_button_state()
            return

        self._worker_refresh_release_summary()
        if hasattr(self, "system_firmware_var"):
            self.system_firmware_var.set(f"v{manifest.firmware_version}")
        if hasattr(self, "system_release_var"):
            self.system_release_var.set("Đã đồng bộ • gói phát hành hợp lệ")
        if firmware_updated:
            self._append_log(
                f"Đã tải và xác minh firmware v{catalog.firmware.firmware_version} từ Setup-Callbox."
            )
        if self.release_manager.tool_update_available(catalog):
            self._set_tool_update_buttons(f"CẬP NHẬT TOOL v{catalog.tool.version}", visible=True)
            if hasattr(self, "worker_release_label"):
                self.worker_release_label.config(fg=COLORS.warning)
            if hasattr(self, "system_release_var"):
                self.system_release_var.set(f"Có Tool v{catalog.tool.version} mới")
        else:
            self._set_tool_update_buttons("CẬP NHẬT TOOL", visible=False)
            if hasattr(self, "system_release_var"):
                self.system_release_var.set("Tool và firmware đang ở trạng thái đã xác minh")

    def _on_release_check_error(self, error: Exception) -> None:
        self._release_check_running = False
        # GitHub/network failure is not a production blocker. Use the last verified package.
        try:
            version = self.release_manager.active_firmware_version()
            text = f"Firmware v{version}  •  dùng bản đã xác minh  •  GitHub tạm thời không truy cập được"
            fg = COLORS.warning
        except Exception:
            text = f"Không kiểm tra được bản phát hành: {error}"
            fg = COLORS.danger
        if hasattr(self, "worker_release_label"):
            self.worker_release_label.config(text=text, fg=fg)
        if hasattr(self, "system_release_var"):
            self.system_release_var.set("Offline • dùng gói đã xác minh trong máy")
        self._append_log(f"Release check: {error}")
        self._worker_update_button_state()

    def _on_tool_update_click(self) -> None:
        catalog = getattr(self, "release_catalog", None)
        if catalog is None or not self.release_manager.tool_update_available(catalog):
            self._start_release_check()
            return
        if self.controller.busy:
            messagebox.showwarning(
                "Đang nạp Callbox",
                "Không thể cập nhật tool khi đang ghi flash.",
                parent=self.root,
            )
            return
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Development mode",
                "Self-update chỉ áp dụng cho bản Setup-CallBox.exe đã đóng gói.",
                parent=self.root,
            )
            return

        self._set_tool_update_buttons("ĐANG TẢI TOOL...", state=tk.DISABLED, visible=True)

        def progress(_label: str, done: int, total: int) -> None:
            pct = int(done * 100 / total) if total else 0
            self.root.after(0, lambda: self._set_tool_update_buttons(f"ĐANG TẢI TOOL {pct}%", state=tk.DISABLED, visible=True))

        def run() -> None:
            try:
                path, digest = self.release_manager.download_tool_update(catalog, progress)
                self.root.after(0, self._apply_downloaded_tool_update, path, digest)
            except Exception as error:
                self.root.after(0, self._tool_update_failed, error)

        threading.Thread(target=run, daemon=True, name="tool-update").start()

    def _apply_downloaded_tool_update(self, path, digest: str) -> None:
        try:
            self._set_tool_update_buttons("ĐANG KHỞI ĐỘNG LẠI...", state=tk.DISABLED, visible=True)
            launch_update_helper(path, sys.executable, os.getpid(), digest)
            self.root.after(200, self.root.destroy)
        except Exception as error:
            self._tool_update_failed(error)

    def _tool_update_failed(self, error: Exception) -> None:
        catalog = getattr(self, "release_catalog", None)
        label = f"CẬP NHẬT TOOL v{catalog.tool.version}" if catalog else "CẬP NHẬT TOOL"
        self._set_tool_update_buttons(label, state=tk.NORMAL, visible=True)
        messagebox.showerror("Cập nhật tool thất bại", str(error), parent=self.root)
