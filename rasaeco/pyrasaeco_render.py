#!/usr/bin/env python

"""Render the scenarios and the scenario ontology."""
import argparse
import contextlib
import dataclasses
import io
import os
import pathlib
import queue
import sys
import threading
import time
from typing import Tuple, Optional, Union, List, TextIO, Generator, TYPE_CHECKING

import watchdog.observers
import watchdog.events

import rasaeco.render


@dataclasses.dataclass
class Once:
    """Represent the command to render everything once."""

    scenarios_dir: pathlib.Path


@dataclasses.dataclass
class Continuously:
    """Represent the command to render everything once."""

    scenarios_dir: pathlib.Path


def _make_argument_parser() -> argparse.ArgumentParser:
    """Create an instance of the argument parser to parse command-line arguments."""
    parser = argparse.ArgumentParser(prog="pyrasaeco-render", description=__doc__)
    subparsers = parser.add_subparsers(help="Commands", dest="command")
    subparsers.required = True

    once = subparsers.add_parser(
        "once", help="Render once the scenarios and the scenario ontology"
    )

    continuously = subparsers.add_parser(
        "continuously",
        help="Re-render continuously the scenarios and the scenario ontology",
    )

    for command in [once, continuously]:
        command.add_argument(
            "-s",
            "--scenarios_dir",
            help="Directory where scenarios reside\n\n"
            "The rendering artefacts will be produced in-place in this directory.",
            required=True,
        )

    return parser


def _parse_args_to_params(
    args: argparse.Namespace,
) -> Tuple[Optional[Union[Once, Continuously]], List[str]]:
    """
    Parse the parameters from the command-line arguments.

    Return parsed parameters, errors if any
    """
    errors = []  # type: List[str]

    if args.command == "once":
        return Once(scenarios_dir=pathlib.Path(args.scenarios_dir)), []
    elif args.command == "continuously":
        return (
            Continuously(scenarios_dir=pathlib.Path(args.scenarios_dir)),
            [],
        )
    else:
        raise AssertionError(f"Unexpected command: {args.command!r}")


def _parse_args(
    parser: argparse.ArgumentParser, argv: List[str]
) -> Tuple[Optional[argparse.Namespace], str, str]:
    """
    Parse the command-line arguments.

    Return (parsed args or None if failure, captured stdout, captured stderr).
    """
    pass  # for pydocstyle

    # From https://stackoverflow.com/questions/18160078
    @contextlib.contextmanager
    def captured_output() -> Generator[Tuple[TextIO, TextIO], None, None]:
        new_out, new_err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = new_out, new_err
            yield sys.stdout, sys.stderr
        finally:
            sys.stdout, sys.stderr = old_out, old_err

    with captured_output() as (out, err):
        try:
            parsed_args = parser.parse_args(argv)

            err.seek(0)
            out.seek(0)
            return parsed_args, out.read(), err.read()

        except SystemExit:
            err.seek(0)
            out.seek(0)
            return None, out.read(), err.read()


# See https://mypy.readthedocs.io/en/stable/common_issues.html#using-classes-that-are-generic-in-stubs-but-not-at-runtime
if TYPE_CHECKING:
    StopQueue = queue.Queue[bool]  # This is only processed by mypy.
else:
    StopQueue = queue.Queue


def _render_continuosly(
    stdout: TextIO, stderr: TextIO, scenarios_dir: pathlib.Path, stop: StopQueue
) -> None:
    """Render continuously the scenarios in an endless loop."""
    last_modification = None  # type: Optional[float]

    print(f"Entering the endless loop to render in-place: {scenarios_dir}", file=stdout)

    signal_queue = queue.Queue()  # type: queue.Queue[int]

    SHOULD_STOP = 0
    SHOULD_RERENDER = 1

    class EventHandler(watchdog.events.FileSystemEventHandler):  # type: ignore
        """Push to the signal queue on any event."""

        def on_any_event(self, event):  # type: ignore
            """Handle any event."""
            _, extension = os.path.splitext(event.src_path)
            if extension == ".md":
                signal_queue.put(SHOULD_RERENDER)

    def work() -> None:
        """Re-render on signals and quit on stop."""
        first = True
        while True:
            action = None
            empty = False
            try:
                action = signal_queue.get_nowait()
            except queue.Empty:
                empty = True

            if first or not empty:
                if first or action == SHOULD_RERENDER:
                    errors = rasaeco.render.once(scenarios_dir=scenarios_dir)
                    for error in errors:
                        print(error, file=stderr)

                    if not errors:
                        print(
                            f"All scenarios re-rendered. Open the ontology in your browser: "
                            f"file://{str(scenarios_dir.absolute() / 'ontology.html')}",
                            file=stdout,
                        )
                        first = False

                elif action == SHOULD_STOP:
                    return

            time.sleep(0.5)

    work_thread = threading.Thread(target=work)
    work_thread.start()

    observer = watchdog.observers.Observer()
    observer.schedule(EventHandler(), str(scenarios_dir), recursive=True)
    try:
        observer.start()
        try:
            while True:
                try:
                    stop.get_nowait()
                    signal_queue.put(SHOULD_STOP)
                    observer.stop()
                    return
                except queue.Empty:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            observer.stop()
    finally:
        observer.stop()
        observer.join()

        signal_queue.put(SHOULD_STOP)
        work_thread.join()


def run(argv: List[str], stdout: TextIO, stderr: TextIO) -> int:
    """Execute the main routine."""
    parser = _make_argument_parser()
    args, out, err = _parse_args(parser=parser, argv=argv)
    if len(out) > 0:
        stdout.write(out)

    if len(err) > 0:
        stderr.write(err)

    if args is None:
        return 1

    command, errors = _parse_args_to_params(args=args)
    if errors:
        for error in errors:
            print(error, file=stderr)
            return 1

    if isinstance(command, Once):
        errors = rasaeco.render.once(scenarios_dir=command.scenarios_dir)
    elif isinstance(command, Continuously):
        stop = queue.Queue()  # type: queue.Queue[bool]
        _render_continuosly(stdout, stderr, command.scenarios_dir, stop)
    else:
        raise AssertionError("Unhandled command: {}".format(command))

    if errors:
        for error in errors:
            print(error, file=stderr)
            return 1

    return 0


def entry_point() -> int:
    """Wrap the entry_point routine wit default arguments."""
    return run(argv=sys.argv[1:], stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    sys.exit(entry_point())
