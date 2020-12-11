"""Perform integration tests."""
import io
import os
import pathlib
import shutil
import unittest
import tempfile

import rasaeco.pyrasaeco_render


class TestOnSamples(unittest.TestCase):
    def test_that_it_works(self) -> None:
        this_dir = pathlib.Path(os.path.realpath(__file__)).parent

        scenarios_dir = this_dir.parent / "sample_scenarios"

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_scenarios_dir = os.path.join(tmp_dir, "sample_scenarios")

            shutil.copytree(src=str(scenarios_dir), dst=tmp_scenarios_dir)

            argv = ["once", "--scenarios_dir", tmp_scenarios_dir]

            stdout = io.StringIO()
            stderr = io.StringIO()

            # This is merely a smoke test.
            exit_code = rasaeco.pyrasaeco_render.run(
                argv=argv, stdout=stdout, stderr=stderr
            )

            self.assertEqual("", stderr.getvalue())
            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
