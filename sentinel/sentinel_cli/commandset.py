"""sentinel_cli.commandset — Command set and command management commands."""

import json

from sentinel_cli.base import SentinelCommand, SentinelLister, SentinelShowOne, _get_client


class ListCommandSets(SentinelLister):
    "List all command sets."

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        css = client.get("/command-sets")
        columns = ("id", "name", "driver", "description")
        rows = [(cs["id"], cs["name"], cs["driver"], cs.get("description", "")) for cs in css]
        return columns, rows


class ShowCommandSet(SentinelShowOne):
    "Show details of a command set (including its commands)."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("command_set_id", help="UUID of the command set.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        cs = client.get(f"/command-sets/{parsed_args.command_set_id}")
        # Flatten commands list for display
        commands = cs.get("commands", [])
        cmd_summary = ", ".join(
            f"{c['name']}({'2FA' if c.get('require_2fa') else 'no-2FA'})"
            for c in commands
        ) or "(none)"
        columns = ("id", "name", "driver", "description", "commands")
        data = (
            cs.get("id", ""),
            cs.get("name", ""),
            cs.get("driver", ""),
            cs.get("description", ""),
            cmd_summary,
        )
        return columns, data


class CreateCommandSet(SentinelShowOne):
    "Create a new command set."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("name", help="Unique name for the command set.")
        p.add_argument(
            "--driver",
            default="posix_bash",
            help="Execution driver (default: posix_bash).",
        )
        p.add_argument("--description", default=None)
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        data = {"name": parsed_args.name, "driver": parsed_args.driver}
        if parsed_args.description:
            data["description"] = parsed_args.description
        cs = client.post("/command-sets", data)
        columns = ("id", "name", "driver", "description")
        return columns, tuple(cs.get(c, "") for c in columns)


class DeleteCommandSet(SentinelCommand):
    "Delete a command set."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("command_set_id", help="UUID of the command set.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete command set '{parsed_args.command_set_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(f"/command-sets/{parsed_args.command_set_id}")
        print(f"Command set '{parsed_args.command_set_id}' deleted.")


class ListCommands(SentinelLister):
    "List commands within a command set."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("command_set_id", help="UUID of the command set.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        cs = client.get(f"/command-sets/{parsed_args.command_set_id}")
        commands = cs.get("commands", [])
        columns = ("id", "name", "binary", "args_regex", "require_2fa")
        rows = [
            (
                c["id"],
                c["name"],
                c["binary"],
                c.get("args_regex", ""),
                c.get("require_2fa", False),
            )
            for c in commands
        ]
        return columns, rows


class AddCommand(SentinelShowOne):
    "Add a command to a command set."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("command_set_id", help="UUID of the command set.")
        p.add_argument("name", help="Logical name for the command (e.g. restart_nginx).")
        p.add_argument("binary", help="Absolute path to the binary (e.g. /usr/bin/systemctl).")
        p.add_argument(
            "--args-regex",
            default=".*",
            help="Regex whitelist for allowed arguments (default: .*).",
        )
        p.add_argument(
            "--require-2fa",
            action="store_true",
            default=False,
            help="Require human 2FA approval before execution.",
        )
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        data = {
            "name": parsed_args.name,
            "binary": parsed_args.binary,
            "args_regex": parsed_args.args_regex,
            "require_2fa": parsed_args.require_2fa,
        }
        cmd = client.post(f"/command-sets/{parsed_args.command_set_id}/commands", data)
        columns = ("id", "name", "binary", "args_regex", "require_2fa")
        return columns, tuple(cmd.get(c, "") for c in columns)


class DeleteCommand(SentinelCommand):
    "Remove a command from a command set."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("command_set_id", help="UUID of the command set.")
        p.add_argument("command_id", help="UUID of the command to remove.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete command '{parsed_args.command_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(
            f"/command-sets/{parsed_args.command_set_id}/commands/{parsed_args.command_id}"
        )
        print(f"Command '{parsed_args.command_id}' deleted.")
