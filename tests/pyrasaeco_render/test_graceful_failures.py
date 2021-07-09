import io
import os
import pathlib
import shutil
import tempfile
import unittest

import rasaeco.pyrasaeco_render


class TestInvalidScenariosDir(unittest.TestCase):
    def test_not_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            scenarios_dir = os.path.join(tmp_dir, "does-not-exist")
            argv = ["once", "--scenarios_dir", scenarios_dir]

            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = rasaeco.pyrasaeco_render.run(
                argv=argv, stdout=stdout, stderr=stderr
            )

            self.assertEqual(1, exit_code)
            self.assertEqual(
                f"The directory you specified in --scenarios_dir does not exist "
                f"on your system: {scenarios_dir}\n",
                stderr.getvalue(),
            )

    def test_not_a_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            scenarios_dir = os.path.join(tmp_dir, "actually-a-file")
            with open(scenarios_dir, "wt") as fid:
                fid.write("oi")

            argv = ["once", "--scenarios_dir", scenarios_dir]

            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = rasaeco.pyrasaeco_render.run(
                argv=argv, stdout=stdout, stderr=stderr
            )

            self.assertEqual(1, exit_code)
            self.assertEqual(
                f"The path you specified in --scenarios_dir is expected "
                f"to be a directory, but it is not: {scenarios_dir}\n",
                stderr.getvalue(),
            )


class TestOnFailureCases(unittest.TestCase):
    def test_that_failures_are_handled_gracefully(self) -> None:
        this_dir = pathlib.Path(os.path.realpath(__file__)).parent
        failure_cases_dir = this_dir.parent / "failure_cases"
        assert failure_cases_dir.exists(), str(failure_cases_dir)

        for pth in sorted(failure_cases_dir.glob("**/scenario.md")):
            with tempfile.TemporaryDirectory() as tmp_dir:
                scenario_dir = os.path.join(tmp_dir, pth.parent.name)
                os.mkdir(scenario_dir)

                scenario_pth = os.path.join(scenario_dir, "scenario.md")
                shutil.copy(src=str(pth), dst=scenario_pth)

                argv = ["once", "--scenarios_dir", tmp_dir]

                stdout = io.StringIO()
                stderr = io.StringIO()

                try:
                    exit_code = rasaeco.pyrasaeco_render.run(
                        argv=argv, stdout=stdout, stderr=stderr
                    )
                except Exception as exception:
                    raise AssertionError(
                        f"Unexpected exception while processing the scenario: {pth}"
                    ) from exception

                error = stderr.getvalue()
                error = error.replace(str(scenario_pth), "<path to scenario.md>")

                expected_pth = pth.parent / "expected.err"
                expected = expected_pth.read_text(encoding="utf-8")

                self.assertEqual(expected, error, str(pth))
                self.assertEqual(exit_code, 1, str(pth))
