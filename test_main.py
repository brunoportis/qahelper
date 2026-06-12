import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qahelper.cli as main
import qahelper.native_screenshot as native_screenshot
from rich.console import Console
from typer.testing import CliRunner


class ScenarioCliTest(unittest.TestCase):
    runner = CliRunner()

    def console(self) -> Console:
        return Console(record=True, width=140, color_system=None)

    def test_start_creates_numbered_scenario_and_reuses_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            first = main.start_scenario("Lead sem conta", root)
            resumed = main.start_scenario("Lead sem conta", root)

            self.assertEqual(first, root / "qa-scenarios/TC-001-lead-sem-conta")
            self.assertEqual(resumed, first)
            state = json.loads((root / ".qahelper/state.json").read_text())
            self.assertEqual(
                state["active_scenario"], "qa-scenarios/TC-001-lead-sem-conta"
            )

    def test_start_uses_next_scenario_number(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            main.start_scenario("Primeiro", root)
            second = main.start_scenario("Segundo", root)

            self.assertEqual(second.name, "TC-002-segundo")

    def test_add_screenshot_uses_next_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = main.start_scenario("Lead sem conta", root)
            (scenario / "001.png").touch()

            def create_screenshot(destination, window=False, delay=0, gui=False):
                self.assertFalse(window)
                self.assertEqual(delay, 0)
                self.assertFalse(gui)
                destination.touch()

            with patch.object(
                main, "capture_screenshot", side_effect=create_screenshot
            ):
                screenshot = main.add_screenshot(None, root)

            self.assertEqual(screenshot, scenario / "002.png")

    def test_add_screenshot_forwards_window_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = main.start_scenario("Lead sem conta", root)

            def create_screenshot(destination, window=False, delay=0, gui=False):
                self.assertTrue(window)
                self.assertEqual(delay, 2.5)
                self.assertFalse(gui)
                destination.touch()

            with patch.object(
                main, "capture_screenshot", side_effect=create_screenshot
            ):
                screenshot = main.add_screenshot(
                    None, root, window=True, delay=2.5
                )

            self.assertEqual(screenshot, scenario / "001.png")

    def test_desktop_environment_uses_ubuntu_session_variables(self):
        environment = {
            "XDG_SESSION_DESKTOP": "ubuntu",
            "DESKTOP_SESSION": "ubuntu-wayland",
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
        }

        with patch.dict(os.environ, environment, clear=True):
            self.assertIn("gnome", main.desktop_environment())

    def test_x11_window_uses_gnome_screenshot_and_delay(self):
        destination = Path("/tmp/window.png")
        environment = {
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":0",
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(
                main.shutil,
                "which",
                side_effect=lambda executable: (
                    f"/usr/bin/{executable}"
                    if executable == "gnome-screenshot"
                    else None
                ),
            ),
            patch.object(main.time, "sleep") as sleep,
            patch.object(main.subprocess, "run") as run,
        ):
            main.capture_screenshot(destination, window=True, delay=2)

        sleep.assert_called_once_with(2)
        run.assert_called_once_with(
            [
                "gnome-screenshot",
                "--window",
                "--file",
                str(destination),
            ],
            check=True,
        )

    def test_wayland_gnome_uses_portal_from_session_desktop(self):
        destination = Path("/tmp/window.png")
        environment = {
            "XDG_SESSION_TYPE": "wayland",
            "WAYLAND_DISPLAY": "wayland-0",
            "XDG_SESSION_DESKTOP": "gnome",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(main.subprocess, "run") as run,
        ):
            main.capture_screenshot(destination, window=True, delay=1)

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/python3")
        self.assertIn("portal_screenshot.py", command[1])
        self.assertEqual(
            command[2:],
            [str(destination), "--interactive", "--delay", "1"],
        )

    def test_gui_uses_portal_on_x11(self):
        destination = Path("/tmp/window.png")
        environment = {
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":0",
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(main.shutil, "which", return_value=None),
            patch.object(main.subprocess, "run") as run,
        ):
            main.capture_screenshot(destination, gui=True, delay=2)

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/python3")
        self.assertIn("portal_screenshot.py", command[1])
        self.assertEqual(
            command[2:],
            [str(destination), "--interactive", "--delay", "2"],
        )

    def test_gui_uses_native_printscreen_ui_on_x11(self):
        destination = Path("/tmp/window.png")
        environment = {
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":0",
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(
                main.shutil,
                "which",
                side_effect=lambda executable: (
                    "/usr/bin/xdotool" if executable == "xdotool" else None
                ),
            ),
            patch.object(main.subprocess, "run") as run,
        ):
            main.capture_screenshot(destination, gui=True, delay=2)

        command = run.call_args.args[0]
        self.assertEqual(command[0], main.sys.executable)
        self.assertIn("native_screenshot.py", command[1])
        self.assertEqual(command[2:], [str(destination), "--delay", "2"])

    def test_native_screenshot_detects_new_png(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old.png"
            new = root / "Screenshots/new.png"
            old.touch()
            before = native_screenshot.png_snapshot(root)
            new.parent.mkdir()
            new.write_bytes(b"png")

            detected = native_screenshot.wait_for_screenshot(
                root, before, timeout_seconds=0.1
            )

            self.assertEqual(detected, new)

    def test_explicit_order_cannot_overwrite_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = main.start_scenario("Lead sem conta", root)
            (scenario / "003.png").touch()

            with self.assertRaisesRegex(main.CliError, "Já existe"):
                main.add_screenshot(3, root)

    def test_list_scenarios_marks_current_and_counts_screenshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = main.start_scenario("Primeiro cenário", root)
            main.start_scenario("Segundo cenário", root)
            (first / "001.png").touch()
            (first / "002.png").touch()
            console = self.console()

            main.list_scenarios(root, console)

            output = console.export_text()
            self.assertIn("TC-001", output)
            self.assertIn("Primeiro Cenario", output)
            self.assertIn("2", output)
            self.assertIn("TC-002", output)
            self.assertIn("●", output)

    def test_current_scenario_shows_path_and_screenshot_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = main.start_scenario("Lead sem conta", root)
            (scenario / "001.png").touch()
            console = self.console()

            main.show_current_scenario(root, console)

            output = console.export_text()
            self.assertIn("Cenário atual", output)
            self.assertIn("TC-001-lead-sem-conta", output)
            self.assertIn("1 screenshot(s)", output)

    def test_dashboard_shows_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = main.start_scenario("Primeiro", root)
            main.start_scenario("Segundo", root)
            (first / "001.png").touch()
            console = self.console()

            main.show_dashboard(root, console)

            output = console.export_text()
            self.assertIn("QA Dashboard", output)
            self.assertIn("2", output)
            self.assertIn("cenários", output)
            self.assertIn("1", output)
            self.assertIn("screenshots", output)
            self.assertIn("TC-002-segundo", output)

    def test_empty_dashboard_does_not_require_active_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            console = self.console()

            main.show_dashboard(Path(directory), console)

            output = console.export_text()
            self.assertIn("0", output)
            self.assertIn("Nenhum cenário encontrado", output)

    def test_typer_exposes_scenario_commands(self):
        result = self.runner.invoke(main.app, ["qa", "scenario", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("start", result.stdout)
        self.assertIn("list", result.stdout)
        self.assertIn("current", result.stdout)
        self.assertIn("dashboard", result.stdout)
        self.assertIn("add-screenshot", result.stdout)

        screenshot_help = self.runner.invoke(
            main.app,
            ["qa", "scenario", "add-screenshot", "--help"],
        )
        self.assertEqual(screenshot_help.exit_code, 0)
        self.assertIn("--gui", screenshot_help.stdout)

    def test_typer_start_command_creates_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            with patch.object(main.Path, "cwd", return_value=root):
                result = self.runner.invoke(
                    main.app,
                    ["qa", "scenario", "start", "Lead sem conta"],
                )

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(
                (root / "qa-scenarios/TC-001-lead-sem-conta").is_dir()
            )

    def test_typer_rejects_negative_delay(self):
        result = self.runner.invoke(
            main.app,
            ["qa", "scenario", "add-screenshot", "--delay", "-1"],
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("--delay não pode ser negativo", result.output)


if __name__ == "__main__":
    unittest.main()
