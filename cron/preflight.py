"""Read-only deployment check before a scheduled game sweep."""

import os
import sys

from dotenv import load_dotenv

from db.client import _cursor


def check_config() -> int:
    load_dotenv()
    required = ("DISCORD_BOT_TOKEN", "OWNER_ID", "ITAD_API_KEY")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise EnvironmentError("Missing required settings: " + ", ".join(missing))
    with _cursor() as cur:
        cur.execute("SELECT email FROM allowed_users LIMIT 0")
        cur.execute("SELECT counts FROM ops.job_runs LIMIT 0")
        cur.execute("SELECT count(*) AS count FROM games")
        return cur.fetchone()["count"]


if __name__ == "__main__":
    try:
        count = check_config()
    except Exception as exc:
        # Connection exceptions can contain hosts, usernames or DSNs.
        print(
            f"Preflight failed ({type(exc).__name__}). Check secrets and migrations.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Configuration and database ready: {count} tracked game(s).")
