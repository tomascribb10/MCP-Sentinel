"""sentinel_cli.host — Agent/host management commands."""

from sentinel_cli.base import SentinelCommand, SentinelLister, SentinelShowOne, _get_client


class ListHosts(SentinelLister):
    "List all registered sentinel-agents."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("--status", default=None, help="Filter by status (active/inactive/unknown).")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        params = {}
        if parsed_args.status:
            params["status_filter"] = parsed_args.status
        agents = client.get("/agents", params=params or None)
        columns = ("agent_id", "hostname", "status", "last_heartbeat")
        rows = [(a["agent_id"], a["hostname"], a["status"], a.get("last_heartbeat", "")) for a in agents]
        return columns, rows


class ShowHost(SentinelShowOne):
    "Show details of a specific agent."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("agent_id", help="agent_id or UUID of the agent.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        agent = client.get(f"/agents/{parsed_args.agent_id}")
        columns = ("id", "agent_id", "hostname", "status", "last_heartbeat", "created_at")
        data = tuple(agent.get(c, "") for c in columns)
        return columns, data


class RegisterHost(SentinelCommand):
    "Update description or labels on an existing agent."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("agent_id", help="agent_id or UUID of the agent.")
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
        agent = client.patch(f"/agents/{parsed_args.agent_id}", data)
        print(f"Updated agent {agent['agent_id']} ({agent['hostname']})")


class DeleteHost(SentinelCommand):
    "Remove an agent from the registry."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("agent_id", help="agent_id or UUID of the agent.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete agent '{parsed_args.agent_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(f"/agents/{parsed_args.agent_id}")
        print(f"Agent '{parsed_args.agent_id}' deleted.")
