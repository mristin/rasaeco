#!/usr/bin/env python3
"""Runs pre-commit checks on the repository."""
import argparse
import os
import pathlib
import subprocess
import sys


def main() -> int:
    """"Execute entry_point routine."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--overwrite",
        help="Overwrites the unformatted source files with the well-formatted code in place. "
        "If not set, an exception is raised if any of the files do not conform to the style guide.",
        action="store_true",
    )

    args = parser.parse_args()

    overwrite = bool(args.overwrite)

    repo_root = pathlib.Path(__file__).parent

    print("Black'ing...")
    black_targets = [
        "rasaeco",
        "tests",
        "precommit.py",
        "setup.py",
        "package_sample_scenarios.py",
        "render_sample_scenarios.py"
    ]

    if overwrite:
        subprocess.check_call(["black"] + black_targets, cwd=str(repo_root))
    else:
        subprocess.check_call(["black", "--check"] + black_targets, cwd=str(repo_root))

    print("Mypy'ing...")
    mypy_targets = ["rasaeco", "tests"]
    subprocess.check_call(["mypy", "--strict"] + mypy_targets, cwd=str(repo_root))

    print("Pydocstyle'ing...")
    subprocess.check_call(["pydocstyle", "rasaeco"], cwd=str(repo_root))

    print("Testing...")
    env = os.environ.copy()
    env["ICONTRACT_SLOW"] = "true"

    subprocess.check_call(
        ["coverage", "run", "--source", "rasaeco", "-m", "unittest", "discover"],
        cwd=str(repo_root),
        env=env,
    )

    subprocess.check_call(["coverage", "report"])

    print("Doctesting...")
    subprocess.check_call([sys.executable, "-m", "doctest", "README.rst"])
    for pth in (repo_root / "rasaeco").glob("**/*.py"):
        subprocess.check_call([sys.executable, "-m", "doctest", str(pth)])

    print("Checking the restructured text of the readme...")
    subprocess.check_call(
        [sys.executable, "setup.py", "check", "--restructuredtext", "--strict"]
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
