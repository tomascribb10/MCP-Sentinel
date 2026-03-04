"""sentinel_cli.policy — Role binding (policy) management commands."""

from sentinel_cli.base import SentinelCommand, SentinelLister, SentinelShowOne, _get_client


class ListPolicies(SentinelLister):
    "List all role bindings (policies)."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument(
            "--principal",
            default=None,
            metavar="ID",
            help="Filter by principal (initiator) ID.",
        )
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        params = {}
        if parsed_args.principal:
            params["principal_id"] = parsed_args.principal
        policies = client.get("/policies", params=params or None)
        columns = ("id", "principal_id", "command_set_id", "target_group_id")
        rows = [
            (
                p["id"],
                p["principal_id"],
                p["command_set_id"],
                p.get("target_group_id") or "(any)",
            )
            for p in policies
        ]
        return columns, rows


class ShowPolicy(SentinelShowOne):
    "Show details of a specific policy."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("policy_id", help="UUID of the policy (role binding).")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        p = client.get(f"/policies/{parsed_args.policy_id}")
        columns = ("id", "principal_id", "command_set_id", "target_group_id", "created_at")
        data = tuple(p.get(c, "") or "" for c in columns)
        return columns, data


class CreatePolicy(SentinelShowOne):
    "Create a new role binding granting a principal access to a command set."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("principal_id", help="ID of the principal (MCP client / user).")
        p.add_argument("command_set_id", help="UUID of the command set to grant.")
        p.add_argument(
            "--target-group",
            default=None,
            metavar="GROUP_ID",
            help="Restrict policy to agents in this group (omit = all agents).",
        )
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        data = {
            "principal_id": parsed_args.principal_id,
            "command_set_id": parsed_args.command_set_id,
            "target_group_id": parsed_args.target_group,
        }
        policy = client.post("/policies", data)
        columns = ("id", "principal_id", "command_set_id", "target_group_id")
        return columns, tuple(policy.get(c, "") or "" for c in columns)


class DeletePolicy(SentinelCommand):
    "Delete a role binding (policy)."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("policy_id", help="UUID of the policy to delete.")
        p.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
        return p

    def take_action(self, parsed_args):
        if not parsed_args.yes:
            confirm = input(f"Delete policy '{parsed_args.policy_id}'? [y/N] ")
            if confirm.lower() != "y":
                print("Aborted.")
                return
        client = _get_client(parsed_args)
        client.delete(f"/policies/{parsed_args.policy_id}")
        print(f"Policy '{parsed_args.policy_id}' deleted.")
