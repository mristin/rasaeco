"""Render sample scenarios so that they are continuously included in the repository for demos."""
import os
import pathlib
import subprocess
import sys


def main() -> int:
    """Execute the main routine."""
    this_directory = pathlib.Path(os.path.realpath(__file__))

    cmd = ['pyrasaeco-render.exe', 'once', '--scenarios_dir',
           str(this_directory / 'sample_scenarios')]

    print(f"Executing: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    return 0


if __name__ == "__main__":
    sys.exit(main())
