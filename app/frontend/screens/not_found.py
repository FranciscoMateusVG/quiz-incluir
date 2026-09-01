"""404 screen: rendered by the Router when no route matches the URL."""

from __future__ import annotations

import flet as ft
from flet import component

import theme


@component
def NotFoundScreen():
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=24,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
            controls=[
                ft.Icon(ft.Icons.SEARCH_OFF_ROUNDED, size=64, color=theme.MUTED),
                ft.Text(
                    "404",
                    size=48,
                    weight=ft.FontWeight.BOLD,
                    color=theme.TEXT_PRIMARY,
                ),
                ft.Text("Page not found", size=18, color=theme.MUTED),
                ft.FilledButton(
                    "Go to homepage",
                    on_click=lambda e: ft.context.page.navigate("/"),
                ),
            ],
        ),
    )
