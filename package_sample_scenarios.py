#!/usr/bin/env python

"""Package sample scenarios to a Zip archive."""
import argparse
import pathlib
import sys
import zipfile
from typing import Optional


def main() -> int:
    """Execute the main routine."""
    parser = argparse.ArgumentParser(
        prog="package_sample_scenarios", description=__doc__
    )
    parser.add_argument(
        "--scenarios_dir", help="Path to the sample scenarios", required=True
    )
    parser.add_argument(
        "--output_path", help="Path to the resulting Zip archive", required=True
    )

    args = parser.parse_args()
    scenarios_dir = pathlib.Path(args.scenarios_dir)
    output_path = pathlib.Path(args.output_path)

    arch = None  # type: Optional[zipfile.ZipFile]
    try:
        arch = zipfile.ZipFile(str(output_path), mode="w")
    except Exception as error:
        print(f"Failed to create the zip file {output_path}: {error}")
        return -1

    assert arch is not None

    try:
        for pth in scenarios_dir.glob("**/*.md"):
            try:
                arch.write(
                    str(pth),
                    arcname=str(
                        pathlib.Path(scenarios_dir.name)
                        / pth.relative_to(scenarios_dir)
                    ),
                )
            except Exception as error:
                print(
                    f"Failed to add the file {pth} to zip archive {output_path}: {error}"
                )
                return -1
    finally:
        arch.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
