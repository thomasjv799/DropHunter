"""Trusted owner-only CLI. No public account-linking endpoint."""

import argparse
import re
from uuid import UUID

from dotenv import load_dotenv

from web.repository import Repository


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Approve/revoke DropHunter web access")
    parser.add_argument("action", choices=["approve", "revoke"])
    parser.add_argument("auth_id", type=UUID, help="Verified UUID from Supabase Auth Users")
    parser.add_argument(
        "--discord-id", help="Existing permitted Discord ID; verify ownership first"
    )
    parser.add_argument("--by", required=True, help="Administrator identifier for the audit record")
    args = parser.parse_args()
    if args.action == "approve" and not re.fullmatch(r"[0-9]{5,25}", args.discord_id or ""):
        parser.error("--discord-id must be an existing verified Discord user ID")
    with Repository().cursor() as cur:
        if args.action == "approve":
            cur.execute(
                """INSERT INTO dashboard.accounts
              (auth_id,discord_id,approved,approved_at,approved_by)
              VALUES (%s,%s,true,now(),%s) ON CONFLICT (auth_id) DO UPDATE
              SET discord_id=EXCLUDED.discord_id,approved=true,approved_at=now(),
              approved_by=EXCLUDED.approved_by,updated_at=now()""",
                (str(args.auth_id), args.discord_id, args.by),
            )
        else:
            cur.execute(
                """UPDATE dashboard.accounts SET approved=false,
              approved_by=%s,updated_at=now() WHERE auth_id=%s""",
                (args.by, str(args.auth_id)),
            )
        print(f"{args.action}: {cur.rowcount} account(s) updated")


if __name__ == "__main__":
    main()
