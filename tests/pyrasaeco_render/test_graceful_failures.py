import io
import os
import pathlib
import queue
import shutil
import sys
import threading
import time
import unittest
import tempfile

import rasaeco.pyrasaeco_render


class TestOnFailureCases(unittest.TestCase):
    def test_that_failures_are_handled_gracefully(self) -> None:
        this_dir = pathlib.Path(os.path.realpath(__file__)).parent
        failure_cases_dir = this_dir.parent / "failure_cases"
        assert failure_cases_dir.exists(), str(failure_cases_dir)

        for pth in sorted(failure_cases_dir.glob("**/scenario.md")):
            with tempfile.TemporaryDirectory() as tmp_dir:
                scenario_pth = os.path.join(tmp_dir, "scenario.md")
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
                error = error.replace(tmp_dir, "<tmp dir>")

                expected_pth = pth.parent / "expected.err"
                expected = expected_pth.read_text(encoding="utf-8")

                self.assertEqual(expected, error, str(pth))
                self.assertEqual(exit_code, 1, str(pth))
