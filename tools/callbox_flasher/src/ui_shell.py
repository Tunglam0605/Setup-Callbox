from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from tools.callbox_flasher.src.resources import resource_path
from tools.callbox_flasher.src.ui_theme import COLORS, configure_ttk_styles


class ShellUiMixin:
    """Application shell: clean separation between factory and engineering workspaces."""

    def _setup_ui(self, manifest_info: str) -> None:
        self.root.configure(bg=COLORS.canvas)
        configure_ttk_styles(self.root)

        self._main_frame = tk.Frame(self.root, bg=COLORS.canvas, padx=10, pady=8)
        self._main_frame.pack(fill=tk.BOTH, expand=True)
        self._build_app_header(self._main_frame, manifest_info)
        self._build_mode_workspace(self._main_frame)

        self._setup_worker_tab(self._worker_page)
        self._page_heading(self._engineer_page_inner["device"], "THIẾT BỊ", "USB  /  Firmware  /  NVS  /  Flash")
        self._build_connection_card(self._engineer_page_inner["device"])
        self._build_firmware_card(self._engineer_page_inner["device"])
        self._build_config_card(self._engineer_page_inner["device"])
        self._build_action_card(self._engineer_page_inner["device"])
        self._build_log_card(self._engineer_page_inner["device"])
        self._set_device_maintenance_visible(False)
        self._page_heading(self._engineer_page_inner["remote"], "KẾT NỐI TỪ XA", "MQTT  /  Remote Config  /  Control")
        self._setup_mqtt_tab(self._engineer_page_inner["remote"], COLORS.white, COLORS.border, COLORS.canvas)
        self._setup_management_tab(self._engineer_page_inner["overview"], COLORS.white, COLORS.border, COLORS.canvas)
        self._build_system_page(self._engineer_page_inner["system"])

        self._show_worker_mode()
        self._update_flash_button()

    def _build_app_header(self, parent: tk.Frame, manifest_info: str) -> None:
        header = tk.Frame(parent, bg=COLORS.text, padx=12, pady=7)
        header.pack(fill=tk.X, pady=(0, 6))
        self._logo_image = None
        try:
            logo_png = resource_path("assets") / "logo_48.png"
            if logo_png.is_file():
                self._logo_image = tk.PhotoImage(file=str(logo_png))
                tk.Label(header, image=self._logo_image, bg=COLORS.text).pack(side=tk.LEFT, padx=(0, 10))
        except Exception:
            pass

        title = tk.Frame(header, bg=COLORS.text)
        title.pack(side=tk.LEFT)
        tk.Label(title, text="AUBOT CallBox Tool", font=("Segoe UI", 14, "bold"), fg=COLORS.white, bg=COLORS.text).pack(anchor="w")
        self.header_context_label = tk.Label(title, text=manifest_info, font=("Segoe UI", 8), fg="#94a3b8", bg=COLORS.text)
        self.header_context_label.pack(anchor="w", pady=(1, 0))

        self.header_mode_button = ttk.Button(header, text="KỸ THUẬT", style="Secondary.TButton", command=self._toggle_engineer_mode)
        self.header_mode_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.header_mode_badge = tk.Label(header, text="SẢN XUẤT", font=("Segoe UI", 8, "bold"), fg="#0f172a", bg="#bae6fd", padx=9, pady=4)
        self.header_mode_badge.pack(side=tk.RIGHT)

    def _build_mode_workspace(self, parent: tk.Frame) -> None:
        self._mode_host = tk.Frame(parent, bg=COLORS.canvas)
        self._mode_host.pack(fill=tk.BOTH, expand=True)
        self._mode_host.grid_rowconfigure(0, weight=1)
        self._mode_host.grid_columnconfigure(0, weight=1)

        self._worker_page = tk.Frame(self._mode_host, bg=COLORS.canvas)
        self._engineer_workspace = tk.Frame(self._mode_host, bg=COLORS.canvas)
        self._worker_page.grid(row=0, column=0, sticky="nsew")
        self._engineer_workspace.grid(row=0, column=0, sticky="nsew")

        sidebar = tk.Frame(self._engineer_workspace, bg="#111827", width=220, padx=10, pady=12)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        content = tk.Frame(self._engineer_workspace, bg=COLORS.canvas)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        tk.Label(sidebar, text="ENGINEERING WORKSPACE", font=("Segoe UI", 11, "bold"), fg=COLORS.white, bg="#111827").pack(anchor="w", padx=6, pady=(0, 2))
        tk.Label(sidebar, text="Service • diagnostics • update", font=("Segoe UI", 8), fg="#94a3b8", bg="#111827").pack(anchor="w", padx=6, pady=(0, 14))

        self._engineer_pages: dict[str, tk.Frame] = {}
        self._engineer_page_inner: dict[str, tk.Frame] = {}
        self._engineer_nav_buttons: dict[str, tk.Button] = {}

        nav = (
            ("CALLBOX", "overview", "Tổng quan", "Online • Task • I/O • Health"),
            ("CALLBOX", "device", "Nạp & bảo trì", "USB • Nạp xưởng • Service"),
            ("CALLBOX", "remote", "Từ xa", "MQTT • Control • Config"),
            ("HỆ THỐNG", "system", "Cấu hình & cập nhật", "Factory profile • Version"),
        )
        last_section = None
        for section, key, title, subtitle in nav:
            if section != last_section:
                tk.Label(sidebar, text=section, font=("Segoe UI", 7, "bold"), fg="#64748b", bg="#111827").pack(anchor="w", padx=6, pady=(12 if last_section else 8, 3))
                last_section = section
            button = tk.Button(
                sidebar, text=f"  {title}\n  {subtitle}", command=lambda k=key: self._show_engineer_page(k),
                anchor="w", justify=tk.LEFT, font=("Segoe UI", 9, "bold"), relief=tk.FLAT, bd=0,
                bg="#111827", fg="#cbd5e1", activebackground="#1e293b", activeforeground=COLORS.white,
                padx=10, pady=7, cursor="hand2",
            )
            button.pack(fill=tk.X, pady=1)
            self._engineer_nav_buttons[key] = button

            page = tk.Frame(content, bg=COLORS.canvas)
            page.grid(row=0, column=0, sticky="nsew")
            self._engineer_pages[key] = page
            if key in ("overview", "device", "remote"):
                self._engineer_page_inner[key] = self._make_scrollable_page(page)
            else:
                self._engineer_page_inner[key] = page

        tk.Frame(sidebar, bg="#334155", height=1).pack(fill=tk.X, padx=6, pady=(18, 8))
        ttk.Button(sidebar, text="←  VỀ SẢN XUẤT", style="Secondary.TButton", command=self._show_worker_mode).pack(fill=tk.X, padx=4)

    def _make_scrollable_page(self, page: tk.Frame) -> tk.Frame:
        canvas = tk.Canvas(page, bg=COLORS.canvas, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=COLORS.canvas, padx=2, pady=2)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        return inner

    def _toggle_engineer_mode(self) -> None:
        if getattr(self, "engineer_mode", False):
            self._show_worker_mode()
        else:
            self._show_engineer_mode()

    def _show_worker_mode(self) -> None:
        self.engineer_mode = False
        try:
            self.root.state("normal")
        except Exception:
            pass
        self._engineer_workspace.grid_remove()
        self._worker_page.grid(row=0, column=0, sticky="nsew")
        self._worker_page.tkraise()
        self.header_mode_button.config(text="KỸ THUẬT")
        self.header_mode_badge.config(text="SẢN XUẤT", bg="#bae6fd", fg=COLORS.text)
        self.root.minsize(820, 560)
        self.root.geometry("1040x650")

    def _show_engineer_mode(self) -> None:
        self.engineer_mode = True
        self._worker_page.grid_remove()
        self._engineer_workspace.grid(row=0, column=0, sticky="nsew")
        self._engineer_workspace.tkraise()
        self.header_mode_button.config(text="SẢN XUẤT")
        self.header_mode_badge.config(text="KỸ THUẬT", bg="#fde68a", fg="#78350f")
        self.root.minsize(1180, 760)
        if self.root.winfo_width() < 1180:
            self.root.geometry("1440x900")
        self._show_engineer_page("overview")

    def _show_engineer_page(self, key: str) -> None:
        page = self._engineer_pages.get(key)
        if page is None:
            return
        page.tkraise()
        for name, button in self._engineer_nav_buttons.items():
            active = name == key
            button.config(bg="#075985" if active else "#111827", fg=COLORS.white if active else "#cbd5e1")

    @staticmethod
    def _page_heading(parent: tk.Frame, title: str, breadcrumb: str) -> None:
        head = tk.Frame(parent, bg=COLORS.canvas, pady=4)
        head.pack(fill=tk.X, pady=(0, 2))
        tk.Label(head, text=title, font=("Segoe UI", 15, "bold"), fg=COLORS.text, bg=COLORS.canvas).pack(anchor="w")
        tk.Label(head, text=breadcrumb, font=("Segoe UI", 8), fg=COLORS.muted, bg=COLORS.canvas).pack(anchor="w", pady=(1, 0))
