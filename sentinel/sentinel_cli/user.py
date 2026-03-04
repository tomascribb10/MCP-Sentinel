"""sentinel_cli.user — Admin user management commands (superuser only)."""

import getpass

from sentinel_cli.base import SentinelCommand, SentinelLister, SentinelShowOne, _get_client


class ListUsers(SentinelLister):
    "List admin users (superuser only)."

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        users = client.get("/users")
        columns = ("id", "username", "is_superuser", "created_at")
        rows = [(u["id"], u["username"], u.get("is_superuser", False), u.get("created_at", ""))
                for u in users]
        return columns, rows


class CreateUser(SentinelShowOne):
    "Create a new admin user (superuser only)."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("username", help="Login username.")
        p.add_argument(
            "--superuser",
            action="store_true",
            default=False,
            help="Grant superuser privileges.",
        )
        p.add_argument(
            "--password",
            default=None,
            help="Password (prompted interactively if omitted).",
        )
        return p

    def take_action(self, parsed_args):
        password = parsed_args.password
        if not password:
            password = getpass.getpass(f"Password for '{parsed_args.username}': ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Error: passwords do not match.")
                import sys
                sys.exit(1)

        client = _get_client(parsed_args)
        data = {
            "username": parsed_args.username,
            "password": password,
            "is_superuser": parsed_args.superuser,
        }
        user = client.post("/users", data)
        columns = ("id", "username", "is_superuser", "created_at")
        return columns, tuple(user.get(c, "") for c in columns)


class DeleteUser(SentinelCommand):
    "Delete an admin user (superuser only)."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("user_id", help="UUID of the user to delete.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete user '{parsed_args.user_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(f"/users/{parsed_args.user_id}")
        print(f"User '{parsed_args.user_id}' deleted.")
