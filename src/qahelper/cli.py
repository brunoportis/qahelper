from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


STATE_DIR = ".qahelper"
STATE_FILE = "state.json"
SCENARIOS_DIR = "qa-scenarios"
SCENARIO_PATTERN = re.compile(r"^TC-(\d+)-(.+)$")
SCREENSHOT_PATTERN = re.compile(r"^(\d+)\.png$")

app = typer.Typer(help="Ferramentas para registrar evidências de QA.")
qa_app = typer.Typer(help="Comandos de QA.")
scenario_app = typer.Typer(help="Gerencia cenários de QA.")
app.add_typer(qa_app, name="qa")
qa_app.add_typer(scenario_app, name="scenario")


class CliError(Exception):
    pass


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def state_path(root: Path) -> Path:
    return root / STATE_DIR / STATE_FILE


def find_project_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if state_path(candidate).is_file():
            return candidate
    raise CliError(
        'Nenhum cenário ativo. Execute `qahelper qa scenario start "Nome"` primeiro.'
    )


def find_workspace_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if state_path(candidate).is_file() or (candidate / SCENARIOS_DIR).is_dir():
            return candidate
    return current


def scenario_directories(root: Path) -> list[Path]:
    scenarios_root = root / SCENARIOS_DIR
    if not scenarios_root.exists():
        return []
    return sorted(
        path
        for path in scenarios_root.iterdir()
        if path.is_dir() and SCENARIO_PATTERN.match(path.name)
    )


def start_scenario(name: str, root: Path) -> Path:
    slug = slugify(name)
    if not slug:
        raise CliError("O nome do cenário precisa conter letras ou números.")

    scenarios = scenario_directories(root)
    scenario = next(
        (
            path
            for path in scenarios
            if (match := SCENARIO_PATTERN.match(path.name)) and match.group(2) == slug
        ),
        None,
    )

    if scenario is None:
        highest_id = max(
            (
                int(match.group(1))
                for path in scenarios
                if (match := SCENARIO_PATTERN.match(path.name))
            ),
            default=0,
        )
        scenario = root / SCENARIOS_DIR / f"TC-{highest_id + 1:03d}-{slug}"
        scenario.mkdir(parents=True)
        action = "criado"
    else:
        action = "retomado"

    state = {"active_scenario": str(scenario.relative_to(root)), "name": name}
    state_file = state_path(root)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=True) + "\n")

    print(f"Cenário {action}: {scenario}")
    return scenario


def active_scenario(root: Path) -> Path:
    try:
        state = json.loads(state_path(root).read_text())
        relative_path = state["active_scenario"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise CliError("O estado do cenário ativo está inválido.") from error

    scenario = root / relative_path
    if not scenario.is_dir():
        raise CliError(f"A pasta do cenário ativo não existe: {scenario}")
    return scenario


def optional_active_scenario(root: Path) -> Path | None:
    if not state_path(root).is_file():
        return None
    try:
        return active_scenario(root)
    except CliError:
        return None


def screenshot_count(scenario: Path) -> int:
    return sum(
        1
        for path in scenario.iterdir()
        if path.is_file() and SCREENSHOT_PATTERN.match(path.name)
    )


def scenario_title(scenario: Path) -> str:
    match = SCENARIO_PATTERN.match(scenario.name)
    if not match:
        return scenario.name
    return match.group(2).replace("-", " ").title()


def scenario_table(root: Path, active: Path | None) -> Table:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("", width=2)
    table.add_column("ID", style="bold")
    table.add_column("Cenário")
    table.add_column("Screenshots", justify="right")
    table.add_column("Pasta", style="dim")

    scenarios = scenario_directories(root)
    for scenario in scenarios:
        match = SCENARIO_PATTERN.match(scenario.name)
        scenario_id = f"TC-{match.group(1)}" if match else "-"
        is_active = active == scenario
        style = "bold green" if is_active else None
        table.add_row(
            "●" if is_active else "",
            scenario_id,
            scenario_title(scenario),
            str(screenshot_count(scenario)),
            str(scenario.relative_to(root)),
            style=style,
        )
    return table


def list_scenarios(start: Path, console: Console | None = None) -> None:
    root = find_workspace_root(start)
    output = console or Console()
    scenarios = scenario_directories(root)
    if not scenarios:
        output.print("[yellow]Nenhum cenário encontrado.[/yellow]")
        return
    output.print(scenario_table(root, optional_active_scenario(root)))


def show_current_scenario(start: Path, console: Console | None = None) -> None:
    root = find_project_root(start)
    scenario = active_scenario(root)
    output = console or Console()
    output.print(
        Panel.fit(
            Text.from_markup(
                f"[bold green]{scenario.name}[/bold green]\n"
                f"{screenshot_count(scenario)} screenshot(s)\n"
                f"[dim]{scenario}[/dim]"
            ),
            title="Cenário atual",
            border_style="green",
        )
    )


def show_dashboard(start: Path, console: Console | None = None) -> None:
    root = find_workspace_root(start)
    output = console or Console()
    scenarios = scenario_directories(root)
    active = optional_active_scenario(root)
    total_screenshots = sum(screenshot_count(scenario) for scenario in scenarios)
    active_label = active.name if active else "Nenhum"

    summary = Table.grid(expand=True)
    summary.add_column(justify="center")
    summary.add_column(justify="center")
    summary.add_column(justify="center")
    summary.add_row(
        f"[bold cyan]{len(scenarios)}[/bold cyan]\ncenários",
        f"[bold magenta]{total_screenshots}[/bold magenta]\nscreenshots",
        f"[bold green]{active_label}[/bold green]\nativo",
    )
    output.print(Panel(summary, title="QA Dashboard", border_style="cyan"))
    if scenarios:
        output.print(scenario_table(root, active))
    else:
        output.print("[yellow]Nenhum cenário encontrado.[/yellow]")


def next_screenshot_order(scenario: Path) -> int:
    orders = [
        int(match.group(1))
        for path in scenario.iterdir()
        if path.is_file() and (match := SCREENSHOT_PATTERN.match(path.name))
    ]
    return max(orders, default=0) + 1


def screenshot_command(destination: Path) -> list[str]:
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("grim"):
        return ["grim", str(destination)]

    candidates = (
        ("gnome-screenshot", ["gnome-screenshot", "-f", str(destination)]),
        ("scrot", ["scrot", str(destination)]),
        ("import", ["import", "-window", "root", str(destination)]),
    )
    for executable, command in candidates:
        if shutil.which(executable):
            return command

    raise CliError(
        "Nenhuma ferramenta de screenshot encontrada. "
        "Instale gdbus/dbus-monitor, grim, gnome-screenshot, scrot ou ImageMagick."
    )


def desktop_environment() -> str:
    return ":".join(
        filter(
            None,
            (
                os.environ.get("XDG_CURRENT_DESKTOP"),
                os.environ.get("XDG_SESSION_DESKTOP"),
                os.environ.get("DESKTOP_SESSION"),
            ),
        )
    ).lower()


def session_type() -> str:
    configured = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if os.environ.get("WAYLAND_DISPLAY") or configured == "wayland":
        return "wayland"
    if os.environ.get("DISPLAY") or configured in {"x11", "xorg"}:
        return "x11"
    return "unknown"


def portal_screenshot_command(
    destination: Path, interactive: bool, delay: float
) -> list[str] | None:
    portal_helper = Path(__file__).with_name("portal_screenshot.py")
    if not (
        "gnome" in desktop_environment()
        and Path("/usr/bin/python3").is_file()
        and portal_helper.is_file()
    ):
        return None

    command = ["/usr/bin/python3", str(portal_helper), str(destination)]
    if interactive:
        command.append("--interactive")
    if delay:
        command.extend(["--delay", str(delay)])
    return command


def x11_window_command(destination: Path) -> list[str]:
    candidates = (
        (
            "gnome-screenshot",
            ["gnome-screenshot", "--window", "--file", str(destination)],
        ),
        ("scrot", ["scrot", "--focused", str(destination)]),
        ("import", ["import", str(destination)]),
    )
    for executable, command in candidates:
        if shutil.which(executable):
            return command
    raise CliError(
        "Nenhuma ferramenta para captura de janela encontrada no X11. "
        "Instale gnome-screenshot, scrot ou ImageMagick."
    )


def capture_screenshot(
    destination: Path,
    window: bool = False,
    delay: float = 0,
    gui: bool = False,
) -> None:
    current_session = session_type()
    portal_command = portal_screenshot_command(
        destination,
        interactive=gui or (window and current_session == "wayland"),
        delay=delay,
    )

    if gui:
        if not portal_command:
            raise CliError(
                "O seletor gráfico requer GNOME com xdg-desktop-portal e "
                "python3-gi instalados."
            )
        subprocess.run(portal_command, check=True)
        return

    if current_session == "wayland" and portal_command:
        subprocess.run(portal_command, check=True)
        return

    if current_session == "x11":
        if delay:
            print(f"Captura em {delay:g} segundos...", flush=True)
            time.sleep(delay)
        command = x11_window_command(destination) if window else screenshot_command(destination)
        subprocess.run(command, check=True)
        return

    if portal_command:
        subprocess.run(portal_command, check=True)
        return

    if window and current_session == "wayland":
        raise CliError(
            "O compositor Wayland atual não oferece captura de janela pelo portal. "
            "No GNOME, confirme que xdg-desktop-portal-gnome está instalado."
        )

    if window:
        raise CliError(
            "Não foi possível identificar a sessão gráfica para capturar uma janela. "
            "Verifique XDG_SESSION_TYPE, WAYLAND_DISPLAY e DISPLAY."
        )

    if delay:
        print(f"Captura em {delay:g} segundos...", flush=True)
        time.sleep(delay)
    subprocess.run(screenshot_command(destination), check=True)


def add_screenshot(
    order: int | None,
    start: Path,
    window: bool = False,
    delay: float = 0,
    gui: bool = False,
) -> Path:
    root = find_project_root(start)
    scenario = active_scenario(root)
    screenshot_order = order if order is not None else next_screenshot_order(scenario)
    if screenshot_order < 1:
        raise CliError("--order precisa ser maior que zero.")

    destination = scenario / f"{screenshot_order:03d}.png"
    if destination.exists():
        raise CliError(f"Já existe um screenshot com a ordem {screenshot_order}: {destination}")

    try:
        capture_screenshot(destination, window=window, delay=delay, gui=gui)
    except subprocess.CalledProcessError as error:
        destination.unlink(missing_ok=True)
        raise CliError(f"Não foi possível capturar o screenshot: {error}") from error
    except CliError:
        destination.unlink(missing_ok=True)
        raise

    if not destination.is_file():
        raise CliError("A ferramenta de screenshot terminou sem criar o arquivo.")

    print(f"Screenshot salvo: {destination}")
    return destination


def exit_with_error(error: CliError) -> None:
    Console(stderr=True).print(f"[bold red]Erro:[/bold red] {error}")
    raise typer.Exit(code=1)


@scenario_app.command("start")
def start_command(
    name: Annotated[str, typer.Argument(help="Nome do cenário")],
) -> None:
    """Cria ou retoma um cenário."""
    try:
        start_scenario(name, Path.cwd())
    except CliError as error:
        exit_with_error(error)


@scenario_app.command("list")
def list_command() -> None:
    """Lista os cenários."""
    list_scenarios(Path.cwd())


@scenario_app.command("current")
def current_command() -> None:
    """Mostra o cenário atual."""
    try:
        show_current_scenario(Path.cwd())
    except CliError as error:
        exit_with_error(error)


@scenario_app.command("dashboard")
def dashboard_command() -> None:
    """Mostra o dashboard de QA."""
    show_dashboard(Path.cwd())


@scenario_app.command("add-screenshot")
def add_screenshot_command(
    order: Annotated[
        int | None,
        typer.Option("--order", help="Ordem do screenshot"),
    ] = None,
    window: Annotated[
        bool,
        typer.Option(
            "--window",
            help="Captura a janela focada ou abre o seletor quando necessário",
        ),
    ] = False,
    gui: Annotated[
        bool,
        typer.Option(
            "--gui",
            help="Abre o seletor gráfico nativo do GNOME",
        ),
    ] = False,
    delay: Annotated[
        float,
        typer.Option("--delay", help="Segundos de espera antes de iniciar a captura"),
    ] = 0,
) -> None:
    """Captura a tela para o cenário ativo."""
    try:
        if delay < 0:
            raise CliError("--delay não pode ser negativo.")
        add_screenshot(order, Path.cwd(), window=window, delay=delay, gui=gui)
    except CliError as error:
        exit_with_error(error)


def main() -> None:
    app(prog_name="qahelper")


if __name__ == "__main__":
    main()
