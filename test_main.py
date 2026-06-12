import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qahelper.cli as main
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

            def create_screenshot(destination, window=False, delay=0):
                self.assertFalse(window)
                self.assertEqual(delay, 0)
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

            def create_screenshot(destination, window=False, delay=0):
                self.assertTrue(window)
                self.assertEqual(delay, 2.5)
                destination.touch()

            with patch.object(
                main, "capture_screenshot", side_effect=create_screenshot
            ):
                screenshot = main.add_screenshot(
                    None, root, window=True, delay=2.5
                )

            self.assertEqual(screenshot, scenario / "001.png")

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
