"""Perform integration tests."""
import io
import os
import pathlib
import queue
import shutil
import tempfile
import threading
import time
import unittest

import rasaeco.pyrasaeco_render


class TestOnSamples(unittest.TestCase):
    def test_render_once(self) -> None:
        this_dir = pathlib.Path(os.path.realpath(__file__)).parent

        scenarios_dir = this_dir.parent.parent / "sample_scenarios"

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

    def test_continuously(self) -> None:
        this_dir = pathlib.Path(os.path.realpath(__file__)).parent

        scenarios_dir = this_dir.parent.parent / "sample_scenarios"

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_scenarios_dir = pathlib.Path(os.path.join(tmp_dir, "sample_scenarios"))
            shutil.copytree(src=str(scenarios_dir), dst=str(tmp_scenarios_dir))

            stdout = io.StringIO()
            stderr = io.StringIO()

            stop = queue.Queue()  # type: queue.Queue[bool]
            worker_thread = threading.Thread(
                target=rasaeco.pyrasaeco_render._render_continuously,
                args=(stdout, stderr, tmp_scenarios_dir, stop),
            )
            worker_thread.start()
            try:
                time.sleep(2)

                # Modify a file
                pth = sorted(tmp_scenarios_dir.glob("**/*.md"))[0]
                text = pth.read_text(encoding="utf-8")
                pth.write_text(text + "\n\nmodified", encoding="utf-8")

                time.sleep(2)
                stop.put(True)
            finally:
                stop.put(True)
                worker_thread.join()

            # This is merely a smoke test.
            self.assertEqual("", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
