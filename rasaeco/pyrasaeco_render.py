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
import http.server
import socketserver

import rasaeco.render


@dataclasses.dataclass
class Once:
    """Represent the command to render everything once."""

    scenarios_dir: pathlib.Path


@dataclasses.dataclass
class Continuously:
    """Represent the command to render everything once."""

    scenarios_dir: pathlib.Path
    port: Optional[int]


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

    continuously.add_argument(
        "-p",
        "--port",
        help="Port on which the demo server should listen to.\n\n"
        "If not specified, the demo server will not be started.",
        type=int,
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
            Continuously(
                scenarios_dir=pathlib.Path(args.scenarios_dir),
                port=None if args.port is None else int(args.port),
            ),
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


class ThreadedServer:
    """Encapsulate a HTTP server running in a separate thread."""

    def __init__(
        self, port: int, scenarios_dir: pathlib.Path, stdout: TextIO, stderr: TextIO
    ) -> None:
        """
        Initialize with the given values and specify the handler.

        No thread is started.
        """
        self.port = port
        self.scenarios_dir = scenarios_dir
        self.stdout = stdout
        self.stderr = stderr

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):  # type: ignore
                super().__init__(*args, directory=str(scenarios_dir), **kwargs)  # type: ignore

            def log_message(self, format, *args):  # type: ignore
                pass

            def do_GET(self):  # type: ignore
                if self.path == "/":
                    self.path = "ontology.html"

                return http.server.SimpleHTTPRequestHandler.do_GET(self)

        self.handler = Handler

        self._httpd = http.server.HTTPServer(("", port), Handler)
        self._work_thread = None  # type: Optional[threading.Thread]

        self._server_exception_lock = threading.Lock()
        self._server_exception = None  # type: Optional[Exception]

    def start(self) -> None:
        """Start the server in a separate thread."""
        pass  # for pydocstyle

        def serve() -> None:
            """Serve forever."""
            prefix = f"In {ThreadedServer.__name__}.{serve.__name__}"
            try:
                print(
                    f"{prefix}: Starting to serve {self.scenarios_dir} forever on: "
                    f"http://localhost:{self.port}",
                    file=self.stdout,
                )

                self._httpd.serve_forever()

                print(f"{prefix}: Stopped serving forever.", file=self.stdout)

            except Exception as error:
                print(
                    f"{prefix}: Caught an exception in the HTTPD server "
                    f"(it will be raised at shutdown): {error}",
                    file=self.stderr,
                )

                with self._server_exception_lock:
                    self._server_exception = error

        self._work_thread = threading.Thread(target=serve)
        self._work_thread.start()

    def shutdown(self) -> None:
        """Shutdown the server and raise any exception from the server."""
        prefix = f"In {ThreadedServer.__name__}.{ThreadedServer.shutdown.__name__}"

        print(f"{prefix}: Instructing the server to shut down...", file=self.stdout)
        with self._server_exception_lock:
            if self._server_exception is not None:
                raise self._server_exception

        print(f"{prefix}: Waiting for server to shut down...", file=self.stdout)
        self._httpd.shutdown()

    def __enter__(self) -> "ThreadedServer":
        """Start the server."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Shut down the server."""
        self.shutdown()


def _render_continuously(
    stdout: TextIO,
    stderr: TextIO,
    scenarios_dir: pathlib.Path,
    stop: StopQueue,
) -> None:
    """Render continuously the scenarios in an endless loop."""
    # Watchdog modules are imported here (instead of importing them at the top) since
    # we had problems with permissions on Windows and anti-virus software complaining.
    #
    # This way the users can still use the tool without the continuous rendering if they have
    # trouble with the permissions.
    import watchdog.observers
    import watchdog.events

    prefix = f"In {_render_continuously.__name__}"

    print(
        f"{prefix}: Entering the endless loop to render in-place: {scenarios_dir}",
        file=stdout,
    )

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

    def render() -> None:
        """Re-render on signals and quit on stop."""
        first = True
        while True:
            action = None  # type: Optional[int]
            if not first:
                action = signal_queue.get()

            if first or action == SHOULD_RERENDER:
                errors = rasaeco.render.once(scenarios_dir=scenarios_dir)
                for error in errors:
                    print(error, file=stderr)

                if not errors:
                    print(
                        f"{prefix}: The scenarios have been re-rendered.", file=stdout
                    )
                    first = False

            elif action == SHOULD_STOP:
                return

            else:
                raise AssertionError(f"Unexpected action: {action}")

    render_thread = threading.Thread(target=render)
    render_thread.start()

    observer = watchdog.observers.Observer()
    observer.schedule(EventHandler(), str(scenarios_dir), recursive=True)
    observer.start()

    try:
        stop.get()
        print(
            f"{prefix}: Received a stop, "
            f"putting it back to the queue to propagate it to other threads.",
            file=stdout,
        )
        stop.put(True)
    finally:
        print(f"{prefix}: Instructing the observer to stop...", file=stdout)
        observer.stop()
        print(f"{prefix}: Joining the observer...", file=stdout)
        observer.join()

        print(f"{prefix}: Putting SHOULD_STOP on signal queue...", file=stdout)
        signal_queue.put(SHOULD_STOP)
        print(f"{prefix}: Joining the render thread...", file=stdout)
        render_thread.join()


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
        server = None  # type: Optional[ThreadedServer]

        with contextlib.ExitStack() as exit_stack:
            if command.port is not None:
                server = ThreadedServer(
                    port=command.port,
                    scenarios_dir=command.scenarios_dir,
                    stdout=stdout,
                    stderr=stderr,
                )
                server.start()
                exit_stack.push(server)

            stop = queue.Queue()  # type: queue.Queue[bool]

            work_thread = threading.Thread(
                target=_render_continuously,
                args=(stdout, stderr, command.scenarios_dir, stop),
            )

            prefix = "In the main"
            work_thread.start()
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                print(f"{prefix}: Got a keyboard interrupt.", file=stdout)
            finally:
                print(f"{prefix}: Sending a stop from the main thread...", file=stdout)
                stop.put(True)
                print(
                    f"{prefix}: Waiting for the work thread in main to join...",
                    file=stdout,
                )
                work_thread.join()

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
