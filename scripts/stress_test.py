#!/usr/bin/env python3
"""CLI: seed TEST submissions then run the admin evaluation pipeline.

Usage:
    python scripts/stress_test.py --url http://localhost:8000 --concurrency 8 --total 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "backend" / ".env")

from app.services.eval_run_service import run_pipeline  # noqa: E402
from app.services.stress_cleanup_service import cleanup_test_data as _cleanup  # noqa: E402
from app.services.stress_test_service import (  # noqa: E402
    TEST_COMPETITION_ID,
    ensure_test_schema,
    make_prompt_payload,
    mint_token,
    run,
)


def cleanup_test_data(db=None):  # noqa: ARG001 — signature kept for the e2e harness
    return _cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed TEST prompts then run Start Eval (dummy LLM, no live drain)."
    )
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument("--requests", "--total", dest="total", type=int, default=1250)
    parser.add_argument("--keep-test-data", action="store_true")
    args = parser.parse_args()

    print(f"Starting stress test against {args.url}")
    print(f"Total={args.total} (sequential, un-throttled — realistic single-instance load)")
    report = asyncio.run(run(args.url, args.total))
    print(
        f"Seeded: {report['succeeded']}/{report['total']} ok, "
        f"{report['errors']} err, {report['req_per_s']} req/s, "
        f"avg {report['avg_latency_ms']} ms, p95 {report['p95_latency_ms']} ms, "
        f"status_codes={report['status_codes']}"
    )
    print(f"Starting evaluation for {TEST_COMPETITION_ID}…")
    eval_report = run_pipeline(
        competition_id=TEST_COMPETITION_ID,
        batch_size=16,
        concurrency=4,
        max_retries=3,
    )
    print(
        f"Eval: status={eval_report.get('status')} enqueued={eval_report.get('enqueued')} "
        f"completed={eval_report.get('completed')} failed={eval_report.get('failed')}"
    )
    eval_ok = eval_report.get("status") == "completed" and not eval_report.get("failed")
    if not args.keep_test_data:
        cleanup_test_data()
        ensure_test_schema()
        print("TEST competition data cleaned.")
    if report["errors"] != 0:
        return 1
    return 0 if eval_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
