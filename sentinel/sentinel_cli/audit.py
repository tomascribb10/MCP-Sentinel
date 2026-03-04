"""sentinel_cli.audit — Audit log query commands."""

from sentinel_cli.base import SentinelLister, _get_client


class ListAuditLogs(SentinelLister):
    "Query the immutable audit log."

    def get_parser(self, prog_name):
        p = super().get_parser(prog_name)
        p.add_argument("--initiator", default=None, metavar="ID", help="Filter by initiator ID.")
        p.add_argument(
            "--agent",
            default=None,
            metavar="AGENT_ID",
            help="Filter by target agent ID.",
        )
        p.add_argument(
            "--outcome",
            default=None,
            choices=["success", "failure", "denied", "pending_2fa"],
            help="Filter by outcome.",
        )
        p.add_argument("--limit", type=int, default=50, help="Max results (default: 50).")
        p.add_argument("--offset", type=int, default=0, help="Pagination offset.")
        return p

    def take_action(self, parsed_args):
        client = _get_client(parsed_args)
        params = {
            "limit": parsed_args.limit,
            "offset": parsed_args.offset,
        }
        if parsed_args.initiator:
            params["initiator_id"] = parsed_args.initiator
        if parsed_args.agent:
            params["target_agent_id"] = parsed_args.agent
        if parsed_args.outcome:
            params["outcome"] = parsed_args.outcome

        logs = client.get("/audit-logs", params=params)
        columns = (
            "request_id",
            "initiator_id",
            "target_agent_id",
            "binary",
            "outcome",
            "exit_code",
            "created_at",
        )
        rows = [
            (
                log.get("request_id", ""),
                log.get("initiator_id", ""),
                log.get("target_agent_id", ""),
                log.get("binary", ""),
                log.get("outcome", ""),
                log.get("exit_code", ""),
                log.get("created_at", ""),
            )
            for log in logs
        ]
        return columns, rows
