import os
import pathlib
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from tools.callbox_flasher.src.app_version import __version__
from tools.callbox_flasher.src.controller import ProvisionController
from tools.callbox_flasher.src.factory_profile import load_factory_profile
from tools.callbox_flasher.src.flash_manifest import load_baseline_manifest
from tools.callbox_flasher.src.image_validator import ImageValidationError, validate_application
from tools.callbox_flasher.src.models import (
    ApplicationInfo,
    DeviceConfig,
    ProvisionEvent,
    ProvisionMode,
    ProvisionState,
)
from tools.callbox_flasher.src.ports import automatic_port, discover_ports
from tools.callbox_flasher.src.resources import resource_path
from tools.callbox_flasher.src.self_update import (
    GitHubReleaseUpdater,
    UpdateError,
    launch_update_helper,
)
from tools.callbox_flasher.src.serial_reader import (
    SerialReaderError,
    query_device_config,
    query_device_status,
)
try:
    from tools.callbox_flasher.src.mqtt_remote_config import (
        CallboxRemoteConfigClient,
        MqttBrokerConfig,
        PAHO_AVAILABLE,
        RemoteConfigPayload,
    )
except ImportError:
    from mqtt_remote_config import (
        CallboxRemoteConfigClient,
        MqttBrokerConfig,
        PAHO_AVAILABLE,
        RemoteConfigPayload,
    )

STATE_COPY = {
    ProvisionState.READY: "Sẵn sàng",
    ProvisionState.VALIDATING: "Đang kiểm tra firmware",
    ProvisionState.CONNECTING: "Đang kết nối ESP32-S3",
    ProvisionState.ERASING: "Đang xóa flash",
    ProvisionState.WRITING: "Đang nạp firmware",
    ProvisionState.VERIFYING: "Đang xác minh",
    ProvisionState.RESETTING: "Đang khởi động lại",
    ProvisionState.SUCCEEDED: "NẠP THÀNH CÔNG",
    ProvisionState.FAILED: "NẠP THẤT BẠI",
}


def can_flash(port: str, image_valid: bool, busy: bool) -> bool:
    return bool(port and image_valid and not busy)


def can_flash_baseline(port: str, busy: bool) -> bool:
    return bool(port and not busy)


def can_flash_config(port: str, busy: bool) -> bool:
    return bool(port and not busy)


class FlasherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"AUBOT Setup CallBox v{__version__} – Nạp & Cấu hình ESP32")
        self.root.minsize(920, 740)
        self.root.geometry("960x780")
        self.mqtt_client: Optional[CallboxRemoteConfigClient] = None
        self.mqtt_is_connected = False
        self.mqtt_device_online = False
        self.mqtt_device_comm = "offline"
        self.mqtt_last_status_monotonic = 0.0
        self.mqtt_last_io_monotonic = 0.0
        self.mqtt_latest_version = ""
        self.mqtt_remote_pending_request_id: Optional[int] = None
        self.mqtt_remote_pending_since = 0.0
        self.update_client = GitHubReleaseUpdater()
        self.update_busy = False
        self.pending_update = None
        self.downloaded_update = None
        self.downloaded_update_sha = None
        self.factory_profile_error = None
        try:
            self.factory_profile = load_factory_profile()
        except Exception as error:
            self.factory_profile = DeviceConfig()
            self.factory_profile_error = str(error)


        # Window icon (hỗ trợ cả định dạng .ico và .png để đảm bảo hiển thị trên mọi phiên bản Windows)
        try:
            ico_file = resource_path("assets") / "app.ico"
            if ico_file.is_file():
                self.root.iconbitmap(default=str(ico_file))
        except Exception:
            pass
        try:
            png_file = resource_path("assets") / "logo_48.png"
            if png_file.is_file():
                self._app_icon_photo = tk.PhotoImage(file=str(png_file))
                self.root.iconphoto(True, self._app_icon_photo)
        except Exception:
            pass

        self.event_queue: queue.Queue[ProvisionEvent] = queue.Queue()
        self.controller = ProvisionController()
        self.app_info: Optional[ApplicationInfo] = None
        self.ports = discover_ports()

        # Try to load baseline manifest info
        try:
            manifest = load_baseline_manifest()
            manifest_info = f"Baseline: {manifest.baseline_version} ({manifest.chip.upper()} 16MB)"
        except Exception as e:
            manifest_info = f"Lỗi baseline manifest: {e}"

        self._setup_ui(manifest_info)
        self._apply_factory_profile(self.factory_profile)
        if self.factory_profile_error:
            self._append_log(f"Factory profile không hợp lệ: {self.factory_profile_error}")
        self._refresh_ports()
        self._auto_detect_firmware()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._drain_events)
        # Non-intrusive startup check: only changes the Update button when a newer
        # GitHub Release exists. Network failures stay silent at startup.
        self.root.after(2500, self._auto_check_update)

    def _setup_ui(self, manifest_info: str) -> None:
        bg_canvas = "#f1f5f9"
        card_bg = "#ffffff"
        border_color = "#e2e8f0"

        self.root.configure(bg=bg_canvas)

        style = ttk.Style()
        style.theme_use("clam")

        # Universal defaults for all ttk elements
        style.configure(".", background=bg_canvas, font=("Segoe UI", 10))
        style.configure("TFrame", background=bg_canvas)
        style.configure("TLabel", background=bg_canvas, font=("Segoe UI", 10))

        # Secondary / standard button style
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 9),
            foreground="#1e293b",
            background="#f8fafc",
            bordercolor="#cbd5e1",
            lightcolor="#f8fafc",
            darkcolor="#f8fafc",
            focuscolor="none",
            borderwidth=1,
        )
        style.map(
            "Secondary.TButton",
            background=[("pressed", "#e2e8f0"), ("active", "#f1f5f9"), ("disabled", "#f1f5f9")],
            foreground=[("disabled", "#94a3b8"), ("!disabled", "#1e293b")],
            bordercolor=[("disabled", "#e2e8f0"), ("!disabled", "#cbd5e1")],
        )

        # Progress bar
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#e2e8f0",
            background="#0284c7",
            bordercolor="#cbd5e1",
            lightcolor="#0284c7",
            darkcolor="#0284c7",
        )

        # Action button 1: Baseline / Setup (Orange)
        style.configure(
            "Baseline.TButton",
            font=("Segoe UI", 9, "bold"),
            foreground="#ffffff",
            background="#ea580c",
            bordercolor="#c2410c",
            lightcolor="#ea580c",
            darkcolor="#ea580c",
            focuscolor="none",
            borderwidth=1,
        )
        style.map(
            "Baseline.TButton",
            background=[("disabled", "#e2e8f0"), ("pressed", "#9a3412"), ("active", "#c2410c")],
            foreground=[("disabled", "#94a3b8"), ("!disabled", "#ffffff")],
            bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#c2410c")],
            lightcolor=[("disabled", "#e2e8f0"), ("!disabled", "#ea580c")],
            darkcolor=[("disabled", "#e2e8f0"), ("!disabled", "#ea580c")],
        )

        # Action button 2: App Only Update (Sky Blue)
        style.configure(
            "AppOnly.TButton",
            font=("Segoe UI", 9, "bold"),
            foreground="#ffffff",
            background="#0284c7",
            bordercolor="#0369a1",
            lightcolor="#0284c7",
            darkcolor="#0284c7",
            focuscolor="none",
            borderwidth=1,
        )
        style.map(
            "AppOnly.TButton",
            background=[("disabled", "#e2e8f0"), ("pressed", "#075985"), ("active", "#0369a1")],
            foreground=[("disabled", "#94a3b8"), ("!disabled", "#ffffff")],
            bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#0369a1")],
            lightcolor=[("disabled", "#e2e8f0"), ("!disabled", "#0284c7")],
            darkcolor=[("disabled", "#e2e8f0"), ("!disabled", "#0284c7")],
        )

        # Action button 3: Full Factory Board Flash (Green)
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 9, "bold"),
            foreground="#ffffff",
            background="#16a34a",
            bordercolor="#15803d",
            lightcolor="#16a34a",
            darkcolor="#16a34a",
            focuscolor="none",
            borderwidth=1,
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#e2e8f0"), ("pressed", "#166534"), ("active", "#15803d")],
            foreground=[("disabled", "#94a3b8"), ("!disabled", "#ffffff")],
            bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#15803d")],
            lightcolor=[("disabled", "#e2e8f0"), ("!disabled", "#16a34a")],
            darkcolor=[("disabled", "#e2e8f0"), ("!disabled", "#16a34a")],
        )

        # Action button 4: Config Only (Purple / Indigo)
        style.configure(
            "ConfigOnly.TButton",
            font=("Segoe UI", 9, "bold"),
            foreground="#ffffff",
            background="#7c3aed",
            bordercolor="#6d28d9",
            lightcolor="#7c3aed",
            darkcolor="#7c3aed",
            focuscolor="none",
            borderwidth=1,
        )
        style.map(
            "ConfigOnly.TButton",
            background=[("disabled", "#e2e8f0"), ("pressed", "#5b21b6"), ("active", "#6d28d9")],
            foreground=[("disabled", "#94a3b8"), ("!disabled", "#ffffff")],
            bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#6d28d9")],
            lightcolor=[("disabled", "#e2e8f0"), ("!disabled", "#7c3aed")],
            darkcolor=[("disabled", "#e2e8f0"), ("!disabled", "#7c3aed")],
        )


        main_frame = tk.Frame(self.root, bg=bg_canvas, padx=14, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ==================== HEADER CARD ====================
        header_card = tk.Frame(
            main_frame,
            bg="#0f172a",
            highlightbackground="#1e293b",
            highlightthickness=1,
            bd=0,
            padx=14,
            pady=10,
        )
        header_card.pack(fill=tk.X, pady=(0, 8))

        # Logo
        self._logo_image = None
        try:
            logo_png = resource_path("assets") / "logo_48.png"
            if logo_png.is_file():
                self._logo_image = tk.PhotoImage(file=str(logo_png))
                logo_label = tk.Label(header_card, image=self._logo_image, bg="#0f172a")
                logo_label.pack(side=tk.LEFT, padx=(0, 12))
        except Exception:
            pass

        title_container = tk.Frame(header_card, bg="#0f172a")
        title_container.pack(side=tk.LEFT, fill=tk.Y)

        title_label = tk.Label(
            title_container,
            text=f"AUBOT Setup CallBox v{__version__}",
            font=("Segoe UI", 15, "bold"),
            fg="#ffffff",
            bg="#0f172a",
        )
        title_label.pack(anchor=tk.W)

        subtitle_label = tk.Label(
            title_container,
            text=f"Development provisioning baseline  •  {manifest_info}",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f172a",
        )
        subtitle_label.pack(anchor=tk.W, pady=(2, 0))

        # Version/update actions on the right. Update is deliberately separate
        # from the ESP32 flashing controller so tool upgrades cannot interfere
        # with an active flash transaction.
        header_actions = tk.Frame(header_card, bg="#0f172a")
        header_actions.pack(side=tk.RIGHT, pady=2)

        badge_label = tk.Label(
            header_actions,
            text="ESP32-S3  •  16MB Flash",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#1e293b",
            padx=10,
            pady=4,
        )
        badge_label.pack(side=tk.TOP, anchor=tk.E)

        self.btn_update = ttk.Button(
            header_actions,
            text=f"Update • v{__version__}",
            command=self._on_check_update_click,
            style="Secondary.TButton",
        )
        self.btn_update.pack(side=tk.TOP, anchor=tk.E, pady=(5, 0))

        # ==================== NOTEBOOK: TABS GIAO DIỆN ====================
        style.configure("TNotebook", background=bg_canvas, tabmargins=[2, 4, 2, 0])
        style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[16, 6])
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#ffffff"), ("!selected", "#e2e8f0")],
            foreground=[("selected", "#0284c7"), ("!selected", "#64748b")],
        )

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        tab_usb = tk.Frame(self.notebook, bg=bg_canvas)
        tab_mqtt = tk.Frame(self.notebook, bg=bg_canvas)

        self.notebook.add(tab_usb, text="  ⚡ Nạp USB & Sản Xuất  ")
        self.notebook.add(tab_mqtt, text="  🌐 Cấu Hình Từ Xa (MQTT)  ")

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

        tk.Label(
            card_conn,
            text="1. KẾT NỐI BOARD ESP32-S3",
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg=card_bg,
        ).pack(anchor=tk.W)

        port_row = tk.Frame(card_conn, bg=card_bg)
        port_row.pack(fill=tk.X, pady=(6, 2))

        tk.Label(
            port_row,
            text="Cổng COM:",
            font=("Segoe UI", 10),
            fg="#334155",
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
        self.btn_refresh.pack(side=tk.LEFT, padx=4)

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
            fg="#64748b",
            bg=card_bg,
        )
        self.port_desc_label.pack(anchor=tk.W, pady=(3, 0))

        self.live_status_label = tk.Label(
            card_conn,
            text="Trạng thái ESP32: Chưa kiểm tra (Nhấn 'Kiểm tra trạng thái (COM)' để đọc qua Serial)",
            font=("Segoe UI", 9, "bold"),
            fg="#64748b",
            bg=card_bg,
        )
        self.live_status_label.pack(anchor=tk.W, pady=(2, 0))


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

        tk.Label(
            card_fw,
            text="2. FIRMWARE ỨNG DỤNG (.BIN)",
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
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
            fg="#64748b",
            bg=card_bg,
            wraplength=800,
            justify=tk.LEFT,
        )
        self.fw_meta_label.pack(anchor=tk.W, pady=(3, 0))

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

        cfg_header_row = tk.Frame(card_cfg, bg=card_bg)
        cfg_header_row.pack(fill=tk.X)

        tk.Label(
            cfg_header_row,
            text="3. CẤU HÌNH THIẾT BỊ (NVS CONFIG - Phân vùng nvs_cfg 0x214000)",
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg=card_bg,
        ).pack(side=tk.LEFT)

        self.btn_reset_defaults = ttk.Button(
            cfg_header_row,
            text="Mặc định Aubot",
            command=self._on_reset_defaults_click,
            style="Secondary.TButton",
        )
        self.btn_reset_defaults.pack(side=tk.RIGHT)

        cfg_grid = tk.Frame(card_cfg, bg=card_bg)
        cfg_grid.pack(fill=tk.X, pady=(6, 2))

        # Dòng 0: Callbox ID, WiFi SSID, WiFi Pass, DHCP
        tk.Label(cfg_grid, text="Callbox ID:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_id_var = tk.StringVar(value="001")
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

        tk.Label(cfg_grid, text="WiFi SSID:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_ssid_var = tk.StringVar(value="")
        self.entry_ssid = ttk.Entry(cfg_grid, textvariable=self.cfg_ssid_var, width=16, font=("Segoe UI", 9))
        self.entry_ssid.grid(row=0, column=3, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="WiFi Pass:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_pass_var = tk.StringVar(value="")
        self.entry_pass = ttk.Entry(cfg_grid, textvariable=self.cfg_pass_var, width=16, font=("Segoe UI", 9), show="*")
        self.entry_pass.grid(row=0, column=5, sticky=tk.W, padx=(0, 10), pady=2)

        self.cfg_dhcp_var = tk.BooleanVar(value=True)
        self.chk_dhcp = ttk.Checkbutton(cfg_grid, text="DHCP", variable=self.cfg_dhcp_var)
        self.chk_dhcp.grid(row=0, column=6, sticky=tk.W, pady=2)

        # Dòng 1: MQTT Broker, Cổng, MQTT User, MQTT Pass
        tk.Label(cfg_grid, text="MQTT Broker:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_broker_var = tk.StringVar(value="")
        self.entry_broker = ttk.Entry(cfg_grid, textvariable=self.cfg_broker_var, width=18, font=("Segoe UI", 9))
        self.entry_broker.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="Port:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=1, column=2, sticky=tk.E, padx=(0, 4), pady=2)
        self.cfg_port_var = tk.StringVar(value="1883")
        self.entry_port = ttk.Entry(cfg_grid, textvariable=self.cfg_port_var, width=6, font=("Segoe UI", 9))
        self.entry_port.grid(row=1, column=3, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="User:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=1, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_user_var = tk.StringVar(value="")
        self.entry_user = ttk.Entry(cfg_grid, textvariable=self.cfg_user_var, width=10, font=("Segoe UI", 9))
        self.entry_user.grid(row=1, column=5, sticky=tk.W, padx=(0, 10), pady=2)

        tk.Label(cfg_grid, text="Pass:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=1, column=6, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_mqtt_pass_var = tk.StringVar(value="")
        self.entry_mqtt_pass = ttk.Entry(cfg_grid, textvariable=self.cfg_mqtt_pass_var, width=10, font=("Segoe UI", 9), show="*")
        self.entry_mqtt_pass.grid(row=1, column=7, sticky=tk.W, pady=2)

        # Dòng 2: Phiên bản vận hành (Điểm Nguồn/Đích bỏ — đội WCS/IT tự điều phối theo ID+Version)
        tk.Label(cfg_grid, text="Phiên bản:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.cfg_ver_var = tk.StringVar(value="2.0")
        self.combo_ver = ttk.Combobox(cfg_grid, textvariable=self.cfg_ver_var, values=["No version", "1.0", "2.0"], width=10, state="readonly", font=("Segoe UI", 9))
        self.combo_ver.grid(row=2, column=1, sticky=tk.W, padx=(0, 10), pady=2)

        # Ghi chú chế độ phiên bản (chỉ đọc)
        self.lbl_ver_note = tk.Label(
            cfg_grid,
            text="",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg=card_bg,
        )
        self.lbl_ver_note.grid(row=2, column=2, columnspan=4, sticky=tk.W, pady=2)

        self.combo_ver.bind("<<ComboboxSelected>>", self._on_version_changed)
        self._on_version_changed()

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

        tk.Label(
            card_action,
            text="4. TIẾN TRÌNH & THAO TÁC NẠP",
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg=card_bg,
        ).pack(anchor=tk.W)

        self.phase_label = tk.Label(
            card_action,
            text=STATE_COPY[ProvisionState.READY],
            font=("Segoe UI", 11, "bold"),
            fg="#0f172a",
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
            fg="#16a34a",
            bg=card_bg,
            wraplength=800,
            justify=tk.LEFT,
        )
        self.banner_label.pack(anchor=tk.W)

        self.result_details_label = tk.Label(
            card_action,
            text="",
            font=("Segoe UI", 9),
            fg="#334155",
            bg=card_bg,
            wraplength=800,
            justify=tk.LEFT,
        )
        self.result_details_label.pack(anchor=tk.W, pady=(1, 4))

        self.action_hint_label = tk.Label(
            card_action,
            text="Vui lòng kết nối cổng COM để thao tác.",
            font=("Segoe UI", 9),
            fg="#64748b",
            bg=card_bg,
        )
        self.action_hint_label.pack(anchor=tk.W, pady=(2, 6))

        # 4 Action Buttons in a clean, equal-width row
        buttons_row = tk.Frame(card_action, bg=card_bg)
        buttons_row.pack(fill=tk.X, pady=(2, 4))

        self.btn_flash_config = ttk.Button(
            buttons_row,
            text="NẠP CẤU HÌNH\n(Chỉ nạp NVS 0x214000, ~2s)",
            style="ConfigOnly.TButton",
            command=self._on_flash_config_click,
        )
        self.btn_flash_config.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3), ipady=6)

        self.btn_flash_full = ttk.Button(
            buttons_row,
            text="NẠP TOÀN BỘ BOARD\n(Xóa Flash + Boot + App + NVS)",
            style="Primary.TButton",
            command=self._on_flash_full_click,
        )
        self.btn_flash_full.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=3, ipady=6)

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


        # ==================== CARD 4: NHẬT KÝ KỸ THUẬT (CONSOLE) ====================
        log_card = tk.Frame(
            tab_usb,
            bg=bg_canvas,
            bd=0,
            pady=4,
        )
        log_card.pack(fill=tk.BOTH, expand=True)

        log_header = tk.Frame(log_card, bg=bg_canvas)
        log_header.pack(fill=tk.X, pady=(2, 4))

        tk.Label(
            log_header,
            text="NHẬT KÝ KỸ THUẬT (LOG CONSOLE)",
            font=("Segoe UI", 9, "bold"),
            fg="#475569",
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
            bg="#0f172a",
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
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            relief="flat",
            padx=8,
            pady=6,
            yscrollcommand=log_scroll.set,
            wrap=tk.WORD,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

        self._setup_mqtt_tab(tab_mqtt, card_bg, border_color, bg_canvas)

        self._update_flash_button()

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

        self._on_port_selected(None)

    def _on_port_selected(self, event=None) -> None:
        device = self.port_combo.get()
        match = next((p for p in self.ports if p.device == device), None)
        if match:
            vid_pid = f" (VID:PID = {hex(match.vid or 0)}:{hex(match.pid or 0)})" if match.vid else ""
            self.port_desc_label.config(
                text=f"{match.description}{vid_pid}",
                fg="#0369a1",
            )
        else:
            self.port_desc_label.config(
                text="Chưa chọn hoặc không tìm thấy cổng COM phù hợp",
                fg="#b91c1c",
            )
        self._update_flash_button()

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
                        fg="#16a34a",
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
                fg="#16a34a",
            )
        except ImageValidationError as error:
            self.app_info = None
            self.fw_meta_label.config(
                text=f"LỖI: {error}",
                fg="#dc2626",
            )
        except Exception as error:
            self.app_info = None
            self.fw_meta_label.config(
                text=f"Lỗi không xác định: {error}",
                fg="#dc2626",
            )
        self._update_flash_button()


    def _update_flash_button(self) -> None:
        port = self.port_combo.get().strip()
        valid = self.app_info is not None
        busy = self.controller.busy

        config_ready = can_flash_config(port, busy)
        baseline_ready = can_flash_baseline(port, busy)
        app_ready = can_flash(port, valid, busy)

        self.btn_flash_config["state"] = tk.NORMAL if config_ready else tk.DISABLED
        self.btn_flash_baseline["state"] = tk.NORMAL if baseline_ready else tk.DISABLED
        self.btn_flash_app["state"] = tk.NORMAL if app_ready else tk.DISABLED
        self.btn_flash_full["state"] = tk.NORMAL if app_ready else tk.DISABLED

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
                text="💡 Cổng COM đã sẵn sàng. Có thể nạp Cấu hình NVS hoặc nạp Bootloader / Setup.",
                fg="#7c3aed",
            )
        else:
            self.action_hint_label.config(
                text="✅ Đã kết nối board và nạp file firmware hợp lệ. Hãy chọn chế độ nạp mong muốn:",
                fg="#16a34a",
            )

    def _set_inputs_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.port_combo["state"] = "readonly" if enabled else tk.DISABLED
        self.btn_refresh["state"] = state
        self.btn_check_status["state"] = state
        self.btn_read_config["state"] = state
        self.btn_browse["state"] = state
        self.btn_reset_defaults["state"] = state
        if hasattr(self, "btn_update"):
            self.btn_update["state"] = state if not self.update_busy else tk.DISABLED

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
                self.lbl_ver_note.config(text="Chế độ: 2 nút", fg="#0369a1")

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

    def _apply_factory_profile(self, config: DeviceConfig) -> None:
        """Fill GUI fields from the private local factory profile, if present."""
        self.cfg_id_var.set(config.callbox_id)
        self.cfg_ssid_var.set(config.wifi_ssid)
        self.cfg_pass_var.set(config.wifi_pass)
        self.cfg_dhcp_var.set(config.wifi_dhcp)
        self.cfg_broker_var.set(config.mqtt_broker)
        self.cfg_port_var.set(str(config.mqtt_port))
        self.cfg_user_var.set(config.mqtt_user)
        self.cfg_mqtt_pass_var.set(config.mqtt_pass)
        self.cfg_ver_var.set(config.operating_version)
        self._on_version_changed()
        if hasattr(self, "rc_broker_var"):
            self.rc_broker_var.set(config.mqtt_broker)
        if hasattr(self, "rc_port_var"):
            self.rc_port_var.set(str(config.mqtt_port))
        if hasattr(self, "rc_user_var"):
            self.rc_user_var.set(config.mqtt_user)
        if hasattr(self, "rc_pass_var"):
            self.rc_pass_var.set(config.mqtt_pass)

    def _on_reset_defaults_click(self) -> None:
        """Restore the local private factory profile, or public-safe blank defaults."""
        self._apply_factory_profile(self.factory_profile)
        self._append_log("Đã khôi phục profile nhà máy cục bộ (hoặc mặc định an toàn nếu chưa có profile).")

    def _on_check_status_click(self) -> None:
        """Gửi lệnh kiểm tra trạng thái ESP32 qua Serial trong luồng nền."""
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showwarning(
                "Chưa chọn cổng",
                "Vui lòng chọn cổng COM trước khi kiểm tra trạng thái.",
                parent=self.root,
            )
            return

        if self.controller.busy:
            return

        self.live_status_label.config(text="Đang đọc trạng thái từ cổng COM...", fg="#2563eb")
        self._append_log(f"--- Đang gửi yêu cầu kiểm tra trạng thái tới {port} ---")

        def worker():
            try:
                status = query_device_status(port)
                def update_ui():
                    sta_icon = "🟢" if status.get("sta") else "⚪"
                    mqtt_icon = "🟢" if status.get("mqtt") else "⚪"
                    sta_txt = f"{sta_icon} WiFi STA: {'Đã kết nối (' + status.get('ssid','') + ', IP: ' + status.get('ip','') + ')' if status.get('sta') else 'Chưa kết nối'}"
                    mqtt_txt = f"{mqtt_icon} MQTT: {'Đã kết nối' if status.get('mqtt') else 'Chưa kết nối'}"
                    client_txt = f"ID: {status.get('client_id', '')}"
                    self.live_status_label.config(
                        text=f"{sta_txt} | {mqtt_txt} | {client_txt}",
                        fg="#15803d" if status.get("sta") else "#64748b",
                    )
                    self._append_log(f"Trạng thái nhận được: STA={status.get('sta')}, IP={status.get('ip')}, RSSI={status.get('rssi')}, MQTT={status.get('mqtt')}, ClientID={status.get('client_id')}")
                self.root.after(0, update_ui)
            except Exception as e:
                def on_err():
                    self.live_status_label.config(text=f"Lỗi đọc trạng thái: {e}", fg="#dc2626")
                    self._append_log(f"Lỗi kiểm tra trạng thái: {e}")
                self.root.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()

    def _on_read_config_click(self) -> None:
        """Gửi lệnh đọc cấu hình hiện tại từ NVS của ESP32 qua Serial và điền vào form."""
        port = self.port_combo.get().strip()
        if not port:
            messagebox.showwarning(
                "Chưa chọn cổng",
                "Vui lòng chọn cổng COM trước khi đọc cấu hình.",
                parent=self.root,
            )
            return

        if self.controller.busy:
            return

        self.live_status_label.config(text="Đang đọc cấu hình từ ESP32...", fg="#2563eb")
        self._append_log(f"--- Đang đọc cấu hình từ thiết bị trên {port} ---")

        def worker():
            try:
                cfg = query_device_config(port)
                def update_ui():
                    self.cfg_id_var.set(cfg.callbox_id)
                    self.cfg_ssid_var.set(cfg.wifi_ssid)
                    self.cfg_pass_var.set(cfg.wifi_pass)
                    self.cfg_dhcp_var.set(cfg.wifi_dhcp)
                    self.cfg_broker_var.set(cfg.mqtt_broker)
                    self.cfg_port_var.set(str(cfg.mqtt_port))
                    self.cfg_user_var.set(cfg.mqtt_user)
                    self.cfg_mqtt_pass_var.set(cfg.mqtt_pass)
                    self.cfg_ver_var.set(cfg.operating_version if cfg.operating_version in ["No version", "1.0", "2.0"] else "No version")
                    # Không hiển thị listpoints — WCS/IT tự điều phối
                    self._on_version_changed()
                    self.live_status_label.config(text="Đã đọc và đồng bộ cấu hình từ chip thành công.", fg="#16a34a")
                    self._append_log(f"Cấu hình nhận được: Callbox ID={cfg.callbox_id}, SSID={cfg.wifi_ssid}, Broker={cfg.mqtt_broker}, Version={cfg.operating_version}")
                self.root.after(0, update_ui)
            except Exception as e:
                def on_err():
                    self.live_status_label.config(text=f"Lỗi đọc cấu hình: {e}", fg="#dc2626")
                    self._append_log(f"Lỗi đọc cấu hình từ chip: {e}")
                self.root.after(0, on_err)

        threading.Thread(target=worker, daemon=True).start()

    def _auto_query_status_after_flash(self) -> None:
        """Tự động kiểm tra lại trạng thái board sau khi nạp xong."""
        if not self.controller.busy:
            self._on_check_status_click()

    def _on_flash_config_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash_config(port, self.controller.busy):
            return

        cfg = self._get_device_config_from_ui()
        confirm = messagebox.askyesno(
            "Xác nhận NẠP CẤU HÌNH",
            f"Nạp cấu hình vào phân vùng NVS (0x214000) cho thiết bị trên cổng {port}?\n\n"
            f"• Cổng COM: {port}\n"
            f"• Callbox ID: {cfg.callbox_id}\n"
            f"• Phiên bản xuất xưởng: Version {cfg.operating_version}\n"
            f"• Wi-Fi SSID: {cfg.wifi_ssid}\n"
            f"• MQTT Broker: {cfg.mqtt_broker}:{cfg.mqtt_port}\n\n"
            "Chỉ nạp phân vùng cấu hình NVS trong ~2 giây (không nạp lại firmware/bootloader).\n"
            "Bạn có muốn tiếp tục?",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.CONFIG_ONLY)

    def _on_flash_baseline_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash_baseline(port, self.controller.busy):
            return

        confirm = messagebox.askyesno(
            "Xác nhận NẠP BOOTLOADER / SETUP",
            f"Nạp cấu hình baseline (Bootloader, Bảng phân vùng 16MB, OTA data) cho thiết bị trên cổng {port}?\n\n"
            "• Khởi tạo phân vùng và bootloader tiêu chuẩn cho board mới\n"
            "• Thao tác này KHÔNG CẦN file firmware ứng dụng\n\n"
            "Bạn có muốn tiếp tục?",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.BASELINE_ONLY)

    def _on_flash_full_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash(port, self.app_info is not None, self.controller.busy):
            return

        cfg = self._get_device_config_from_ui()
        confirm = messagebox.askyesno(
            "Xác nhận NẠP TOÀN BỘ BOARD",
            f"Bạn có chắc muốn nạp mới toàn bộ board trên cổng {port}?\n\n"
            "THÔNG SỐ XUẤT XƯỞNG:\n"
            f"• Cổng COM: {port}\n"
            f"• Firmware ứng dụng: {self.app_info.path.name} (v{self.app_info.version})\n"
            f"• Callbox ID: {cfg.callbox_id}\n"
            f"• Phiên bản xuất xưởng: Version {cfg.operating_version}\n"
            f"• Wi-Fi SSID: {cfg.wifi_ssid}\n"
            f"• MQTT Broker: {cfg.mqtt_broker}:{cfg.mqtt_port}\n\n"
            "TIẾN TRÌNH SẼ THỰC HIỆN:\n"
            "1. XÓA SẠCH toàn bộ bộ nhớ Flash của chip ESP32-S3\n"
            "2. Nạp Bootloader tiêu chuẩn và Bảng phân vùng 16MB\n"
            "3. Nạp Firmware ứng dụng hợp lệ\n"
            "4. Nạp phân vùng Cấu hình NVS vừa chỉ định\n\n"
            "Thao tác không thể hoàn tác. Bạn có chắc chắn tiếp tục?",
            icon="warning",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.FULL)

    def _on_flash_app_click(self) -> None:
        port = self.port_combo.get().strip()
        if not can_flash(port, self.app_info is not None, self.controller.busy):
            return

        confirm = messagebox.askyesno(
            "Xác nhận CẬP NHẬT ỨNG DỤNG",
            f"Cập nhật firmware ứng dụng cho board trên cổng {port}?\n\n"
            f"• Dự án: {self.app_info.project} | Phiên bản: {self.app_info.version}\n"
            "• Ghi đè vào phân vùng 0x10000 (Factory)\n"
            "• Reset trạng thái OTA về Factory\n"
            "• GIỮ NGUYÊN cấu hình WiFi và dữ liệu NVS hiện có\n\n"
            "Bạn có muốn tiếp tục?",
            icon="question",
            parent=self.root,
        )
        if not confirm:
            return

        self._start_flashing(port, ProvisionMode.APP_ONLY)

    def _start_flashing(self, port: str, mode: ProvisionMode) -> None:
        self._set_inputs_enabled(False)
        self.banner_label.config(text="")
        self.result_details_label.config(text="")
        self.progress_bar["value"] = 0

        dev_config = None
        if mode == ProvisionMode.FULL:
            mode_str = f"NẠP TOÀN BỘ BOARD ({self.app_info.path.name})"
            dev_config = self._get_device_config_from_ui()
        elif mode == ProvisionMode.CONFIG_ONLY:
            mode_str = "NẠP CẤU HÌNH NVS (0x214000)"
            dev_config = self._get_device_config_from_ui()
        elif mode == ProvisionMode.APP_ONLY:
            mode_str = f"CẬP NHẬT ỨNG DỤNG ({self.app_info.path.name})"
        else:
            mode_str = "NẠP BOOTLOADER / SETUP"
        self._append_log(f"--- Bắt đầu {mode_str} vào {port} ---")

        app_path = self.app_info.path if self.app_info else None
        self.controller.start(
            port=port,
            application=app_path,
            emit=self.event_queue.put,
            mode=mode,
            config=dev_config,
        )

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self._drain_events)

    def _handle_event(self, event: ProvisionEvent) -> None:
        if event.technical:
            self._append_log(event.technical)

        self.phase_label.config(text=STATE_COPY.get(event.state, event.message))
        self.progress_bar["value"] = event.progress

        if event.state == ProvisionState.SUCCEEDED:
            self._set_inputs_enabled(True)
            res = event.result
            mac_str = res.mac.upper() if res and res.mac else "N/A"
            time_str = f"{res.elapsed_seconds}s" if res else ""
            version_str = res.version if res else ""

            if res and res.mode == ProvisionMode.FULL:
                banner_text = "NẠP TOÀN BỘ BOARD THÀNH CÔNG"
                detail_note = (
                    f"Đã nạp sạch board và ghi cấu hình NVS (ID: {self.cfg_id_var.get().strip()}). "
                    "Board đang khởi động lại."
                )
                self.root.after(4000, self._auto_query_status_after_flash)
            elif res and res.mode == ProvisionMode.CONFIG_ONLY:
                banner_text = "NẠP CẤU HÌNH THÀNH CÔNG"
                detail_note = (
                    f"Đã nạp cấu hình NVS (ID: {self.cfg_id_var.get().strip()}) vào 0x214000. "
                    "Board đang khởi động lại."
                )
                self.root.after(3500, self._auto_query_status_after_flash)
            elif res and res.mode == ProvisionMode.APP_ONLY:
                banner_text = "CẬP NHẬT APP THÀNH CÔNG"
                detail_note = "Toàn bộ cấu hình WiFi và dữ liệu NVS được giữ nguyên vẹn."
                self.root.after(3500, self._auto_query_status_after_flash)
            else:
                banner_text = "NẠP BOOTLOADER / SETUP THÀNH CÔNG"
                detail_note = (
                    "Bootloader và bảng phân vùng đã sẵn sàng. "
                    "Bạn có thể nạp tiếp firmware hoặc cấu hình bất cứ lúc nào."
                )

            self.banner_label.config(
                text=banner_text,
                fg="#16a34a",
            )
            self.result_details_label.config(
                text=f"MAC: {mac_str} | Phiên bản: {version_str} | Thời gian: {time_str}\n{detail_note}",
                fg="#15803d",
            )
            self._append_log(f"--- {banner_text} (MAC: {mac_str}, Version: {version_str}) ---")
            self._refresh_ports()

        elif event.state == ProvisionState.FAILED:
            self._set_inputs_enabled(True)
            self.banner_label.config(
                text="THAO TÁC THẤT BẠI",
                fg="#dc2626",
            )
            self.result_details_label.config(
                text=f"Nguyên nhân: {event.message}",
                fg="#b91c1c",
            )
            self._append_log(f"--- THẤT BẠI: {event.message} ---")


    def _setup_mqtt_tab(self, parent: tk.Frame, card_bg: str, border_color: str, bg_canvas: str) -> None:
        """Xây dựng giao diện MQTT; remote operations are isolated from legacy flows."""
        self.rc_target_id_var = tk.StringVar(value="001")
        self.rc_remote_test_enable_var = tk.BooleanVar(value=False)
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
            fg="#0f172a",
            bg=card_bg,
        ).pack(side=tk.LEFT)

        self.lbl_rc_broker_status = tk.Label(
            header_b,
            text="● Chưa kết nối",
            font=("Segoe UI", 9, "bold"),
            fg="#64748b",
            bg=card_bg,
        )
        self.lbl_rc_broker_status.pack(side=tk.RIGHT)

        b_grid = tk.Frame(card_broker, bg=card_bg)
        b_grid.pack(fill=tk.X, pady=(6, 2))

        # Row 0: Broker Host, Port, User, Pass
        tk.Label(b_grid, text="Broker:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_broker_var = tk.StringVar(value="")
        self.entry_rc_broker = ttk.Entry(b_grid, textvariable=self.rc_broker_var, width=18, font=("Segoe UI", 9))
        self.entry_rc_broker.grid(row=0, column=1, sticky=tk.W, padx=(0, 8), pady=2)

        tk.Label(b_grid, text="Cổng:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_port_var = tk.StringVar(value="1883")
        self.entry_rc_port = ttk.Entry(b_grid, textvariable=self.rc_port_var, width=6, font=("Segoe UI", 9))
        self.entry_rc_port.grid(row=0, column=3, sticky=tk.W, padx=(0, 8), pady=2)

        tk.Label(b_grid, text="Tài khoản:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_user_var = tk.StringVar(value="")
        self.entry_rc_user = ttk.Entry(b_grid, textvariable=self.rc_user_var, width=10, font=("Segoe UI", 9))
        self.entry_rc_user.grid(row=0, column=5, sticky=tk.W, padx=(0, 8), pady=2)

        tk.Label(b_grid, text="Mật khẩu:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=6, sticky=tk.W, padx=(0, 4), pady=2)
        self.rc_pass_var = tk.StringVar(value="")
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

        # ==================== CARD M2: GIÁM SÁT & ĐIỀU KHIỂN TỪ XA ====================
        card_remote = tk.Frame(
            parent, bg=card_bg, highlightbackground=border_color,
            highlightthickness=1, bd=0, padx=12, pady=8,
        )
        card_remote.pack(fill=tk.X, pady=4)

        remote_head = tk.Frame(card_remote, bg=card_bg)
        remote_head.pack(fill=tk.X)
        tk.Label(
            remote_head, text="2. GIÁM SÁT & ĐIỀU KHIỂN CALLBOX",
            font=("Segoe UI", 9, "bold"), fg="#0f172a", bg=card_bg,
        ).pack(side=tk.LEFT)
        self.lbl_rc_device_status = tk.Label(
            remote_head, text="● Chưa theo dõi", font=("Segoe UI", 9, "bold"),
            fg="#64748b", bg=card_bg,
        )
        self.lbl_rc_device_status.pack(side=tk.RIGHT)

        target_row = tk.Frame(card_remote, bg=card_bg)
        target_row.pack(fill=tk.X, pady=(6, 4))
        tk.Label(target_row, text="Callbox ID:", font=("Segoe UI", 9, "bold"),
                 fg="#334155", bg=card_bg).pack(side=tk.LEFT)
        self.entry_rc_monitor_id = ttk.Entry(
            target_row, textvariable=self.rc_target_id_var, width=12,
            font=("Segoe UI", 9, "bold"),
        )
        self.entry_rc_monitor_id.pack(side=tk.LEFT, padx=(6, 6))
        ttk.Button(
            target_row, text="Theo dõi", style="Secondary.TButton",
            command=self._on_mqtt_watch_click,
        ).pack(side=tk.LEFT)
        self.lbl_rc_device_meta = tk.Label(
            target_row, text="Comm: —   Version: —   FW: —", font=("Segoe UI", 9),
            fg="#475569", bg=card_bg,
        )
        self.lbl_rc_device_meta.pack(side=tk.LEFT, padx=(14, 0))
        self.entry_rc_monitor_id.bind("<Return>", self._on_mqtt_watch_click)

        state_row = tk.Frame(card_remote, bg=card_bg)
        state_row.pack(fill=tk.X, pady=(3, 4))
        self.lbl_rc_task1 = tk.Label(state_row, text="Task 1: —", width=24, anchor="w",
                                     font=("Segoe UI", 9, "bold"), fg="#334155", bg=card_bg)
        self.lbl_rc_task1.pack(side=tk.LEFT)
        self.lbl_rc_task2 = tk.Label(state_row, text="Task 2: —", width=24, anchor="w",
                                     font=("Segoe UI", 9, "bold"), fg="#334155", bg=card_bg)
        self.lbl_rc_task2.pack(side=tk.LEFT)
        self.lbl_rc_cancel_state = tk.Label(state_row, text="Cancel: —", anchor="w",
                                             font=("Segoe UI", 9), fg="#334155", bg=card_bg)
        self.lbl_rc_cancel_state.pack(side=tk.LEFT)

        control_row = tk.Frame(card_remote, bg=card_bg)
        control_row.pack(fill=tk.X, pady=(4, 4))
        tk.Label(control_row, text="Điều khiển:", font=("Segoe UI", 9, "bold"),
                 fg="#334155", bg=card_bg).pack(side=tk.LEFT, padx=(0, 6))
        self.chk_rc_remote_test = ttk.Checkbutton(
            control_row,
            text="DEBUG/TEST",
            variable=self.rc_remote_test_enable_var,
            command=self._on_remote_test_toggle,
        )
        self.chk_rc_remote_test.pack(side=tk.LEFT, padx=(0, 8))
        self.btn_rc_remote_1 = ttk.Button(
            control_row, text="NÚT 1 / TASK 1", style="ConfigOnly.TButton",
            command=lambda: self._on_mqtt_remote_button_click(1), state=tk.DISABLED,
        )
        self.btn_rc_remote_1.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_rc_remote_2 = ttk.Button(
            control_row, text="NÚT 2 / TASK 2", style="ConfigOnly.TButton",
            command=lambda: self._on_mqtt_remote_button_click(2), state=tk.DISABLED,
        )
        self.btn_rc_remote_2.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_rc_remote_cancel = ttk.Button(
            control_row, text="HỦY", style="Secondary.TButton",
            command=lambda: self._on_mqtt_remote_button_click(3), state=tk.DISABLED,
        )
        self.btn_rc_remote_cancel.pack(side=tk.LEFT, padx=(0, 10))
        self.lbl_rc_remote_ack = tk.Label(
            control_row, text="Remote: chờ telemetry /io", font=("Segoe UI", 9, "bold"),
            fg="#64748b", bg=card_bg,
        )
        self.lbl_rc_remote_ack.pack(side=tk.LEFT)

        io_row = tk.Frame(card_remote, bg=card_bg)
        io_row.pack(fill=tk.X, pady=(4, 0))
        tk.Label(io_row, text="LED nút:", font=("Segoe UI", 9, "bold"), fg="#334155", bg=card_bg).pack(side=tk.LEFT)
        self.lbl_rc_led1 = tk.Label(io_row, text="● LED1", fg="#94a3b8", bg=card_bg, font=("Segoe UI", 9, "bold"))
        self.lbl_rc_led1.pack(side=tk.LEFT, padx=(6, 8))
        self.lbl_rc_led2 = tk.Label(io_row, text="● LED2", fg="#94a3b8", bg=card_bg, font=("Segoe UI", 9, "bold"))
        self.lbl_rc_led2.pack(side=tk.LEFT, padx=(0, 8))
        self.lbl_rc_led_cancel = tk.Label(io_row, text="● HỦY", fg="#94a3b8", bg=card_bg, font=("Segoe UI", 9, "bold"))
        self.lbl_rc_led_cancel.pack(side=tk.LEFT, padx=(0, 16))
        tk.Label(io_row, text="Tháp:", font=("Segoe UI", 9, "bold"), fg="#334155", bg=card_bg).pack(side=tk.LEFT)
        self.lbl_rc_tower_red = tk.Label(io_row, text="● ĐỎ", fg="#94a3b8", bg=card_bg, font=("Segoe UI", 9, "bold"))
        self.lbl_rc_tower_red.pack(side=tk.LEFT, padx=(6, 8))
        self.lbl_rc_tower_yellow = tk.Label(io_row, text="● VÀNG", fg="#94a3b8", bg=card_bg, font=("Segoe UI", 9, "bold"))
        self.lbl_rc_tower_yellow.pack(side=tk.LEFT, padx=(0, 8))
        self.lbl_rc_tower_green = tk.Label(io_row, text="● XANH", fg="#94a3b8", bg=card_bg, font=("Segoe UI", 9, "bold"))
        self.lbl_rc_tower_green.pack(side=tk.LEFT)

        # ==================== CARD M3: THAM SỐ CẤU HÌNH TỪ XA ====================
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

        header_p = tk.Frame(card_params, bg=card_bg)
        header_p.pack(fill=tk.X)
        tk.Label(
            header_p,
            text="3. THIẾT LẬP THAM SỐ GỬI ĐẾN CALLBOX (PARTIAL UPDATE)",
            font=("Segoe UI", 9, "bold"),
            fg="#0f172a",
            bg=card_bg,
        ).pack(side=tk.LEFT)

        tk.Label(
            header_p,
            text="Chỉ gửi các trường có nhập giá trị · Trường để trống sẽ giữ nguyên trên chip",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg=card_bg,
        ).pack(side=tk.RIGHT)

        p_grid = tk.Frame(card_params, bg=card_bg)
        p_grid.pack(fill=tk.X, pady=(6, 2))

        # Row 0: Target Callbox ID & Version
        tk.Label(p_grid, text="Callbox ID mục tiêu (*):", font=("Segoe UI", 9, "bold"), fg="#b91c1c", bg=card_bg).grid(row=0, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.entry_rc_target_id = ttk.Entry(p_grid, textvariable=self.rc_target_id_var, width=12, font=("Segoe UI", 9, "bold"))
        self.entry_rc_target_id.grid(row=0, column=1, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Phiên bản vận hành:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=2, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_ver_var = tk.StringVar(value="(Giữ nguyên)")
        self.combo_rc_ver = ttk.Combobox(p_grid, textvariable=self.rc_ver_var, values=["(Giữ nguyên)", "2.0", "1.0", "No version"], width=13, state="readonly", font=("Segoe UI", 9))
        self.combo_rc_ver.grid(row=0, column=3, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Đổi Callbox ID mới:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=0, column=4, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_new_id_var = tk.StringVar(value="")
        self.entry_rc_new_id = ttk.Entry(p_grid, textvariable=self.rc_new_id_var, width=12, font=("Segoe UI", 9))
        self.entry_rc_new_id.grid(row=0, column=5, sticky=tk.W, padx=(0, 4), pady=3)

        # Row 1: New WiFi SSID & Pass
        tk.Label(p_grid, text="Wi-Fi SSID mới:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=1, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_wifi_ssid_var = tk.StringVar(value="")
        self.entry_rc_wifi_ssid = ttk.Entry(p_grid, textvariable=self.rc_wifi_ssid_var, width=16, font=("Segoe UI", 9))
        self.entry_rc_wifi_ssid.grid(row=1, column=1, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Mật khẩu Wi-Fi mới:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=1, column=2, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_wifi_pass_var = tk.StringVar(value="")
        self.entry_rc_wifi_pass = ttk.Entry(p_grid, textvariable=self.rc_wifi_pass_var, width=16, font=("Segoe UI", 9), show="*")
        self.entry_rc_wifi_pass.grid(row=1, column=3, sticky=tk.W, padx=(0, 14), pady=3)

        self.rc_reboot_var = tk.BooleanVar(value=True)
        self.chk_rc_reboot = tk.Checkbutton(
            p_grid,
            text="Khởi động lại sau khi lưu (Reboot)",
            variable=self.rc_reboot_var,
            font=("Segoe UI", 9),
            fg="#0369a1",
            bg=card_bg,
            activebackground=card_bg,
        )
        self.chk_rc_reboot.grid(row=1, column=4, columnspan=2, sticky=tk.W, pady=3)

        # Row 2: New MQTT Broker & Port
        tk.Label(p_grid, text="MQTT Broker mới:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=2, column=0, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_new_broker_var = tk.StringVar(value="")
        self.entry_rc_new_broker = ttk.Entry(p_grid, textvariable=self.rc_new_broker_var, width=16, font=("Segoe UI", 9))
        self.entry_rc_new_broker.grid(row=2, column=1, sticky=tk.W, padx=(0, 14), pady=3)

        tk.Label(p_grid, text="Cổng MQTT mới:", font=("Segoe UI", 9), fg="#334155", bg=card_bg).grid(row=2, column=2, sticky=tk.W, padx=(0, 4), pady=3)
        self.rc_new_port_var = tk.StringVar(value="")
        self.entry_rc_new_port = ttk.Entry(p_grid, textvariable=self.rc_new_port_var, width=8, font=("Segoe UI", 9))
        self.entry_rc_new_port.grid(row=2, column=3, sticky=tk.W, padx=(0, 14), pady=3)

        # Action send button row
        action_row = tk.Frame(card_params, bg=card_bg)
        action_row.pack(fill=tk.X, pady=(8, 2))

        self.btn_rc_send = ttk.Button(
            action_row,
            text="🚀 GỬI CẤU HÌNH QUA MQTT (callbox/<ID>/cmd)",
            style="ConfigOnly.TButton",
            command=self._on_mqtt_send_config_click,
        )
        self.btn_rc_send.pack(side=tk.LEFT, ipady=6, ipadx=14)

        self.lbl_rc_ack_status = tk.Label(
            action_row,
            text="Trạng thái lệnh: Sẵn sàng gửi",
            font=("Segoe UI", 9, "bold"),
            fg="#64748b",
            bg=card_bg,
        )
        self.lbl_rc_ack_status.pack(side=tk.LEFT, padx=(14, 0))

        # ==================== CARD M4: NHẬT KÝ MQTT CONSOLE ====================
        card_log = tk.Frame(parent, bg=bg_canvas, bd=0, pady=4)
        card_log.pack(fill=tk.BOTH, expand=True)

        m_log_header = tk.Frame(card_log, bg=bg_canvas)
        m_log_header.pack(fill=tk.X, pady=(2, 4))

        tk.Label(
            m_log_header,
            text="NHẬT KÝ BẢN TIN MQTT & PHẢN HỒI ACK TỪ CALLBOX",
            font=("Segoe UI", 9, "bold"),
            fg="#475569",
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
            bg="#0f172a",
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
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            relief="flat",
            padx=8,
            pady=6,
            yscrollcommand=m_log_scroll.set,
            wrap=tk.WORD,
        )
        self.rc_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        m_log_scroll.config(command=self.rc_log_text.yview)
        self.root.after(1000, self._mqtt_monitor_watchdog)

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

        self.lbl_rc_broker_status.config(text="● Đang kết nối...", fg="#d97706")
        self._mqtt_log_append(f"--- Đang kết nối đến broker {cfg.host}:{cfg.port} ---")

        if not self.mqtt_client:
            self.mqtt_client = CallboxRemoteConfigClient()
            self.mqtt_client.on_connect = lambda ok, msg: self.root.after(0, self._on_mqtt_connect_result, ok, msg)
            self.mqtt_client.on_ack = lambda cid, ok: self.root.after(0, self._on_mqtt_ack_result, cid, ok)
            self.mqtt_client.on_status = lambda cid, data: self.root.after(0, self._on_mqtt_status, cid, data)
            self.mqtt_client.on_io = lambda cid, data: self.root.after(0, self._on_mqtt_io, cid, data)
            self.mqtt_client.on_control_ack = lambda cid, data: self.root.after(0, self._on_mqtt_control_ack, cid, data)
            self.mqtt_client.on_log = lambda m: self.root.after(0, self._mqtt_log_append, m)

        self.mqtt_client.connect(cfg)

    def _on_mqtt_connect_result(self, ok: bool, msg: str) -> None:
        self.mqtt_is_connected = ok
        if ok:
            self.lbl_rc_broker_status.config(text=f"● Đã kết nối: {self.rc_broker_var.get().strip()}", fg="#16a34a")
            self.btn_rc_connect.config(state=tk.DISABLED)
            self.btn_rc_disconnect.config(state=tk.NORMAL)
            self._mqtt_log_append("KẾT NỐI THÀNH CÔNG: cấu hình cũ giữ nguyên; remote monitor chạy độc lập.")
            self._on_mqtt_watch_click()
        else:
            self.lbl_rc_broker_status.config(text=f"● Lỗi kết nối ({msg})", fg="#dc2626")
            self.btn_rc_connect.config(state=tk.NORMAL)
            self.btn_rc_disconnect.config(state=tk.DISABLED)

    def _on_mqtt_disconnect_click(self) -> None:
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        self.mqtt_is_connected = False
        self.lbl_rc_broker_status.config(text="● Đã ngắt kết nối", fg="#64748b")
        self.btn_rc_connect.config(state=tk.NORMAL)
        self.btn_rc_disconnect.config(state=tk.DISABLED)
        self._mqtt_log_append("Đã ngắt kết nối khỏi MQTT Broker.")
        self._mqtt_mark_device_offline("Đã ngắt broker")

    def _set_remote_indicator(self, label: tk.Label, on: bool, color: str) -> None:
        label.config(fg=color if on else "#94a3b8")

    def _mqtt_remote_controls_refresh(self) -> None:
        io_fresh = self.mqtt_last_io_monotonic > 0 and (time.monotonic() - self.mqtt_last_io_monotonic) < 3.5
        transport_ready = (
            self.mqtt_is_connected
            and self.mqtt_device_online
            and self.mqtt_device_comm == "ready"
            and io_fresh
        )
        test_enabled = bool(self.rc_remote_test_enable_var.get())
        no_inflight = self.mqtt_remote_pending_request_id is None
        enabled = transport_ready and test_enabled and no_inflight
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (self.btn_rc_remote_1, self.btn_rc_remote_2, self.btn_rc_remote_cancel):
            button.config(state=state)

        if self.mqtt_remote_pending_request_id is not None:
            self.lbl_rc_remote_ack.config(
                text=f"DEBUG/TEST: chờ ACK #{self.mqtt_remote_pending_request_id}", fg="#d97706"
            )
        elif not test_enabled:
            self.lbl_rc_remote_ack.config(
                text="DEBUG/TEST: khóa - nút vật lý là điều khiển chính", fg="#64748b"
            )
        elif not io_fresh and self.mqtt_device_online:
            self.lbl_rc_remote_ack.config(text="DEBUG/TEST: cần firmware v1.5+ (/io)", fg="#d97706")
        elif not transport_ready:
            self.lbl_rc_remote_ack.config(text="DEBUG/TEST: chờ CallBox READY", fg="#d97706")

    def _on_remote_test_toggle(self) -> None:
        if not self.rc_remote_test_enable_var.get():
            self.mqtt_remote_pending_request_id = None
            self.mqtt_remote_pending_since = 0.0
        self._mqtt_remote_controls_refresh()

    def _mqtt_mark_device_offline(self, reason: str) -> None:
        self.mqtt_device_online = False
        self.mqtt_device_comm = "offline"
        self.lbl_rc_device_status.config(text=f"● Offline — {reason}", fg="#dc2626")
        self._mqtt_remote_controls_refresh()

    def _on_mqtt_watch_click(self, event=None) -> None:
        target_id = self.rc_target_id_var.get().strip()
        if not target_id:
            return
        self.mqtt_last_status_monotonic = 0.0
        self.mqtt_last_io_monotonic = 0.0
        self.mqtt_device_online = False
        self.mqtt_device_comm = "offline"
        self.mqtt_remote_pending_request_id = None
        self.mqtt_remote_pending_since = 0.0
        self.lbl_rc_device_status.config(text=f"● Đang theo dõi {target_id}...", fg="#d97706")
        if self.mqtt_client:
            self.mqtt_client.watch_callbox(target_id)
        self._mqtt_remote_controls_refresh()

    def _on_mqtt_status(self, callbox_id: str, data: dict) -> None:
        if callbox_id != self.rc_target_id_var.get().strip():
            return
        self.mqtt_last_status_monotonic = time.monotonic()
        self.mqtt_device_online = bool(data.get("online", False))
        self.mqtt_device_comm = str(data.get("comm", "offline"))
        self.mqtt_latest_version = str(data.get("version", ""))
        fw = str(data.get("fw", "—"))
        self.lbl_rc_device_meta.config(
            text=f"Comm: {self.mqtt_device_comm.upper()}   Version: {self.mqtt_latest_version or '—'}   FW: {fw}"
        )
        if self.mqtt_latest_version == "1.0":
            self.btn_rc_remote_2.config(text="NÚT 2 / TASK 1")
        else:
            self.btn_rc_remote_2.config(text="NÚT 2 / TASK 2")
        task1 = str(data.get("task1", "—"))
        task2 = str(data.get("task2", "—"))
        self.lbl_rc_task1.config(text=f"Task 1: {task1.upper()}")
        self.lbl_rc_task2.config(text=f"Task 2: {task2.upper()}")
        if self.mqtt_device_online:
            self.lbl_rc_device_status.config(text=f"● Online — {callbox_id}", fg="#16a34a")
        else:
            self._mqtt_mark_device_offline("LWT")
        self._mqtt_remote_controls_refresh()

    def _on_mqtt_io(self, callbox_id: str, data: dict) -> None:
        if callbox_id != self.rc_target_id_var.get().strip():
            return
        self.mqtt_last_io_monotonic = time.monotonic()
        call1 = bool(data.get("call1_pending", False))
        call2 = bool(data.get("call2_pending", False))
        cancel_pending = bool(data.get("cancel_pending", False))
        task1 = str(data.get("task1", "—")).upper()
        task2 = str(data.get("task2", "—")).upper()
        self.lbl_rc_task1.config(text=f"Task 1: {task1}" + ("  • CALL pending" if call1 else ""))
        self.lbl_rc_task2.config(text=f"Task 2: {task2}" + ("  • CALL pending" if call2 else ""))
        cancel_target = int(data.get("cancel_target", 0) or 0)
        self.lbl_rc_cancel_state.config(
            text=(f"Cancel: pending Task {cancel_target}" if cancel_pending else "Cancel: idle")
        )
        leds = data.get("button_leds") or [0, 0, 0]
        while len(leds) < 3:
            leds.append(0)
        self._set_remote_indicator(self.lbl_rc_led1, bool(leds[0]), "#16a34a")
        self._set_remote_indicator(self.lbl_rc_led2, bool(leds[1]), "#16a34a")
        self._set_remote_indicator(self.lbl_rc_led_cancel, bool(leds[2]), "#16a34a")
        tower = data.get("tower") or {}
        self._set_remote_indicator(self.lbl_rc_tower_red, bool(tower.get("red")), "#dc2626")
        self._set_remote_indicator(self.lbl_rc_tower_yellow, bool(tower.get("yellow")), "#d97706")
        self._set_remote_indicator(self.lbl_rc_tower_green, bool(tower.get("green")), "#16a34a")
        self._mqtt_remote_controls_refresh()

    def _on_mqtt_control_ack(self, callbox_id: str, data: dict) -> None:
        if callbox_id != self.rc_target_id_var.get().strip():
            return
        request_id = int(data.get("request_id", 0) or 0)
        if self.mqtt_remote_pending_request_id is not None and request_id != self.mqtt_remote_pending_request_id:
            self._mqtt_log_append(
                f"Bỏ qua control_ack cũ #{request_id}; đang chờ #{self.mqtt_remote_pending_request_id}."
            )
            return

        ok = data.get("status") == "ok"
        button = data.get("button", "?")
        reason = str(data.get("reason", ""))
        if self.mqtt_remote_pending_request_id == request_id:
            self.mqtt_remote_pending_request_id = None
            self.mqtt_remote_pending_since = 0.0

        if ok:
            detail = "đã bỏ bản tin lặp" if reason == "duplicate_ignored" else "đã vào hàng đợi Mission Manager"
            self.lbl_rc_remote_ack.config(
                text=f"DEBUG/TEST: Nút {button} {detail}", fg="#16a34a"
            )
        else:
            self.lbl_rc_remote_ack.config(
                text=f"DEBUG/TEST lỗi Nút {button}: {reason or 'unknown'}", fg="#dc2626"
            )
        self._mqtt_remote_controls_refresh()

    def _on_mqtt_remote_button_click(self, button: int) -> None:
        target_id = self.rc_target_id_var.get().strip()
        if not self.mqtt_client or not self.mqtt_is_connected or not target_id:
            return
        if not self.rc_remote_test_enable_var.get():
            messagebox.showwarning(
                "Chế độ DEBUG/TEST đang khóa",
                "Nút vật lý là điều khiển chính. Chỉ bật DEBUG/TEST khi kỹ thuật viên cần thử nút ảo.",
                parent=self.root,
            )
            return
        if self.mqtt_remote_pending_request_id is not None:
            return
        if not (self.mqtt_device_online and self.mqtt_device_comm == "ready"):
            messagebox.showwarning(
                "Callbox chưa sẵn sàng",
                "Chỉ điều khiển từ xa khi Callbox Online và COMM=READY.",
                parent=self.root,
            )
            return
        if button == 1:
            action = "Nút 1 / Task 1"
        elif button == 2:
            action = "Nút 2 / Task 1" if self.mqtt_latest_version == "1.0" else "Nút 2 / Task 2"
        else:
            action = "HỦY"
        confirm = messagebox.askyesno(
            "Xác nhận thao tác từ xa",
            f"Gửi thao tác {action} tới Callbox {target_id}?\n\n"
            "Lệnh sẽ đi vào chính Mission Manager như nút vật lý; không bỏ qua state machine.",
            parent=self.root,
        )
        if not confirm:
            return
        request_id = self.mqtt_client.send_remote_button(target_id, button)
        if request_id is None:
            self.lbl_rc_remote_ack.config(text="DEBUG/TEST: publish MQTT thất bại", fg="#dc2626")
        else:
            self.mqtt_remote_pending_request_id = request_id
            self.mqtt_remote_pending_since = time.monotonic()
            self.lbl_rc_remote_ack.config(
                text=f"DEBUG/TEST: đã gửi Nút {button}, chờ ACK #{request_id}", fg="#d97706"
            )
        self._mqtt_remote_controls_refresh()

    def _mqtt_monitor_watchdog(self) -> None:
        if self.mqtt_is_connected and self.mqtt_last_status_monotonic > 0:
            if time.monotonic() - self.mqtt_last_status_monotonic > 4.0:
                self._mqtt_mark_device_offline("telemetry timeout")
        if self.mqtt_remote_pending_request_id is not None and self.mqtt_remote_pending_since > 0:
            if time.monotonic() - self.mqtt_remote_pending_since > 5.0:
                timed_out = self.mqtt_remote_pending_request_id
                self.mqtt_remote_pending_request_id = None
                self.mqtt_remote_pending_since = 0.0
                self.lbl_rc_remote_ack.config(
                    text=f"DEBUG/TEST: ACK #{timed_out} timeout - kiểm tra trạng thái trước khi thử lại",
                    fg="#dc2626",
                )
        self._mqtt_remote_controls_refresh()
        self.root.after(1000, self._mqtt_monitor_watchdog)

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

        confirm = messagebox.askyesno(
            "Xác nhận gửi cấu hình từ xa",
            f"Gửi lệnh remote_config đến Callbox ID: {target_id} qua MQTT?\n\n"
            f"• Topic: callbox/{target_id}/cmd\n"
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

        self.lbl_rc_ack_status.config(text=f"Đang gửi đến Callbox {target_id} và chờ ACK...", fg="#d97706")
        ok = self.mqtt_client.send_remote_config(target_id, payload)
        if not ok:
            self.lbl_rc_ack_status.config(text="Lỗi publish MQTT!", fg="#dc2626")

    def _on_mqtt_ack_result(self, callbox_id: str, ok: bool) -> None:
        if ok:
            msg = f"✅ THÀNH CÔNG: Callbox {callbox_id} đã nhận và lưu cấu hình vào NVS!"
            self.lbl_rc_ack_status.config(text=msg, fg="#16a34a")
            self._mqtt_log_append(f"★ {msg}")
        else:
            msg = f"❌ THẤT BẠI: Callbox {callbox_id} báo lỗi khi lưu cấu hình!"
            self.lbl_rc_ack_status.config(text=msg, fg="#dc2626")
            self._mqtt_log_append(f"★ {msg}")

    def _auto_check_update(self) -> None:
        if not self.controller.busy and not self.update_busy:
            self._check_for_update(silent=True)

    def _on_check_update_click(self) -> None:
        if self.controller.busy:
            messagebox.showwarning(
                "Đang nạp ESP32",
                "Không thể cập nhật công cụ trong khi đang nạp thiết bị.",
                parent=self.root,
            )
            return
        if self.update_busy:
            return
        if self.pending_update is not None:
            self._offer_update(self.pending_update)
            return
        self._check_for_update(silent=False)

    def _check_for_update(self, silent: bool) -> None:
        if self.update_busy:
            return
        self.update_busy = True
        self.btn_update.config(text="Đang kiểm tra...", state=tk.DISABLED)

        def worker():
            try:
                result = self.update_client.check(__version__)
            except Exception as error:
                self.root.after(0, self._on_update_check_failed, error, silent)
            else:
                self.root.after(0, self._on_update_check_done, result, silent)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_check_failed(self, error: Exception, silent: bool) -> None:
        self.update_busy = False
        self.btn_update.config(text=f"Update • v{__version__}", state=tk.NORMAL)
        self._append_log(f"Kiểm tra cập nhật: {error}")
        if not silent:
            messagebox.showerror(
                "Không kiểm tra được cập nhật",
                str(error),
                parent=self.root,
            )

    def _on_update_check_done(self, result, silent: bool) -> None:
        self.update_busy = False
        if result.available:
            self.pending_update = result.release
            self.btn_update.config(
                text=f"Có v{result.release.version} • Update",
                state=tk.NORMAL,
            )
            self._append_log(
                f"Có bản Setup CallBox mới: v{result.release.version} "
                f"(hiện tại v{__version__})."
            )
            if not silent:
                self._offer_update(result.release)
        else:
            self.pending_update = None
            self.btn_update.config(text=f"Mới nhất • v{__version__}", state=tk.NORMAL)
            if not silent:
                messagebox.showinfo(
                    "Setup CallBox",
                    f"Bạn đang dùng phiên bản mới nhất: v{__version__}.",
                    parent=self.root,
                )

    def _offer_update(self, release) -> None:
        notes = (release.notes or "Không có ghi chú phát hành.").strip()
        if len(notes) > 1200:
            notes = notes[:1200] + "…"
        confirm = messagebox.askyesno(
            "Có bản cập nhật Setup CallBox",
            f"Phiên bản hiện tại: v{__version__}\n"
            f"Phiên bản mới: v{release.version}\n\n"
            f"Thay đổi:\n{notes}\n\n"
            "Tải bản mới từ GitHub và xác minh SHA-256?",
            parent=self.root,
        )
        if confirm:
            self._start_update_download(release)

    def _start_update_download(self, release) -> None:
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Chế độ phát triển",
                "Updater chỉ tự thay thế khi chạy từ Setup-CallBox.exe đóng gói. "
                "Source mode vẫn có thể được kiểm thử bằng unit test.",
                parent=self.root,
            )
            return
        self.update_busy = True
        self.btn_update.config(text="Đang tải 0%", state=tk.DISABLED)

        def progress(done: int, total: int) -> None:
            percent = int(done * 100 / total) if total else 0
            self.root.after(
                0,
                lambda p=percent: self.btn_update.config(text=f"Đang tải {p}%"),
            )

        def worker():
            try:
                package, digest = self.update_client.download(release, progress)
            except Exception as error:
                self.root.after(0, self._on_update_download_failed, error)
            else:
                self.root.after(
                    0,
                    self._on_update_download_done,
                    release,
                    package,
                    digest,
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_download_failed(self, error: Exception) -> None:
        self.update_busy = False
        if self.pending_update:
            text = f"Có v{self.pending_update.version} • Update"
        else:
            text = f"Update • v{__version__}"
        self.btn_update.config(text=text, state=tk.NORMAL)
        self._append_log(f"Tải cập nhật thất bại: {error}")
        messagebox.showerror("Cập nhật thất bại", str(error), parent=self.root)

    def _on_update_download_done(self, release, package: pathlib.Path, digest: str) -> None:
        self.update_busy = False
        self.downloaded_update = pathlib.Path(package)
        self.downloaded_update_sha = digest
        self.btn_update.config(text=f"Cài v{release.version}", state=tk.NORMAL)
        self._append_log(
            f"Đã tải và xác minh v{release.version}: SHA-256 {digest[:16]}..."
        )
        confirm = messagebox.askyesno(
            "Cài bản cập nhật",
            f"Setup CallBox v{release.version} đã tải xong và SHA-256 hợp lệ.\n\n"
            "Ứng dụng sẽ đóng, tự thay thế EXE hiện tại và mở lại. Cài ngay?",
            parent=self.root,
        )
        if confirm:
            self._install_downloaded_update()

    def _install_downloaded_update(self) -> None:
        if self.controller.busy:
            messagebox.showwarning(
                "Đang nạp ESP32",
                "Hãy hoàn tất quá trình nạp trước khi cập nhật công cụ.",
                parent=self.root,
            )
            return
        if self.downloaded_update is None or not self.downloaded_update_sha:
            return
        try:
            launch_update_helper(
                self.downloaded_update,
                pathlib.Path(sys.executable),
                os.getpid(),
                self.downloaded_update_sha,
            )
        except Exception as error:
            messagebox.showerror(
                "Không thể cài cập nhật",
                str(error),
                parent=self.root,
            )
            return
        self.root.destroy()

    def _on_close(self) -> None:
        if self.mqtt_client:
            try:
                self.mqtt_client.disconnect()
            except Exception:
                pass
        if self.controller.busy:
            if not messagebox.askyesno(
                "Cảnh báo tiến trình đang chạy",
                "Tiến trình nạp board đang diễn ra!\nNếu bạn thoát lúc này, board có thể bị mất firmware.\n"
                "Bạn có chắc chắn muốn thoát?",
            ):
                return
        self.root.destroy()
