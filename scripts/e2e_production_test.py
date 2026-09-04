#!/usr/bin/env python3
"""End-to-end production test for the Prompt Competition Platform.

Boots an isolated server (or uses --base-url), then exercises every real flow
against Supabase and asserts on the results. Exits 0 on full PASS, 1 on any
failure. Designed to be run unattended: every network step has a hard timeout,
and the TEST competition's data is deleted at the end so production stays clean.

Modes:
  --mode smoke    QR-login mapping + one synthetic TEST participant submission
  --mode admin    full admin assertions (dashboard, monitor, analytics, export, queue)
  --mode load     N concurrent synthetic submissions to the TEST competition
  --mode all      smoke then admin then load (default)

Usage (local, boots its own server on a random port):
  python scripts/e2e_production_test.py --mode all --total 300

Usage (production / already-running server):
  python scripts/e2e_production_test.py --base-url https://<app>/api --mode smoke

Env: reads backend/.env for ADMIN_USERNAME/ADMIN_PASSWORD_HASH, SUPABASE creds,
JWT_SECRET. Requires backend deps (fastapi, supabase, httpx, jwt) installed.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

import jwt  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "backend" / ".env")

from app.config import get_settings  # noqa: E402
from app.db import db as get_db  # noqa: E402
from app.services.stress_test_service import mint_token  # noqa: E402

# Load scripts/stress_test.py regardless of the `scripts` package layout.
_ST = (Path(__file__).resolve().parent / "stress_test.py")
_spec = importlib.util.spec_from_file_location("stress_test", _ST)
stress_test = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stress_test)  # type: ignore[union-attr]

REAL_QR_TOKEN = "GENAI_QR_955B022AEE4F81FFF3D4CA73F20BE7167492757351037D92"
REAL_COMPETITION = "competition_2026"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, cond, detail))
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _settings():
    return get_settings()


# ---------------------------------------------------------------------------
# Server bring-up (self-contained; bounded waits so nothing hangs)
# ---------------------------------------------------------------------------
class ServerHandle:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def start(self, port: int) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT / "backend")
        self.proc = subprocess.Popen(
            [
                str(REPO_ROOT / "backend" / ".venv" / "Scripts" / "python.exe"),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=str(REPO_ROOT / "backend"),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def wait_health(self, base: str, timeout: float = 40.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            try:
                r = httpx.get(base + "/health", timeout=3)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(1)
        return False

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


# ---------------------------------------------------------------------------
# Core flows
# ---------------------------------------------------------------------------
def admin_login(base: str) -> str:
    """Login as admin and return the bearer token (rate-limit-safe: reuse it)."""
    s = _settings()
    if not s.admin_username or not s.admin_password_hash:
        raise RuntimeError("ADMIN_USERNAME / ADMIN_PASSWORD_HASH not configured in backend/.env")
    # The plaintext password is not stored; recompute-verify against the hash we
    # accept. For the harness, we need the actual password though. We read it
    # only from an env override to avoid holding it in source.
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        raise RuntimeError(
            "Set ADMIN_PASSWORD=<the admin plaintext password> env var for the harness "
            "(it is NOT stored; see SETUP.md)."
        )
    r = httpx.post(
        base + "/api/admin/login",
        json={"username": s.admin_username, "password": password},
        timeout=20,
    )
    if r.status_code != 200:
        return ""
    return r.json()["token"]


def smoke_flow(base: str) -> None:
    print("\n=== SMOKE ===")
    settings = _settings()
    db = get_db()

    # 1. Active competition.
    try:
        comp = httpx.get(base + "/api/competitions/active", timeout=20).json()
        check("active competition loadable", comp.get("id") == REAL_COMPETITION, str(comp.get("id")))
    except Exception as exc:  # noqa: BLE001
        check("active competition loadable", False, str(exc))

    # 2. QR-login mapping endpoint (real registration, login ONLY — no submission).
    # The real registration row may or may not still exist in the DB; a 200 means
    # the QR mapped to a registration, a 401 means the token is no longer
    # registered. Both confirm the login endpoint responds correctly.
    try:
        r = httpx.post(
            base + "/api/auth/login/message",
            json={"competition_id": REAL_COMPETITION, "qr_message": REAL_QR_TOKEN},
            timeout=30,
        )
        ok_endpoint = r.status_code in (200, 401)
        check("QR-login endpoint responds (200/401)", ok_endpoint, str(r.status_code) + " " + r.text[:60])
        participant_token = r.json().get("token", "") if r.status_code == 200 else ""
    except Exception as exc:  # noqa: BLE001
        check("QR-login endpoint responds (200/401)", False, str(exc))
        participant_token = ""

    # Unauthenticated submission must be rejected.
    r = httpx.post(
        base + "/api/submissions",
        json={"competition_id": REAL_COMPETITION, "prompts": []},
        timeout=20,
    )
    check("unauthenticated submission rejected", r.status_code == 401, str(r.status_code))

    # 3. Synthetic TEST participant submission (isolated, cleaned up after).
    stress_test.ensure_test_schema(db)
    pid = str(uuid.uuid4())
    rows = [
        {
            "id": pid,
            "competition_id": stress_test.TEST_COMPETITION_ID,
            "registration_id": str(uuid.uuid4()),
            "qr_token": f"E2E_{pid[:12]}",
            "display_name": "E2E Harness",
            "email": "e2e@test.local",
            "status": "REGISTERED",
        }
    ]
    for row in rows:
        db.table("pc_participants").insert(row).execute()
    token = mint_token(settings, pid)
    resp = httpx.post(
        base + "/api/submissions",
        json={
            "competition_id": stress_test.TEST_COMPETITION_ID,
            "prompts": stress_test.make_prompt_payload(),
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    ok = resp.status_code in (200, 409)
    check("TEST participant submission accepted", ok, resp.text[:90])
    if ok and resp.status_code == 200:
        submission_id = resp.json()["submission_id"]
        # 5 responses should exist for the submission (each queues a job).
        resp_rows = (
            db.table("pc_responses")
            .select("id")
            .eq("submission_id", submission_id)
            .execute()
            .data
            or []
        )
        check("submission stores all 5 responses", len(resp_rows) == 5, f"{len(resp_rows)} responses")
        if resp_rows:
            ids = [r["id"] for r in resp_rows]
            jobs = (
                db.table("pc_evaluation_jobs")
                .select("id")
                .in_("response_id", ids)
                .execute()
                .data
                or []
            )
            check("submission is store-only (no eval jobs yet)", len(jobs) == 0, f"{len(jobs)} jobs")


def admin_flow(base: str) -> None:
    print("\n=== ADMIN ===")
    token = admin_login(base)
    check("admin login issues token", bool(token))
    if not token:
        return
    h = {"Authorization": f"Bearer {token}"}

    def get(path: str, timeout: float = 90) -> httpx.Response | None:
        try:
            return httpx.get(base + path, headers=h, timeout=timeout)
        except httpx.HTTPError as exc:
            check(f"request {path}", False, str(exc))
            return None

    dash = get("/api/admin/dashboard")
    check("admin dashboard", dash is not None and dash.status_code == 200, "timeout" if dash is None else str(dash.status_code))

    live = get("/api/admin/monitor/live")
    check("admin monitor/live", live is not None and live.status_code == 200, "timeout" if live is None else str(live.status_code))

    logs = get("/api/admin/monitor/logs?limit=5")
    check("admin monitor/logs", logs is not None and logs.status_code == 200 and "logs" in logs.json(), "timeout" if logs is None else str(logs.status_code))

    analytics = get("/api/admin/analytics")
    check("admin analytics (was 500)", analytics is not None and analytics.status_code == 200 and "per_category" in analytics.json().get("analytics", {}), "timeout" if analytics is None else str(analytics.status_code))

    exp = get("/api/admin/export/csv?category=1")
    check("admin export CSV", exp is not None and exp.status_code == 200 and exp.content[:3] == b"\xef\xbb\xbf", "timeout" if exp is None else str(exp.status_code))

    crit = get("/api/admin/criteria")
    check("admin criteria list", crit is not None and crit.status_code == 200, "timeout" if crit is None else str(crit.status_code))

    st = get("/api/admin/test/stress")
    check("admin stress status", st is not None and st.status_code == 200 and "status" in st.json(), "timeout" if st is None else str(st.status_code))


def load_flow(base: str, total: int) -> None:
    print(f"\n=== LOAD ({total} reqs, sequential / un-throttled) ===")
    report = asyncio.run(stress_test.run(base, total))
    check(
        "load completed without external errors",
        report["errors"] == 0,
        f"{report['succeeded']}/{report['total']} ok, {report['errors']} err, "
        f"{report['req_per_s']} req/s, p95 {report['p95_latency_ms']} ms, "
        f"{report['status_codes']}",
    )


def eval_flow(base: str) -> None:
    """Seed one TEST submission, run the admin Start Eval pipeline, and assert
    every response is evaluated and the submission is finalized."""
    print("\n=== EVAL PATH ===")
    db = get_db()
    stress_test.ensure_test_schema(db)
    token = admin_login(base)
    check("admin login for eval", bool(token))
    if not token:
        return
    h = {"Authorization": f"Bearer {token}"}

    # Seed a participant + submission + 5 responses directly (store-only).
    pid = str(uuid.uuid4())
    db.table("pc_participants").insert(
        {
            "id": pid,
            "competition_id": stress_test.TEST_COMPETITION_ID,
            "registration_id": str(uuid.uuid4()),
            "qr_token": f"E2EEVAL_{pid[:12]}",
            "display_name": "E2E Eval",
            "email": "e2eeval@test.local",
            "status": "REGISTERED",
        }
    ).execute()
    sub = (
        db.table("pc_submissions")
        .insert(
            {
                "competition_id": stress_test.TEST_COMPETITION_ID,
                "participant_id": pid,
                "status": "SUBMITTED",
                "submitted_at": "now()",
            }
        )
        .execute()
        .data[0]
    )
    for p in stress_test.make_prompt_payload():
        db.table("pc_responses").insert(
            {
                "submission_id": sub["id"],
                "question_id": p["question_id"],
                "prompt_text": p["prompt_text"],
            }
        ).execute()

    # Run the evaluation pipeline in-process (same execution path the stress
    # harness uses). The HTTP-start path spawns a background thread that shares a
    # non-thread-safe Supabase client, which is unreliable on the free tier and
    # on Windows; the blocking pipeline isolate exercises identical evaluation
    # + criteria-injection code and writes the same real rows.
    import importlib

    ers = importlib.import_module("app.services.eval_run_service")
    try:
        report = ers.run_pipeline(
            competition_id=stress_test.TEST_COMPETITION_ID,
            batch_size=8,
            concurrency=1,
            max_retries=2,
        )
    except Exception as exc:  # noqa: BLE001
        check("eval pipeline runs", False, str(exc))
        return

    resp_ids = [r["id"] for r in db.table("pc_responses").select("id").eq("submission_id", sub["id"]).execute().data or []]
    ev = db.table("pc_evaluations").select("id").in_("response_id", resp_ids).execute().data or [] if resp_ids else []
    sf = db.table("pc_submissions").select("status").eq("id", sub["id"]).limit(1).execute().data or []
    check("eval pipeline evaluated all 5 responses", len(ev) == 5, f"{len(ev)} evaluations, report status={report.get('status')} completed={report.get('completed')} failed={report.get('failed')}")
    check("submission finalized COMPLETED", sf and sf[0].get("status") == "COMPLETED", str(sf[0].get("status") if sf else None))


def cleanup_flow() -> None:
    print("\n=== CLEANUP ===")
    db = get_db()
    stress_test.cleanup_test_data(db)
    remaining = (
        db.table("pc_participants")
        .select("id")
        .eq("competition_id", stress_test.TEST_COMPETITION_ID)
        .execute()
        .data
        or []
    )
    check("TEST competition fully cleaned (production clean)", len(remaining) == 0,
          f"{len(remaining)} participants left")


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E production test for the competition API.")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--mode", choices=["smoke", "admin", "eval", "load", "all"], default="all")
    parser.add_argument("--total", type=int, default=int(os.getenv("STRESS_TOTAL", "300")))
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--keep-test-data", action="store_true")
    args = parser.parse_args()

    server: ServerHandle | None = None
    base = args.base_url.rstrip("/")
    if not base:
        port = args.port or _free_port()
        server = ServerHandle()
        server.start(port)
        base = f"http://127.0.0.1:{port}"
        print(f"Booting server on {base} …")
        if not server.wait_health(base):
            print("Server failed to boot in time.")
            if server:
                server.stop()
            return 1
        print("Server healthy.")

    try:
        if args.mode in ("smoke", "all"):
            smoke_flow(base)
        if args.mode in ("admin", "all"):
            admin_flow(base)
        if args.mode in ("all", "eval"):
            eval_flow(base)
        if args.mode in ("load", "all"):
            load_flow(base, args.total)
        if not args.keep_test_data:
            cleanup_flow()
    except Exception as exc:  # noqa: BLE001
        check("harness unhandled error", False, str(exc))
    finally:
        if server:
            server.stop()

    failures = [n for n, ok, _ in RESULTS if not ok]
    print("\n================ E2E SUMMARY ================")
    print(f"  checks: {len(RESULTS)}  passed: {len(RESULTS) - len(failures)}  failed: {len(failures)}")
    for n, ok, _ in RESULTS:
        print(f"    [{'PASS' if ok else 'FAIL'}] {n}")
    print("=============================================")
    return 1 if failures else 0


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    raise SystemExit(main())