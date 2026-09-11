from dataclasses import dataclass
import re
from typing import Callable, Iterable, Optional, Sequence
import serial.tools.list_ports


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str
    vid: Optional[int]
    pid: Optional[int]
    serial_number: Optional[str]


def _natural_sort_key(port: PortInfo) -> tuple[int, int, str]:
    match = re.search(r"(\d+)", port.device)
    if match:
        return (0, int(match.group(1)), port.device)
    return (1, 0, port.device)


def discover_ports(
    enumerator: Optional[Callable[[], Iterable[object]]] = None
) -> tuple[PortInfo, ...]:
    if enumerator is None:
        raw_ports = serial.tools.list_ports.comports()
    else:
        raw_ports = enumerator()

    candidates: list[PortInfo] = []
    for p in raw_ports:
        device = getattr(p, "device", "")
        description = getattr(p, "description", "") or ""
        vid = getattr(p, "vid", None)
        pid = getattr(p, "pid", None)
        serial_number = getattr(p, "serial_number", None)

        is_usb = (vid is not None and pid is not None) or ("usb" in description.lower())
        if not is_usb:
            continue

        candidates.append(
            PortInfo(
                device=device,
                description=description,
                vid=vid,
                pid=pid,
                serial_number=serial_number,
            )
        )

    candidates.sort(key=_natural_sort_key)
    return tuple(candidates)


def automatic_port(ports: Sequence[PortInfo]) -> Optional[str]:
    if len(ports) == 1:
        return ports[0].device
    return None
