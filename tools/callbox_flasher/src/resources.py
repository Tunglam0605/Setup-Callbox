import pathlib
import sys


def resource_path(relative: str) -> pathlib.Path:
    base = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
    return base / relative

