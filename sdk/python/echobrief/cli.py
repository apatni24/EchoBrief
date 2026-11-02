from __future__ import annotations

import argparse
import json
import sys

from .client import EchoBriefClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="echobrief", description="EchoBrief agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    summarize = sub.add_parser("summarize", help="Summarize an episode URL")
    summarize.add_argument("url")
    summarize.add_argument("--type", default="ts", choices=["bs", "ns", "ts"])
    summarize.add_argument("--cache-only", action="store_true")
    summarize.add_argument("--idempotency-key")
    summarize.add_argument("--wait", action="store_true")

    sub.add_parser("health", help="GET /health")
    sub.add_parser("sandbox", help="GET /agent/v1/sandbox")

    job = sub.add_parser("job", help="GET /agent/v1/jobs/{id}")
    job.add_argument("job_id")
    job.add_argument("--wait", action="store_true")

    args = parser.parse_args(argv)
    client = EchoBriefClient()
    try:
        if args.command == "health":
            result = client.health()
        elif args.command == "sandbox":
            result = client.sandbox()
        elif args.command == "job":
            result = client.wait_for_job(args.job_id) if args.wait else client.get_job(args.job_id)
        elif args.command == "summarize":
            result = client.summarize(
                args.url,
                args.type,
                idempotency_key=args.idempotency_key,
                cache_only=args.cache_only,
            )
            job_id = (result.get("data") or {}).get("job_id")
            status = (result.get("data") or {}).get("status")
            if args.wait and job_id and status not in {"done", "failed", "cancelled", "expired"}:
                result = client.wait_for_job(job_id)
        else:
            parser.error("unknown command")
            return 1
    finally:
        client.close()

    print(json.dumps(result.get("data"), indent=2, default=str))
    status = result.get("status", 500)
    return 0 if result.get("ok") or status == 202 else 1


if __name__ == "__main__":
    sys.exit(main())
