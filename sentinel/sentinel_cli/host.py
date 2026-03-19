"""sentinel_cli.host — Target/host management commands."""

from sentinel_cli.base import SentinelCommand, SentinelLister, SentinelShowOne, _get_client


class ListHosts(SentinelLister):
    "List all registered sentinel-targets."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("--status", default=None, help="Filter by status (active/inactive/unknown).")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        params = {}
        if parsed_args.status:
            params["status_filter"] = parsed_args.status
        targets = client.get("/targets", params=params or None)
        columns = ("target_id", "hostname", "status", "last_heartbeat")
        rows = [(t["target_id"], t["hostname"], t["status"], t.get("last_heartbeat", "")) for t in targets]
        return columns, rows


class ShowHost(SentinelShowOne):
    "Show details of a specific target."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("target_id", help="target_id or UUID of the target.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        target = client.get(f"/targets/{parsed_args.target_id}")
        columns = ("id", "target_id", "hostname", "target_type", "status", "last_heartbeat", "created_at")
        data = tuple(target.get(c, "") for c in columns)
        return columns, data


class RegisterHost(SentinelCommand):
    "Update description or labels on an existing target."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("target_id", help="target_id or UUID of the target.")
        p.add_argument("--description", default=None)
        p.add_argument("--label", action="append", metavar="KEY=VALUE", default=[],
                       help="Label to set (repeatable). Example: --label env=prod")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        data = {}
        if parsed_args.description is not None:
            data["description"] = parsed_args.description
        if parsed_args.label:
            labels = {}
            for kv in parsed_args.label:
                k, _, v = kv.partition("=")
                labels[k.strip()] = v.strip()
            data["labels"] = labels
        if not data:
            print("Nothing to update.")
            return
        target = client.patch(f"/targets/{parsed_args.target_id}", data)
        print(f"Updated target {target['target_id']} ({target['hostname']})")


class DeleteHost(SentinelCommand):
    "Remove a target from the registry."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("target_id", help="target_id or UUID of the target.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete target '{parsed_args.target_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(f"/targets/{parsed_args.target_id}")
        print(f"Target '{parsed_args.target_id}' deleted.")
