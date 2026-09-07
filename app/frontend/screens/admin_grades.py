"""Admin: real-time grade distribution and per-question breakdown for one quiz.

Polls the admin endpoints on an interval so the view stays current as
students finish attempts, without needing any websocket/SSE infrastructure.
"""

from __future__ import annotations

import asyncio
import base64
from io import BytesIO

import flet as ft
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flet import component, use_effect, use_ref, use_route_params, use_state
from quiz_shared.enums import CourseLevel

import theme
from controllers.admin_controller import AdminController
from controllers.auth_controller import AuthController
from services.exceptions import QuizApiError
from state.app_state import AppState
from widgets.navbar import app_bar

POLL_INTERVAL_S = 10

_LEVEL_OPTIONS = [ft.DropdownOption(key="", text="All levels")] + [
    ft.DropdownOption(key=level.value, text=level.value) for level in CourseLevel
]


def _build_boxplot_png(attempts) -> str:
    """Render a grade-distribution boxplot (one box per CourseLevel present)
    to a base64-encoded PNG string, for display via ``ft.Image(src=...)`` —
    Flet's ``Image.src`` accepts a URL/path, a base64 string, or raw bytes
    (there is no separate ``src_base64`` parameter in this Flet version).
    Raw bytes doesn't survive the JSON-based patch wire format cleanly, so
    the base64-string form is what actually round-trips to the browser.

    Rendered as a plain static image rather than through flet-charts'
    ``MatplotlibChart``/``PlotlyChart`` live-streaming controls: those wrap a
    stateful client/server protocol (canvas resize handshake, binary frame
    streaming) that hung indefinitely in this environment with no visible
    error on either side. A static PNG needs nothing beyond the core
    ``ft.Image`` control, which is already proven to work elsewhere in this
    app (e.g. the navbar logo).
    """
    scored = [a for a in attempts if a.finished and a.score is not None]
    levels = sorted({str(a.level) for a in scored})
    data = [[a.score for a in scored if str(a.level) == lvl] for lvl in levels]

    fig, ax = plt.subplots(figsize=(6, 3.5))
    if data:
        ax.boxplot(
            data,
            tick_labels=levels,
            patch_artist=True,
            boxprops=dict(facecolor=theme.PRIMARY_LIGHT, color=theme.PRIMARY),
            medianprops=dict(color=theme.PRIMARY_DARK),
        )
    ax.set_ylabel("Score")
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


@component
def AdminGradesScreen(
    state: AppState, controller: AdminController, auth: AuthController
):
    params = use_route_params()
    quiz_id = params.get("quiz_id", "")

    level, set_level = use_state("")
    attempts, set_attempts = use_state([])
    stats, set_stats = use_state([])
    loading, set_loading = use_state(True)
    error, set_error = use_state("")
    forbidden, set_forbidden = use_state(False)

    task_ref = use_ref(None)

    async def load():
        try:
            lvl = level or None
            new_attempts, new_stats = await asyncio.gather(
                controller.list_attempts(quiz_id, lvl),
                controller.get_question_stats(quiz_id, lvl),
            )
            set_attempts(new_attempts)
            set_stats(new_stats)
            set_error("")
            set_forbidden(False)
        except QuizApiError as ex:
            if ex.status_code == 403:
                set_forbidden(True)
            else:
                set_error(f"Could not load grades: {ex.detail}")
        except Exception as ex:
            set_error(f"Could not load grades: {ex}")
        finally:
            set_loading(False)

    async def start_polling():
        async def poll_loop():
            while True:
                await load()
                await asyncio.sleep(POLL_INTERVAL_S)

        task_ref.current = asyncio.create_task(poll_loop())

    def stop_polling():
        if task_ref.current is not None:
            task_ref.current.cancel()
            task_ref.current = None

    use_effect(start_polling, [quiz_id, level], stop_polling)

    def on_level_change(e):
        set_level(e.control.value or "")
        set_loading(True)

    level_filter = ft.Dropdown(
        label="Class (level)",
        value=level,
        options=_LEVEL_OPTIONS,
        on_select=on_level_change,
        width=220,
        border_radius=theme.INPUT_RADIUS,
    )

    if forbidden:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, color=theme.ERROR, size=50),
                    ft.Text(
                        "You don't have access to the admin dashboard.",
                        color=theme.ERROR,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        )
    elif loading and not attempts and not stats:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [ft.ProgressRing(), ft.Text("Loading grades...", color=theme.MUTED)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        )
    elif error:
        body = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.ERROR, size=50),
                    ft.Text(error, color=theme.ERROR, text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
        )
    else:
        finished_count = sum(1 for a in attempts if a.finished)
        boxplot = theme.card(
            ft.Column(
                [
                    ft.Text("Grade distribution", size=18, weight=ft.FontWeight.BOLD),
                    ft.Image(
                        src=_build_boxplot_png(attempts),
                        fit=ft.BoxFit.CONTAIN,
                        width=600,
                        height=350,
                    )
                    if finished_count
                    else ft.Text(
                        "No finished attempts yet for this filter.", color=theme.MUTED
                    ),
                ],
                spacing=12,
            )
        )

        question_table = theme.card(
            ft.Column(
                [
                    ft.Text(
                        "Per-question correct / wrong",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("Question")),
                            ft.DataColumn(ft.Text("Correct"), numeric=True),
                            ft.DataColumn(ft.Text("Wrong"), numeric=True),
                            ft.DataColumn(ft.Text("Unanswered"), numeric=True),
                        ],
                        rows=[
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(
                                        ft.Text(
                                            s.prompt,
                                            max_lines=1,
                                            overflow=ft.TextOverflow.ELLIPSIS,
                                        )
                                    ),
                                    ft.DataCell(ft.Text(str(s.correct_count))),
                                    ft.DataCell(ft.Text(str(s.incorrect_count))),
                                    ft.DataCell(ft.Text(str(s.unanswered_count))),
                                ]
                            )
                            for s in stats
                        ],
                    ),
                ],
                spacing=12,
            )
        )

        body = ft.Container(
            padding=20,
            expand=True,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("Grades", size=26, weight=ft.FontWeight.BOLD),
                            level_filter,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text(
                        f"Updates automatically every {POLL_INTERVAL_S}s.",
                        size=12,
                        color=theme.MUTED,
                    ),
                    boxplot,
                    question_table,
                ],
                spacing=20,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    return ft.View(
        route=f"/admin/grades/{quiz_id}",
        bgcolor=theme.BACKGROUND,
        appbar=app_bar(state, auth, title="Class Grades"),
        controls=[
            theme.responsive(
                body,
                expand=True,
                col={"xs": 12, "sm": 12, "md": 11, "lg": 10, "xl": 9},
            )
        ],
    )
