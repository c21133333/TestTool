from __future__ import annotations

from requesttool.cli import build_parser


def test_cli_supports_web_first_commands():
    parser = build_parser()

    serve_args = parser.parse_args(["serve", "--host", "0.0.0.0", "--port", "9000", "--reload"])
    migrate_args = parser.parse_args(["migrate", "--revision", "head"])
    worker_args = parser.parse_args(["worker", "--once"])

    assert serve_args.command == "serve"
    assert serve_args.host == "0.0.0.0"
    assert serve_args.port == 9000
    assert serve_args.reload is True
    assert migrate_args.command == "migrate"
    assert migrate_args.revision == "head"
    assert worker_args.command == "worker"
    assert worker_args.once is True
