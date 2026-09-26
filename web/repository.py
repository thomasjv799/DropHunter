"""Scoped web queries. Each operation owns its connection and transaction."""

import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor


class Repository:
    @contextmanager
    def cursor(self):
        schema = os.environ.get("DB_SCHEMA", "public")
        if schema not in ("public", "drophunter"):
            raise ValueError("Unsupported database schema")
        dsn = os.environ.get("DATABASE_URL") or os.environ.get("LOCAL_DB_URL")
        if not dsn:
            raise ValueError("Database is not configured")
        conn = psycopg2.connect(
            dsn,
            connect_timeout=10,
            options=f"-c search_path=pg_catalog,{schema} -c statement_timeout=10000",
        )
        try:
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    yield cur
        finally:
            conn.close()

    def account(self, auth_id):
        with self.cursor() as cur:
            cur.execute(
                "SELECT discord_id, approved FROM dashboard.accounts "
                "WHERE auth_id=%s AND approved=true",
                (auth_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            if row["discord_id"] != os.environ.get("OWNER_ID"):
                cur.execute("SELECT 1 FROM allowed_users WHERE user_id=%s", (row["discord_id"],))
                if not cur.fetchone():
                    return None
            return dict(row)

    def list_games(self, user, query="", status="all", sort="name", page=1, limit=10):
        orders = {
            "name": "lower(title),id",
            "price": "price ASC NULLS LAST,id",
            "gap": "(price-target_price) ASC NULLS LAST,id",
        }
        condition = {
            "all": "true",
            "deal": "price <= target_price",
            "watching": "(price > target_price OR target_price IS NULL)",
            "unknown": "price IS NULL",
        }[status]
        cte = """WITH latest AS (
          SELECT g.id,g.title,g.target_price,g.added_at,h.price,h.regular_price,h.store,h.fetched_at
          FROM games g LEFT JOIN LATERAL (
            SELECT price,regular_price,store,fetched_at FROM price_history
            WHERE game_id=g.id ORDER BY fetched_at DESC,id DESC LIMIT 1
          ) h ON true WHERE g.user_id=%s
        ), filtered AS (SELECT * FROM latest WHERE strpos(lower(title),lower(%s))>0 AND """
        with self.cursor() as cur:
            cur.execute(cte + condition + ") SELECT count(*) AS n FROM filtered", (user, query))
            total = cur.fetchone()["n"]
            cur.execute(
                cte
                + condition
                + ") SELECT * FROM filtered ORDER BY "
                + orders[sort]
                + " LIMIT %s OFFSET %s",
                (user, query, limit, (page - 1) * limit),
            )
            return {
                "items": [dict(r) for r in cur.fetchall()],
                "total": total,
                "page": page,
                "limit": limit,
            }

    def summary(self, user):
        with self.cursor() as cur:
            cur.execute(
                """SELECT count(*) AS games,
              count(*) FILTER (WHERE h.price<=g.target_price) AS at_target,
              count(*) FILTER (WHERE h.price IS NULL) AS unknown,
              count(*) FILTER (WHERE h.fetched_at < now()-interval '24 hours') AS stale,
              max(h.fetched_at) AS last_observed
              FROM games g LEFT JOIN LATERAL (
                SELECT price,fetched_at FROM price_history WHERE game_id=g.id
                ORDER BY fetched_at DESC,id DESC LIMIT 1
              ) h ON true WHERE g.user_id=%s""",
                (user,),
            )
            return dict(cur.fetchone())

    def game(self, user, game_id):
        with self.cursor() as cur:
            cur.execute(
                "SELECT id,title,target_price FROM games WHERE id=%s AND user_id=%s",
                (game_id, user),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def history(self, user, game_id, days):
        with self.cursor() as cur:
            cur.execute(
                """SELECT h.price,h.regular_price,h.store,h.fetched_at
              FROM price_history h JOIN games g ON g.id=h.game_id
              WHERE g.user_id=%s AND g.id=%s AND h.fetched_at>=now()-(%s*interval '1 day')
              ORDER BY h.fetched_at,h.id LIMIT 1000""",
                (user, game_id, days),
            )
            return [dict(r) for r in cur.fetchall()]

    def update_game(self, user, game_id, target):
        with self.cursor() as cur:
            cur.execute(
                "UPDATE games SET target_price=%s WHERE id=%s AND user_id=%s RETURNING id",
                (target, game_id, user),
            )
            return cur.fetchone() is not None

    def remove_game(self, user, game_id):
        with self.cursor() as cur:
            cur.execute(
                "DELETE FROM games WHERE id=%s AND user_id=%s RETURNING id", (game_id, user)
            )
            return cur.fetchone() is not None

    def add_game(self, user, title, itad_id, target):
        with self.cursor() as cur:
            # Serialize additions per user so parallel requests cannot exceed the limit.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("dashboard:" + user,))
            cur.execute("SELECT id FROM games WHERE user_id=%s AND itad_id=%s", (user, itad_id))
            existing = cur.fetchone()
            if existing:
                return {"id": str(existing["id"]), "existing": True}
            cur.execute("SELECT count(*) AS n FROM games WHERE user_id=%s", (user,))
            if cur.fetchone()["n"] >= 100:
                raise ValueError("You can track up to 100 games.")
            cur.execute(
                """INSERT INTO games (user_id,title,itad_id,target_price)
              VALUES (%s,%s,%s,%s) RETURNING id""",
                (user, title, itad_id, target),
            )
            return dict(cur.fetchone())

    def watches(self, user):
        with self.cursor() as cur:
            cur.execute(
                """SELECT w.id,w.name,w.brand,w.target_price,h.swisstimehouse_price AS price,
                h.fetched_at FROM watches w LEFT JOIN LATERAL (
                SELECT swisstimehouse_price,fetched_at FROM watch_price_history WHERE watch_id=w.id
                ORDER BY fetched_at DESC,id DESC LIMIT 1) h ON true
                WHERE w.user_id=%s ORDER BY w.name LIMIT 100""",
                (user,),
            )
            return [dict(r) for r in cur.fetchall()]

    def activity(self, user):
        with self.cursor() as cur:
            cur.execute(
                """SELECT g.title,n.price,n.notified_at FROM notifications_log n
              JOIN games g ON g.id=n.game_id WHERE g.user_id=%s
              ORDER BY n.notified_at DESC LIMIT 50""",
                (user,),
            )
            return [dict(r) for r in cur.fetchall()]

    def settings(self, user):
        with self.cursor() as cur:
            cur.execute("SELECT email FROM allowed_users WHERE user_id=%s", (user,))
            row = cur.fetchone()
            return {"email": row["email"] if row else None}

    def set_email(self, user, email):
        with self.cursor() as cur:
            if user == os.environ.get("OWNER_ID"):
                cur.execute(
                    """INSERT INTO allowed_users (user_id,email) VALUES (%s,%s)
                    ON CONFLICT (user_id) DO UPDATE SET email=EXCLUDED.email""",
                    (user, email),
                )
            else:
                cur.execute("UPDATE allowed_users SET email=%s WHERE user_id=%s", (email, user))
                if not cur.rowcount:
                    raise PermissionError("Your access was revoked. Contact the owner.")
