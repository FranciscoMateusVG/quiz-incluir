"""Central theme constants. Single source of truth for colors, radii and spacing.

Palette mirrors Programa Incluir's web app (app.programaincluir.org): a warm
orange brand accent over neutral grays, flat white surfaces with a hairline
border instead of heavy shadows.
"""

import flet as ft

# Brand accent
PRIMARY = "#E8622C"
PRIMARY_DARK = "#C94F1F"
PRIMARY_LIGHT = "#FDEEE3"
PRIMARY_GRADIENT = ["#E8622C", "#F4A15B"]

# White copy on PRIMARY is only 3.38:1. Keep PRIMARY for decorative brand
# surfaces and use the darker action token anywhere normal-sized white text
# sits on orange (4.54:1 against white).
ACTION_PRIMARY = PRIMARY_DARK
ACTION_PRIMARY_HOVER = "#B8451B"

# Status colors
SUCCESS = "#2E7D32"
SUCCESS_LIGHT = "#E8F5E9"
# 5.65:1 on ERROR_LIGHT: normal-sized error copy remains WCAG AA.
ERROR = "#B42318"
ERROR_LIGHT = "#FBEAEA"

# Text
TEXT_PRIMARY = "#181411"
TEXT_SECONDARY = "#6B7280"
MUTED = TEXT_SECONDARY
MUTED_700 = "#4B5563"

# Surfaces
BORDER = "#E5E3E0"
SURFACE = "#FFFFFF"
BACKGROUND = "#F7F7F5"

# Shape
CARD_RADIUS = 16
INPUT_RADIUS = 12
PILL_RADIUS = 20
STEP_RADIUS = 15

# Spacing
SPACING_SM = 4
SPACING_MD = 8
SPACING_LG = 12
SPACING_2LG = 16
SPACING_3LG = 20
SPACING_XL = 24
SPACING_2XL = 32
SPACING_3XL = 40

# Interaction and layout guardrails shared by auth/navigation controls.
CONTROL_HEIGHT = 48
MIN_TARGET_SIZE = 44
FORM_WIDTH = 380
FORM_MAX_WIDTH = 420


def card(
    content: ft.Control, *, padding: int = 20, radius: int | None = None
) -> ft.Container:
    """Flat white card with a hairline border (no drop shadow)."""
    return ft.Container(
        content=content,
        padding=padding,
        border_radius=radius if radius is not None else CARD_RADIUS,
        bgcolor=SURFACE,
        border=ft.Border.all(1, BORDER),
    )


def responsive(
    content: ft.Control, *, col: dict | None = None, expand: bool = False
) -> ft.Control:
    """Full-width on mobile, centered max-width column on desktop."""
    return ft.ResponsiveRow(
        alignment=ft.MainAxisAlignment.CENTER,
        expand=expand,
        controls=[
            ft.Container(
                col=col or {"xs": 12, "sm": 11, "md": 8, "lg": 6, "xl": 5},
                content=content,
                expand=expand,
            )
        ],
    )


def text_field(**kwargs) -> ft.TextField:
    """Visible-label field with the shared 48px+ form treatment."""
    defaults = {
        # A minimum decorator height keeps the control touchable without
        # clipping helper/error copy below it as a fixed height would.
        "size_constraints": ft.BoxConstraints(min_height=56),
        "text_size": 16,
        "border_radius": INPUT_RADIUS,
        "border_color": BORDER,
        "focused_border_color": ACTION_PRIMARY,
        "focused_border_width": 2,
        "bgcolor": SURFACE,
        "filled": True,
        "content_padding": ft.Padding.symmetric(vertical=12, horizontal=16),
        "scroll_padding": ft.Padding.all(SPACING_XL),
    }
    defaults.update(kwargs)
    return ft.TextField(**defaults)


def primary_button(content, **kwargs) -> ft.FilledButton:
    """Accessible primary action with one consistent 48px target."""
    defaults = {
        "height": CONTROL_HEIGHT,
        "content": content,
        "style": ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DEFAULT: ACTION_PRIMARY,
                ft.ControlState.HOVERED: ACTION_PRIMARY_HOVER,
            },
            color=ft.Colors.WHITE,
            padding=ft.Padding.symmetric(vertical=12, horizontal=20),
            shape=ft.RoundedRectangleBorder(radius=INPUT_RADIUS),
            animation_duration=180,
            text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_600),
        ),
    }
    defaults.update(kwargs)
    return ft.FilledButton(**defaults)


def icon_action(*, icon, tooltip: str, on_click=None, **kwargs) -> ft.IconButton:
    """Named 44px icon action; the glyph can remain optically smaller."""
    defaults = {
        "icon": icon,
        "tooltip": tooltip,
        "width": MIN_TARGET_SIZE,
        "height": MIN_TARGET_SIZE,
        "size_constraints": ft.BoxConstraints(
            min_width=MIN_TARGET_SIZE,
            min_height=MIN_TARGET_SIZE,
        ),
        "icon_size": 20,
        "on_click": on_click,
    }
    defaults.update(kwargs)
    return ft.IconButton(**defaults)


def page_theme() -> ft.Theme:
    """Material theme wiring the brand palette into every default control."""
    return ft.Theme(
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=ACTION_PRIMARY,
            # The scheme's on-primary pairing also feeds controls outside our
            # helpers, so keep it on the accessible action shade.
            on_primary=ft.Colors.WHITE,
            primary_container=PRIMARY_LIGHT,
            on_primary_container=PRIMARY_DARK,
            secondary=ACTION_PRIMARY,
            on_secondary=ft.Colors.WHITE,
            error=ERROR,
            on_error=ft.Colors.WHITE,
            surface=SURFACE,
            on_surface=TEXT_PRIMARY,
            outline=BORDER,
            outline_variant=BORDER,
        ),
        card_theme=ft.CardTheme(
            color=SURFACE,
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS),
        ),
        appbar_theme=ft.AppBarTheme(
            bgcolor=SURFACE,
            color=TEXT_PRIMARY,
            elevation=0,
        ),
        filled_button_theme=ft.FilledButtonTheme(
            style=ft.ButtonStyle(
                bgcolor=ACTION_PRIMARY,
                color=ft.Colors.WHITE,
                padding=ft.Padding.symmetric(vertical=12, horizontal=20),
                shape=ft.RoundedRectangleBorder(radius=INPUT_RADIUS),
                animation_duration=180,
                text_style=ft.TextStyle(size=16, weight=ft.FontWeight.W_600),
            )
        ),
        outlined_button_theme=ft.OutlinedButtonTheme(
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                side=ft.BorderSide(1, BORDER),
                padding=ft.Padding.symmetric(vertical=12, horizontal=20),
                shape=ft.RoundedRectangleBorder(radius=INPUT_RADIUS),
                animation_duration=180,
            )
        ),
        text_button_theme=ft.TextButtonTheme(
            style=ft.ButtonStyle(
                color=ACTION_PRIMARY,
                padding=ft.Padding.symmetric(vertical=10, horizontal=12),
                animation_duration=180,
            )
        ),
        icon_button_theme=ft.IconButtonTheme(
            style=ft.ButtonStyle(
                color=TEXT_PRIMARY,
                padding=ft.Padding.all(12),
                animation_duration=180,
            )
        ),
        progress_indicator_theme=ft.ProgressIndicatorTheme(color=ACTION_PRIMARY),
        divider_color=BORDER,
    )
