import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from tools.callbox_flasher.src.app_version import __version__
from tools.callbox_flasher.src.controller import ProvisionController
from tools.callbox_flasher.src.factory_profile import load_factory_profile, validate_factory_profile_for_worker
from tools.callbox_flasher.src.image_validator import validate_application
from tools.callbox_flasher.src.models import ApplicationInfo, ProvisionEvent
from tools.callbox_flasher.src.mqtt_remote_config import CallboxRemoteConfigClient
from tools.callbox_flasher.src.ports import discover_ports
from tools.callbox_flasher.src.release_update import ReleaseManager
from tools.callbox_flasher.src.resources import resource_path
from tools.callbox_flasher.src.ui_flash import FlashWorkflowMixin
from tools.callbox_flasher.src.ui_management import ManagementUiMixin
from tools.callbox_flasher.src.ui_management_diagnostic import ManagementDiagnosticUiMixin
from tools.callbox_flasher.src.ui_management_resources import ManagementResourcesUiMixin
from tools.callbox_flasher.src.ui_mqtt_session import MqttSessionMixin
from tools.callbox_flasher.src.ui_production import ProductionUiMixin
from tools.callbox_flasher.src.ui_shell import ShellUiMixin
from tools.callbox_flasher.src.ui_remote import RemoteMqttUiMixin
from tools.callbox_flasher.src.ui_system import SystemUiMixin
from tools.callbox_flasher.src.ui_state import (
    can_flash, can_flash_baseline, can_flash_bundle, can_flash_config,
    can_monitor_io, can_remote_control,
)
from tools.callbox_flasher.src.ui_updates import UpdateUiMixin
from tools.callbox_flasher.src.ui_worker import WorkerUiMixin


class FlasherApp(
    ShellUiMixin,
    SystemUiMixin,
    ProductionUiMixin,
    FlashWorkflowMixin,
    MqttSessionMixin,
    RemoteMqttUiMixin,
    ManagementUiMixin,
    ManagementDiagnosticUiMixin,
    ManagementResourcesUiMixin,
    WorkerUiMixin,
    UpdateUiMixin,
):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"AUBOT Setup CallBox v{__version__}")
        self.root.minsize(900, 690)
        self.root.geometry("960x760")
        self.mqtt_client: Optional[CallboxRemoteConfigClient] = None
        self.mqtt_is_connected = False
        self.engineer_mode = False
        self.release_catalog = None
        self._worker_job_active = False

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
        self.release_manager = ReleaseManager(__version__)
        self.controller = ProvisionController(
            manifest_loader=self.release_manager.load_active_firmware_manifest
        )
        self.app_info: Optional[ApplicationInfo] = None
        self.bundle_info: Optional[ApplicationInfo] = None
        self.ports = discover_ports()

        try:
            self.factory_profile = load_factory_profile(require=True)
            validate_factory_profile_for_worker(self.factory_profile)
            self.factory_profile_error = ""
        except Exception as error:
            self.factory_profile = None
            self.factory_profile_error = str(error)

        try:
            manifest = self.release_manager.load_active_firmware_manifest()
            manifest.verify_assets()
            self.bundle_info = validate_application(manifest.application.path)
            manifest_info = (
                f"Tool v{__version__} • Firmware v{manifest.firmware_version} • "
                f"{manifest.chip.upper()} 16MB"
            )
        except Exception as error:
            self.bundle_info = None
            manifest_info = f"Firmware package lỗi: {error}"

        self._setup_ui(manifest_info)
        self._refresh_ports()
        self._auto_detect_firmware()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._drain_events)
        self.root.after(800, self._start_release_check)

    def _on_close(self) -> None:
        if self.controller.busy:
            if not messagebox.askyesno(
                "Đang nạp Callbox",
                "Tiến trình ghi flash đang chạy. Thoát lúc này có thể làm board không khởi động.\n\n"
                "Bạn có chắc chắn muốn thoát?",
                parent=self.root,
            ):
                return
        if getattr(self, "_closing", False):
            return
        self._closing = True

        # 1. Cancel recurring after timer handles
        for after_attr in (
            "_mgmt_subscribe_after_id", "_io_subscribe_after_id",
            "_mgmt_tick_after_id", "_drain_events_after_id", "_poll_ports_after_id",
        ):
            after_id = getattr(self, after_attr, None)
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
                setattr(self, after_attr, None)

        # 2. Detach MQTT client callbacks and disconnect in background
        mqtt_client = self.mqtt_client
        self.mqtt_client = None
        if mqtt_client:
            for callback_name in (
                "on_connect", "on_ack", "on_button_ack", "on_io_state",
                "on_status_state", "on_internet_state", "on_health_state",
                "on_diagnostic_state", "on_info_state", "on_network_state",
                "on_trace_event", "on_log",
            ):
                setattr(mqtt_client, callback_name, None)
            threading.Thread(
                target=mqtt_client.disconnect,
                daemon=True,
                name="mqtt-shutdown",
            ).start()

        # 3. Stop Tk event loop and destroy window
        try:
            self.root.quit()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
