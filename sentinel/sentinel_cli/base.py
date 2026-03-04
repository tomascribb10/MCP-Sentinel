"""
sentinel_cli.base
==================
Shared base class for all sentinel CLI commands.

Provides a pre-built AdminAPIClient and consistent error handling.
"""

import os
import sys

from cliff.command import Command as BaseCommand
from cliff.lister import Lister as BaseLister
from cliff.show import ShowOne as BaseShowOne

from sentinel_cli.client import AdminAPIClient, APIError


def _get_client(parsed_args) -> AdminAPIClient:
    api_url = getattr(parsed_args, "api_url", None) or os.environ.get("SENTINEL_API_URL")
    return AdminAPIClient(api_url=api_url)


def _handle_api_error(exc: APIError) -> None:
    if exc.status_code == 401:
        print("Error: not authenticated. Run `sentinel login` first.", file=sys.stderr)
    elif exc.status_code == 404:
        print(f"Error: not found — {exc.detail}", file=sys.stderr)
    elif exc.status_code == 403:
        print(f"Error: forbidden — {exc.detail}", file=sys.stderr)
    else:
        print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)


class SentinelLister(BaseLister):
    def run(self, parsed_args):
        try:
            return super().run(parsed_args)
        except APIError as exc:
            _handle_api_error(exc)


class SentinelShowOne(BaseShowOne):
    def run(self, parsed_args):
        try:
            return super().run(parsed_args)
        except APIError as exc:
            _handle_api_error(exc)


class SentinelCommand(BaseCommand):
    def run(self, parsed_args):
        try:
            return super().run(parsed_args)
        except APIError as exc:
            _handle_api_error(exc)
