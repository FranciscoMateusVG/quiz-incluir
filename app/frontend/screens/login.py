from __future__ import annotations

import re

import flet as ft
from flet import component, use_effect, use_state

import theme
from config import APP_TITLE
from controllers.auth_controller import AuthController
from quiz_shared.enums import UserRole
from services.exceptions import QuizApiError

CPF_DIGITS_RE = re.compile(r"^[0-9]{11}$")
CPF_MASK_RE = re.compile(r"^[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}$")

_ERROR_MESSAGES = {
    "invalid_cpf": "CPF inválido. Confira os 11 números e tente novamente.",
    "invalid_request": "Preencha o CPF e a senha para continuar.",
    "invalid_credentials": "CPF ou senha inválidos.",
    "account_denied": "Esta conta não pode acessar o Incluir Quiz.",
    "rate_limited": "Muitas tentativas. Aguarde um momento e tente novamente.",
    "auth_unavailable": "Não foi possível entrar agora. Tente novamente.",
    "auth_invalid_response": (
        "O serviço de acesso respondeu de forma inesperada. Tente novamente."
    ),
}


def _mask_cpf_digits(digits: str) -> str:
    """Apply the canonical mask to an ASCII digit prefix."""
    digits = digits[:11]
    if len(digits) <= 3:
        return digits
    if len(digits) <= 6:
        return f"{digits[:3]}.{digits[3:]}"
    if len(digits) <= 9:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:]}"
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


def format_cpf(value: str) -> str:
    """Format a valid incremental CPF prefix without sanitizing arbitrary input.

    A raw ASCII digit prefix is maskable. An already-masked prefix is maskable
    only when its punctuation is in the canonical positions. Unexpected
    punctuation, letters and Unicode digits remain visible so submit validation
    can reject them instead of silently changing the user's input.
    """
    value = value.strip()
    if re.fullmatch(r"[0-9]{0,11}", value):
        return _mask_cpf_digits(value)
    if not re.fullmatch(r"[0-9.-]{0,14}", value):
        return value
    digits = value.replace(".", "").replace("-", "")
    candidate = _mask_cpf_digits(digits)
    return candidate if value == candidate else value


def normalize_cpf_digits(value: str) -> str:
    """Return 11 ASCII digits for either exact accepted wire shape."""
    value = value.strip()
    if CPF_DIGITS_RE.fullmatch(value):
        return value
    if CPF_MASK_RE.fullmatch(value):
        return f"{value[:3]}{value[4:7]}{value[8:11]}{value[12:14]}"
    raise ValueError("invalid CPF shape")


def _error_code(error: Exception) -> str | None:
    if not isinstance(error, QuizApiError):
        return None
    if error.code:
        return error.code
    if isinstance(error.detail, str) and error.detail in _ERROR_MESSAGES:
        return error.detail
    return None


def login_error_message(error: Exception) -> str:
    """Map typed API outcomes to safe, actionable pt-BR copy."""
    code = _error_code(error)
    if code == "rate_limited" and isinstance(error, QuizApiError):
        retry = error.retry_after_seconds
        if isinstance(retry, int) and retry > 0:
            return f"Muitas tentativas. Tente novamente em {retry} segundos."
    return _ERROR_MESSAGES.get(code, "Não foi possível entrar. Tente novamente.")


def _brand_logo(*, width: int, height: int) -> ft.Semantics:
    return ft.Semantics(
        label="Programa Incluir",
        image=True,
        content=ft.Image(
            src="logo-branco.png",
            width=width,
            height=height,
            fit=ft.BoxFit.CONTAIN,
        ),
    )


@component
def LoginScreen(auth: AuthController):
    cpf, set_cpf = use_state("")
    password, set_password = use_state("")
    password_visible, set_password_visible = use_state(False)
    error, set_error = use_state("")
    loading, set_loading = use_state(False)

    page = ft.context.page

    def set_page_title():
        page.title = f"Acessar | {APP_TITLE}"
        page.update()

        def restore_page_title():
            page.title = APP_TITLE
            page.update()

        return restore_page_title

    use_effect(set_page_title, [])

    async def on_login(e):
        if loading:
            return
        try:
            cpf_digits = normalize_cpf_digits(cpf or "")
        except ValueError:
            set_error(_ERROR_MESSAGES["invalid_cpf"])
            return
        if not password:
            set_error(_ERROR_MESSAGES["invalid_request"])
            return

        set_loading(True)
        set_error("")
        try:
            if not await auth.login(cpf_digits, password):
                return
            is_admin = (
                auth.state.current_user is not None
                and auth.state.current_user.role == UserRole.ADMIN
            )
            destination = auth.state.consume_return_route(is_admin=is_admin)
            # login() just completed the authoritative /users/me call, so this
            # one destination can render without an immediate duplicate probe.
            auth.mark_validated_route(destination)
            page.navigate(destination)
        except Exception as ex:
            set_error(login_error_message(ex))
        finally:
            set_loading(False)

    def on_cpf_change(e):
        set_cpf(format_cpf(e.control.value or ""))

    def toggle_password(e):
        set_password_visible(not password_visible)

    password_label = "Ocultar senha" if password_visible else "Mostrar senha"
    password_button = theme.icon_action(
        key="login-password-visibility",
        icon=(
            ft.Icons.VISIBILITY_OFF_OUTLINED
            if password_visible
            else ft.Icons.VISIBILITY_OUTLINED
        ),
        tooltip=password_label,
        on_click=toggle_password,
        icon_color=theme.MUTED_700,
    )
    # Flutter Web does not expose IconButton.tooltip as a computed AX name.
    # One excluding Semantics node supplies the only accessible label while
    # the inner 44px IconButton remains the literal pointer target.
    password_action = ft.Semantics(
        key="login-password-visibility-semantics",
        label=password_label,
        button=True,
        focusable=True,
        exclude_semantics=True,
        on_tap=toggle_password,
        content=password_button,
    )

    cpf_field = theme.text_field(
        key="login-cpf",
        width=theme.FORM_MAX_WIDTH,
        value=cpf,
        on_change=on_cpf_change,
        label="CPF",
        hint_text="000.000.000-00",
        prefix_icon=ft.Icons.BADGE_OUTLINED,
        keyboard_type=ft.KeyboardType.NUMBER,
        autofocus=True,
        autocorrect=False,
        enable_suggestions=False,
        smart_dashes_type=False,
        smart_quotes_type=False,
        autofill_hints=ft.AutofillHint.USERNAME,
        error=error if error == _ERROR_MESSAGES["invalid_cpf"] else None,
        error_max_lines=2,
    )
    password_field = theme.text_field(
        key="login-password",
        width=theme.FORM_MAX_WIDTH,
        value=password,
        on_change=lambda e: set_password(e.control.value or ""),
        label="Senha",
        hint_text="Digite sua senha",
        prefix_icon=ft.Icons.LOCK_OUTLINE,
        suffix_icon=password_action,
        suffix_icon_size_constraints=ft.BoxConstraints(
            min_width=theme.MIN_TARGET_SIZE,
            min_height=theme.MIN_TARGET_SIZE,
        ),
        password=not password_visible,
        can_reveal_password=False,
        on_submit=on_login,
        autocorrect=False,
        enable_suggestions=False,
        smart_dashes_type=False,
        smart_quotes_type=False,
        autofill_hints=ft.AutofillHint.PASSWORD,
    )

    status_message = error or auth.state.auth_notice
    status = ft.Semantics(
        container=True,
        live_region=True,
        label=status_message or "",
        hidden=not bool(status_message),
        content=(
            ft.Container(
                key="login-status",
                padding=12,
                bgcolor=(theme.ERROR_LIGHT if error else theme.PRIMARY_LIGHT),
                border_radius=theme.INPUT_RADIUS,
                border=ft.Border.all(1, theme.ERROR if error else theme.BORDER),
                content=ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Icon(
                            ft.Icons.ERROR_OUTLINE if error else ft.Icons.INFO_OUTLINE,
                            color=theme.ERROR if error else theme.PRIMARY_DARK,
                            size=20,
                        ),
                        ft.Text(
                            status_message,
                            color=theme.ERROR if error else theme.TEXT_PRIMARY,
                            size=14,
                            expand=True,
                        ),
                    ],
                ),
            )
            if status_message
            else ft.Container(height=0)
        ),
    )

    submit_content = (
        ft.Row(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
            controls=[
                ft.ProgressRing(
                    width=18,
                    height=18,
                    stroke_width=2,
                    color=ft.Colors.WHITE,
                ),
                ft.Text("Entrando…"),
            ],
        )
        if loading
        else ft.Text("Entrar no Quiz")
    )

    form = ft.Column(
        key="login-form",
        spacing=theme.SPACING_XL,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            ft.Column(
                spacing=theme.SPACING_MD,
                controls=[
                    ft.Semantics(
                        header=True,
                        heading_level=1,
                        label="Acesse o Incluir Quiz",
                        exclude_semantics=True,
                        content=ft.Text(
                            "Acesse o Incluir Quiz",
                            size=32,
                            weight=ft.FontWeight.BOLD,
                            color=theme.TEXT_PRIMARY,
                        ),
                    ),
                    ft.Text(
                        "Use o mesmo CPF e senha do Programa Incluir.",
                        size=16,
                        color=theme.TEXT_SECONDARY,
                    ),
                ],
            ),
            ft.Column(
                spacing=theme.SPACING_2LG,
                controls=[cpf_field, password_field],
            ),
            status,
            theme.primary_button(
                submit_content,
                key="login-submit",
                width=theme.FORM_MAX_WIDTH,
                disabled=loading,
                on_click=on_login,
            ),
        ],
    )

    desktop_brand = ft.Container(
        key="login-brand-desktop",
        col={"xs": 0, "sm": 0, "md": 0, "lg": 6, "xl": 6, "xxl": 6},
        expand=True,
        padding=40,
        bgcolor=theme.PRIMARY,
        content=ft.Column(
            expand=True,
            controls=[
                _brand_logo(width=220, height=72),
                ft.Container(expand=True),
                ft.Column(
                    spacing=theme.SPACING_LG,
                    controls=[
                        ft.Container(
                            width=64,
                            height=64,
                            border_radius=32,
                            bgcolor=theme.ACTION_PRIMARY,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(
                                ft.Icons.SCHOOL, color=ft.Colors.WHITE, size=34
                            ),
                        ),
                        ft.Semantics(
                            header=True,
                            heading_level=2,
                            label="Incluir Quiz",
                            content=ft.Text(
                                "Incluir Quiz",
                                size=36,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.WHITE,
                            ),
                        ),
                        ft.Text(
                            "Pratique inglês com atividades curtas e objetivas.",
                            size=18,
                            weight=ft.FontWeight.W_600,
                            color=theme.TEXT_PRIMARY,
                        ),
                    ],
                ),
            ],
        ),
    )

    compact_brand = ft.Container(
        key="login-brand-compact",
        col={"xs": 12, "sm": 12, "md": 12, "lg": 0, "xl": 0, "xxl": 0},
        bgcolor=theme.PRIMARY,
        padding=ft.Padding.symmetric(vertical=16, horizontal=24),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                _brand_logo(width=150, height=52),
                ft.Container(
                    width=48,
                    height=48,
                    border_radius=24,
                    bgcolor=theme.ACTION_PRIMARY,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.SCHOOL, color=ft.Colors.WHITE, size=26),
                ),
            ],
        ),
    )

    desktop_form_panel = ft.Container(
        key="login-form-desktop",
        col={"xs": 0, "sm": 0, "md": 0, "lg": 6, "xl": 6, "xxl": 6},
        expand=True,
        bgcolor=theme.SURFACE,
        padding=theme.SPACING_2XL,
        content=ft.Column(
            expand=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[ft.Container(width=theme.FORM_MAX_WIDTH, content=form)],
        ),
    )

    compact_form_panel = ft.Container(
        key="login-form-compact",
        col={"xs": 12, "sm": 12, "md": 12, "lg": 0, "xl": 0, "xxl": 0},
        bgcolor=theme.SURFACE,
        padding=ft.Padding.symmetric(vertical=32, horizontal=24),
        content=ft.ResponsiveRow(
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=0,
            run_spacing=0,
            controls=[
                ft.Container(
                    col={
                        "xs": 12,
                        "sm": 8,
                        "md": 7,
                        "lg": 0,
                        "xl": 0,
                        "xxl": 0,
                    },
                    content=form,
                )
            ],
        ),
    )

    return ft.View(
        route="/",
        bgcolor=theme.BACKGROUND,
        padding=0,
        controls=[
            ft.ResponsiveRow(
                key="login-shell",
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                spacing=0,
                run_spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    desktop_brand,
                    compact_brand,
                    desktop_form_panel,
                    compact_form_panel,
                ],
            )
        ],
    )
