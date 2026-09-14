from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

@dataclass(frozen=True)
class UiColors:
    canvas: str = "#f1f5f9"
    card: str = "#ffffff"
    surface_alt: str = "#f8fafc"
    border: str = "#e2e8f0"
    text: str = "#0f172a"
    text_secondary: str = "#334155"
    muted_dark: str = "#475569"
    muted: str = "#64748b"
    success: str = "#16a34a"
    danger: str = "#dc2626"
    warning: str = "#d97706"
    info: str = "#0369a1"
    success_bg: str = "#dcfce7"
    success_text: str = "#166534"
    danger_bg: str = "#fee2e2"
    danger_text: str = "#b91c1c"
    warning_bg: str = "#fef3c7"
    warning_text: str = "#92400e"
    dark: str = "#1e293b"
    console: str = "#0f172a"
    white: str = "#ffffff"

COLORS = UiColors()


def configure_ttk_styles(root: tk.Misc) -> None:
    bg_canvas = COLORS.canvas
    style = ttk.Style(root)
    style.theme_use("clam")

    # Universal defaults for all ttk elements
    style.configure(".", background=bg_canvas, font=("Segoe UI", 10))
    style.configure("TFrame", background=bg_canvas)
    style.configure("TLabel", background=bg_canvas, font=("Segoe UI", 10))

    # Secondary / standard button style
    style.configure(
        "Secondary.TButton",
        font=("Segoe UI", 9),
        foreground=COLORS.dark,
        background=COLORS.surface_alt,
        bordercolor="#cbd5e1",
        lightcolor=COLORS.surface_alt,
        darkcolor=COLORS.surface_alt,
        focuscolor="none",
        borderwidth=1,
    )
    style.map(
        "Secondary.TButton",
        background=[("pressed", COLORS.border), ("active", COLORS.canvas), ("disabled", COLORS.canvas)],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.dark)],
        bordercolor=[("disabled", COLORS.border), ("!disabled", "#cbd5e1")],
    )

    # Progress bar
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=COLORS.border,
        background="#0284c7",
        bordercolor="#cbd5e1",
        lightcolor="#0284c7",
        darkcolor="#0284c7",
    )

    # Action button 1: Baseline / Setup (Orange)
    style.configure(
        "Baseline.TButton",
        font=("Segoe UI", 9, "bold"),
        foreground=COLORS.white,
        background="#ea580c",
        bordercolor="#c2410c",
        lightcolor="#ea580c",
        darkcolor="#ea580c",
        focuscolor="none",
        borderwidth=1,
    )
    style.map(
        "Baseline.TButton",
        background=[("disabled", COLORS.border), ("pressed", "#9a3412"), ("active", "#c2410c")],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.white)],
        bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#c2410c")],
        lightcolor=[("disabled", COLORS.border), ("!disabled", "#ea580c")],
        darkcolor=[("disabled", COLORS.border), ("!disabled", "#ea580c")],
    )

    # Action button 2: App Only Update (Sky Blue)
    style.configure(
        "AppOnly.TButton",
        font=("Segoe UI", 9, "bold"),
        foreground=COLORS.white,
        background="#0284c7",
        bordercolor=COLORS.info,
        lightcolor="#0284c7",
        darkcolor="#0284c7",
        focuscolor="none",
        borderwidth=1,
    )
    style.map(
        "AppOnly.TButton",
        background=[("disabled", COLORS.border), ("pressed", "#075985"), ("active", COLORS.info)],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.white)],
        bordercolor=[("disabled", "#cbd5e1"), ("!disabled", COLORS.info)],
        lightcolor=[("disabled", COLORS.border), ("!disabled", "#0284c7")],
        darkcolor=[("disabled", COLORS.border), ("!disabled", "#0284c7")],
    )

    # Action button 3: Full Factory Board Flash (Green)
    style.configure(
        "Primary.TButton",
        font=("Segoe UI", 9, "bold"),
        foreground=COLORS.white,
        background=COLORS.success,
        bordercolor="#15803d",
        lightcolor=COLORS.success,
        darkcolor=COLORS.success,
        focuscolor="none",
        borderwidth=1,
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", COLORS.border), ("pressed", COLORS.success_text), ("active", "#15803d")],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.white)],
        bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#15803d")],
        lightcolor=[("disabled", COLORS.border), ("!disabled", COLORS.success)],
        darkcolor=[("disabled", COLORS.border), ("!disabled", COLORS.success)],
    )

    # Action button 4: Config Only (Purple / Indigo)
    style.configure(
        "ConfigOnly.TButton",
        font=("Segoe UI", 9, "bold"),
        foreground=COLORS.white,
        background="#7c3aed",
        bordercolor="#6d28d9",
        lightcolor="#7c3aed",
        darkcolor="#7c3aed",
        focuscolor="none",
        borderwidth=1,
    )
    style.map(
        "ConfigOnly.TButton",
        background=[("disabled", COLORS.border), ("pressed", "#5b21b6"), ("active", "#6d28d9")],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.white)],
        bordercolor=[("disabled", "#cbd5e1"), ("!disabled", "#6d28d9")],
        lightcolor=[("disabled", COLORS.border), ("!disabled", "#7c3aed")],
        darkcolor=[("disabled", COLORS.border), ("!disabled", "#7c3aed")],
    )

    style.configure(
        "Danger.TButton",
        font=("Segoe UI", 9, "bold"), foreground=COLORS.white,
        background=COLORS.danger, bordercolor=COLORS.danger_text,
        lightcolor=COLORS.danger, darkcolor=COLORS.danger,
        focuscolor="none", borderwidth=1,
    )
    style.map(
        "Danger.TButton",
        background=[("disabled", COLORS.border), ("pressed", "#991b1b"), ("active", COLORS.danger_text)],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.white)],
        bordercolor=[("disabled", "#cbd5e1"), ("!disabled", COLORS.danger_text)],
    )





# WorkerPrimary is intentionally oversized and high-contrast for factory use.

    style.configure(
        "WorkerPrimary.TButton",
        font=("Segoe UI", 15, "bold"),
        foreground=COLORS.white,
        background=COLORS.success,
        bordercolor="#15803d",
        lightcolor=COLORS.success,
        darkcolor=COLORS.success,
        focuscolor="none",
        borderwidth=1,
        padding=[14, 10],
    )
    style.map(
        "WorkerPrimary.TButton",
        background=[("disabled", COLORS.border), ("pressed", COLORS.success_text), ("active", "#15803d")],
        foreground=[("disabled", "#94a3b8"), ("!disabled", COLORS.white)],
        bordercolor=[("disabled", COLORS.border), ("!disabled", "#15803d")],
    )
