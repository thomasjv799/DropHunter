# Split Sweep + Self-Hosted Watch Workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the **game** price sweep on the existing GitHub-hosted runner (ITAD API works from datacenter IPs) and the **watch** sweep on a self-hosted runner on the Mac mini (residential IP, so Swiss Time House's Cloudflare doesn't 403 it), by splitting `cron.price_check` into independently runnable halves.

**Architecture:** `cron/price_check.py` keeps one entrypoint but gains `--games`/`--watches` flags (no flags = both, preserving local/manual behaviour). Two scheduled workflows call the appropriate flag: the existing `price_check.yml` (GitHub-hosted) runs `--games`; a new `watch_check.yml` (`runs-on: self-hosted`) runs `--watches`. A single self-hosted runner on the Mac mini executes the watch workflow.

**Tech Stack:** Python 3.11/3.12, pytest + pytest-mock, GitHub Actions (hosted + self-hosted runner), the existing `cloudscraper`-based `utils/watches.py`.

**Why this exists:** The 12-hour GitHub-hosted sweep logs `403 Client Error: Forbidden` when fetching Swiss Time House — Cloudflare blocks GitHub's datacenter IP ranges. `cloudscraper` succeeds from a residential IP (verified locally and on the Mac mini). Splitting lets each half run where it works.

---

## File Structure

- `cron/price_check.py` (modify) — extract `sweep_games()` and `sweep_watches()` from `run()`; add `run(games=True, watches=True)`; add `_parse_scope(argv)`; update `__main__` to use it. Single responsibility per function; `run()` stays the "both" orchestrator.
- `tests/test_cron.py` (modify) — add tests for `_parse_scope`, `run(games-only)`, `run(watches-only)`. Existing `test_run_checks_all_games` / `test_run_checks_watches_too` must keep passing (they call `run()` with no args = both).
- `.github/workflows/price_check.yml` (modify) — append `--games` to the run command; rename to "Game Price Check".
- `.github/workflows/watch_check.yml` (create) — self-hosted, 12h schedule, `--watches`, venv-based deps.
- No DB or fixture changes.

---

## Task 1: Split the sweep into games/watches with CLI flags

**Files:**
- Modify: `cron/price_check.py`
- Test: `tests/test_cron.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cron.py`:

```python
def test_parse_scope_no_flags_runs_both():
    from cron.price_check import _parse_scope
    assert _parse_scope([]) == (True, True)


def test_parse_scope_games_only():
    from cron.price_check import _parse_scope
    assert _parse_scope(["--games"]) == (True, False)


def test_parse_scope_watches_only():
    from cron.price_check import _parse_scope
    assert _parse_scope(["--watches"]) == (False, True)


def test_parse_scope_both_flags():
    from cron.price_check import _parse_scope
    assert _parse_scope(["--games", "--watches"]) == (True, True)


def test_run_games_only_skips_watches(mocker):
    from cron.price_check import run
    mock_games = mocker.patch("cron.price_check.get_games", return_value=[])
    mock_watches = mocker.patch("cron.price_check.get_watches", return_value=[])
    run(games=True, watches=False)
    mock_games.assert_called_once()
    mock_watches.assert_not_called()


def test_run_watches_only_skips_games(mocker):
    from cron.price_check import run
    mock_games = mocker.patch("cron.price_check.get_games", return_value=[])
    mock_watches = mocker.patch("cron.price_check.get_watches", return_value=[])
    run(games=False, watches=True)
    mock_watches.assert_called_once()
    mock_games.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_cron.py -k "parse_scope or only" -v`
Expected: FAIL — `ImportError: cannot import name '_parse_scope'` and `TypeError: run() got an unexpected keyword argument 'games'`.

- [ ] **Step 3: Refactor `cron/price_check.py`**

Add `import sys` to the top imports (with the existing imports). Replace the current `run()` function and the `if __name__ == "__main__":` block with:

```python
def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def sweep_games() -> None:
    games = get_games()
    logger.info("Checking prices for %d game(s)...", len(games))
    for game in games:
        try:
            process_game(game)
        except Exception as exc:
            logger.error("[%s] ERROR: %s", game["title"], exc, exc_info=True)


def sweep_watches() -> None:
    watches = get_watches()
    logger.info("Checking prices for %d watch(es)...", len(watches))
    for watch in watches:
        try:
            process_watch(watch)
        except Exception as exc:
            logger.error("[%s] ERROR: %s", watch["name"], exc, exc_info=True)


def run(games: bool = True, watches: bool = True) -> None:
    _configure_logging()
    if games:
        sweep_games()
    if watches:
        sweep_watches()
    logger.info("Price check run complete.")


def _parse_scope(argv: list) -> tuple:
    """Return (run_games, run_watches). No --games/--watches flag means run both."""
    flags = set(argv)
    if "--games" in flags or "--watches" in flags:
        return ("--games" in flags, "--watches" in flags)
    return (True, True)


if __name__ == "__main__":
    run_games, run_watches = _parse_scope(sys.argv[1:])
    run(games=run_games, watches=run_watches)
```

- [ ] **Step 4: Run the new tests**

Run: `python3 -m pytest tests/test_cron.py -k "parse_scope or only" -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the full cron test file (no regressions)**

Run: `python3 -m pytest tests/test_cron.py -v`
Expected: all PASS — including the pre-existing `test_run_checks_all_games` and `test_run_checks_watches_too` (both call `run()` with no args, which still sweeps both).

- [ ] **Step 6: Smoke-test the flags locally**

Run: `python3 -m cron.price_check --games`
Expected: logs "Checking prices for N game(s)..." and "Price check run complete." with **no** "Checking prices for N watch(es)..." line.

Run: `python3 -m cron.price_check --watches`
Expected: logs only the watch sweep, then "Price check run complete."

- [ ] **Step 7: Lint and commit**

Run: `python3 -m ruff check cron/price_check.py tests/test_cron.py`
Expected: no NEW errors on changed lines (≤100 chars; no `# noqa`).

```bash
git add cron/price_check.py tests/test_cron.py
git commit -m "feat: split price sweep into --games/--watches flags"
```

---

## Task 2: Point the GitHub-hosted workflow at games only

**Files:**
- Modify: `.github/workflows/price_check.yml`

- [ ] **Step 1: Update the workflow**

Edit `.github/workflows/price_check.yml`. Change the workflow `name` and the final run command:

- Change `name: Price Check` to `name: Game Price Check`.
- Change the last step's command from `run: python -m cron.price_check` to:

```yaml
        run: python -m cron.price_check --games
```

Leave everything else as-is: `runs-on: ubuntu-latest`, the `0 */12 * * *` schedule, `workflow_dispatch`, and all existing `env:` secrets (games need `ITAD_API_KEY`, `SUPABASE_*`, `DISCORD_WEBHOOK_URL`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `AI_PROVIDER`).

- [ ] **Step 2: Validate YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/price_check.yml'))" && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/price_check.yml
git commit -m "ci: game sweep workflow runs --games only"
```

---

## Task 3: Add the self-hosted watch workflow

**Files:**
- Create: `.github/workflows/watch_check.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/watch_check.yml`:

```yaml
name: Watch Price Check

on:
  schedule:
    - cron: "30 */12 * * *"   # every 12h, offset 30 min from the game sweep
  workflow_dispatch:

jobs:
  check-watches:
    runs-on: self-hosted      # runs on the Mac mini (residential IP, passes Cloudflare)

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up venv and install dependencies
        run: |
          python3 -m venv .venv
          .venv/bin/pip install --upgrade pip
          .venv/bin/pip install -r requirements.txt

      - name: Run watch sweep
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          AI_PROVIDER: ${{ secrets.AI_PROVIDER }}
        run: .venv/bin/python -m cron.price_check --watches
```

Notes baked into this choice:
- A self-contained `.venv` avoids depending on / polluting the Mac mini's system Python (it has 3.12; `cloudscraper`+`beautifulsoup4` install cleanly).
- `ITAD_API_KEY` is intentionally omitted — the watch sweep never calls ITAD.
- Only `schedule` + `workflow_dispatch` triggers (never `pull_request`), so fork PRs cannot run code on the self-hosted runner.

- [ ] **Step 2: Validate YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/watch_check.yml'))" && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/watch_check.yml
git commit -m "ci: add self-hosted watch sweep workflow (--watches)"
```

---

## Task 4: Install and harden the self-hosted runner on the Mac mini (ops — manual)

This task runs on the **Mac mini**, not in CI. It has no unit tests; verification is via the runner showing "Idle" on GitHub. The full rationale is in `docs/superpowers/plans/2026-04-30-mac-mini-auto-deploy.md` — this reuses the **same** runner for the watch sweep.

- [ ] **Step 1: Register the runner**

On GitHub: repo → **Settings → Actions → Runners → New self-hosted runner → Linux / x64**. Copy the exact commands GitHub shows (they include a one-time token), then on the Mac mini:

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
# paste GitHub's exact curl + tar lines for the current runner version, then:
./config.sh --url https://github.com/thomasjv799/DropHunter --token <TOKEN_FROM_GITHUB>
```
Accept defaults; optionally name it `mac-mini`.

- [ ] **Step 2: Run it as a boot service**

```bash
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status     # expect: active (running)
```
Verify on GitHub: Settings → Actions → Runners shows the runner **Idle / green**.

- [ ] **Step 3: Harden (public-repo safety)**

Because the repo is **public**, a self-hosted runner is a known risk (a malicious fork PR could execute on your box). Apply both:
- Repo → **Settings → Actions → General → Fork pull request workflows from outside collaborators** → set to **"Require approval for all outside collaborators"** (default; confirm it's on).
- Confirm no workflow on this repo runs on `pull_request` with `runs-on: self-hosted` (only `watch_check.yml` is self-hosted, and it has no `pull_request` trigger).

Expected: the runner only ever executes `watch_check.yml` (schedule/manual) and any push-triggered deploy you add later.

- [ ] **Step 4: Confirm the runner's IP passes Cloudflare**

On the Mac mini:
```bash
cd /home/thomas/repos/DropHunter
docker run --rm --env-file .env drophunter \
  python -c "from utils.watches import fetch_swisstimehouse; print(fetch_swisstimehouse('https://www.swisstimehouse.com/casio-g1714'))"
```
Expected: a dict (e.g. `{'name': 'Casio G1714 ...', 'price': 34997.0, ...}`), **not** `None`. If `None`/403, the Mac mini's IP is also blocked — stop and revisit (residential proxy / FlareSolverr) before relying on the workflow.

---

## Task 5: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Trigger the watch workflow manually**

GitHub → **Actions → Watch Price Check → Run workflow** (on `main`). It should pick the `self-hosted` runner.

- [ ] **Step 2: Confirm the fetch succeeds (no 403)**

In the run logs, the `Run watch sweep` step should show `[<watch name>] Current ...` / a deal evaluation, **not** `WARNING drophunter.watches: Failed to fetch swisstimehouse URL ...: 403`.

- [ ] **Step 3: Confirm the game workflow still works**

GitHub → **Actions → Game Price Check → Run workflow**. Logs should show only the game sweep (no watch lines) and complete cleanly on `ubuntu-latest`.

- [ ] **Step 4: Confirm no double-sweeping of either type**

The game workflow runs `--games` (no watch processing); the watch workflow runs `--watches` (no game processing). Each price type is swept in exactly one place.

---

## Self-Review Notes (coverage)

- Split into `--games`/`--watches`, default both, testable `_parse_scope` → Task 1 ✓
- Existing `run()`-with-no-args tests stay green (both) → Task 1 Step 5 ✓
- GitHub-hosted workflow → games only → Task 2 ✓
- Self-hosted workflow → watches only, no `pull_request` trigger, no ITAD secret → Task 3 ✓
- Self-hosted runner install + public-repo hardening + IP check → Task 4 ✓
- E2E: watch fetch no longer 403s; games still run; no double-sweep → Task 5 ✓
- Function names consistent across tasks: `sweep_games`, `sweep_watches`, `run(games, watches)`, `_parse_scope` ✓
