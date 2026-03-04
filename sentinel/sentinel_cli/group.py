"""sentinel_cli.group — Host group management commands."""

from sentinel_cli.base import SentinelCommand, SentinelLister, SentinelShowOne, _get_client


class ListGroups(SentinelLister):
    "List all host groups."

    def get_parser(self, prog_name):
        return super().get_parser(prog_name)

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        groups = client.get("/groups")
        columns = ("id", "name", "description")
        rows = [(g["id"], g["name"], g.get("description", "")) for g in groups]
        return columns, rows


class ShowGroup(SentinelShowOne):
    "Show details of a specific host group."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("group_id", help="UUID of the group.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        g = client.get(f"/groups/{parsed_args.group_id}")
        columns = ("id", "name", "description", "created_at")
        data = tuple(g.get(c, "") for c in columns)
        return columns, data


class CreateGroup(SentinelShowOne):
    "Create a new host group."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("name", help="Unique name for the group.")
        p.add_argument("--description", default=None, help="Optional description.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        data = {"name": parsed_args.name}
        if parsed_args.description:
            data["description"] = parsed_args.description
        g = client.post("/groups", data)
        columns = ("id", "name", "description", "created_at")
        return columns, tuple(g.get(c, "") for c in columns)


class DeleteGroup(SentinelCommand):
    "Delete a host group."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("group_id", help="UUID of the group.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete group '{parsed_args.group_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(f"/groups/{parsed_args.group_id}")
        print(f"Group '{parsed_args.group_id}' deleted.")


class ListGroupMembers(SentinelLister):
    "List agents that belong to a host group."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("group_id", help="UUID of the group.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        agents = client.get(f"/groups/{parsed_args.group_id}/members")
        columns = ("agent_id", "hostname", "status")
        rows = [(a["agent_id"], a["hostname"], a["status"]) for a in agents]
        return columns, rows


class AddGroupMember(SentinelCommand):
    "Add an agent to a host group."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("group_id", help="UUID of the group.")
        p.add_argument("agent_id", help="agent_id or UUID of the agent to add.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        client.post(
            f"/groups/{parsed_args.group_id}/members",
            {"agent_id": parsed_args.agent_id},
        )
        print(f"Agent '{parsed_args.agent_id}' added to group '{parsed_args.group_id}'.")


class RemoveGroupMember(SentinelCommand):
    "Remove an agent from a host group."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("group_id", help="UUID of the group.")
        p.add_argument("agent_id", help="agent_id or UUID of the agent to remove.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        client.delete(f"/groups/{parsed_args.group_id}/members/{parsed_args.agent_id}")
        print(f"Agent '{parsed_args.agent_id}' removed from group '{parsed_args.group_id}'.")
