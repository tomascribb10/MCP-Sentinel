"""sentinel_cli.login — Login and logout commands."""

import getpass
import os
import sys

from sentinel_cli.base import SentinelCommand, _get_client
from sentinel_cli.client import AdminAPIClient, APIError


class Login(SentinelCommand):
    "Authenticate to the Admin API and save token to ~/.sentinel/token."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("-u", "--username", default=os.environ.get("SENTINEL_USER", "admin"))
        p.add_argument("-p", "--password", default=os.environ.get("SENTINEL_PASSWORD"))
        return p

    def take_action(self, parsed_args):
        password = parsed_args.password or getpass.getpass(
            f"Password for {parsed_args.username}: "
        )
        client = _get_client(parsed_args)
        try:
            client.login(parsed_args.username, password)
        except APIError as exc:
            print(f"Login failed: {exc.detail}", file=sys.stderr)
            sys.exit(1)
        print(f"Logged in as {parsed_args.username}. Token saved to ~/.sentinel/token")


class Logout(SentinelCommand):
    "Remove the cached authentication token."

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        client.clear_token()
        print("Token removed.")
