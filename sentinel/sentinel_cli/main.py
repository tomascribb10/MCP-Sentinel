"""
sentinel_cli.main
==================
Entry point for the sentinel CLI (cliff-based).

Usage:
    sentinel <command> [options]

Global options (also via env vars):
    --api-url   Admin API URL  (SENTINEL_API_URL, default: http://localhost:8001)
"""

import sys

from cliff.app import App
from cliff.commandmanager import CommandManager


class SentinelApp(App):
    def __init__(self) -> None:
        super().__init__(
            description="MCP-Sentinel — Zero Trust infrastructure management CLI",
            version="0.1.0",
            command_manager=CommandManager("sentinel"),
            deferred_help=True,
        )

    def build_option_parser(self, description, version):
        parser = super().build_option_parser(description, version)
        parser.add_argument(
            "--api-url",
            metavar="URL",
            default=None,
            help="Admin API base URL (overrides SENTINEL_API_URL env var).",
        )
        return parser

    def initialize_app(self, argv):
        pass

    def prepare_to_run_command(self, cmd):
        pass

    def clean_up(self, cmd, result, err):
        pass


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    app = SentinelApp()
    return app.run(argv)


if __name__ == "__main__":
    sys.exit(main())
