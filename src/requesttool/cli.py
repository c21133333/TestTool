import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="requesttool")
    parser.add_argument("--version", action="store_true", help="Show version and exit")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the web server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto reload")

    migrate_parser = subparsers.add_parser("migrate", help="Apply database migrations")
    migrate_parser.add_argument("--revision", default="head", help="Alembic revision target")

    worker_parser = subparsers.add_parser("worker", help="Run the suite execution worker")
    worker_parser.add_argument("--once", action="store_true", help="Process a single pending execution and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    effective_argv = list(argv) if argv is not None else list(sys.argv[1:])
    if not effective_argv:
        effective_argv = ["serve"]
    args = parser.parse_args(effective_argv)
    if args.version:
        from . import __version__

        print(__version__)
        return 0
    command = args.command or "serve"
    if command == "serve":
        return _run_server(host=args.host, port=args.port, reload=args.reload)
    if command == "migrate":
        return _run_migrations(revision=args.revision)
    if command == "worker":
        return _run_worker(run_once=args.once)
    parser.print_help()
    return 0


def _run_server(*, host: str, port: int, reload: bool) -> int:
    import uvicorn

    uvicorn.run("backend.main:app", host=host, port=port, reload=reload)
    return 0


def _run_worker(*, run_once: bool) -> int:
    from backend.app.worker import main as worker_main
    from backend.app.worker import run_once as worker_run_once

    if run_once:
        return 0 if worker_run_once() else 1
    return worker_main()


def _run_migrations(*, revision: str) -> int:
    from backend.app.core.database import run_migrations

    run_migrations(revision=revision)
    return 0
