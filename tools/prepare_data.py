"""Validate the original store data and build the generated catalog under var/.

Dry-run by default: prints what would be built and every finding, writes nothing.
    uv run python tools/prepare_data.py            # dry-run
    uv run python tools/prepare_data.py --apply    # write var/emporio.db, var/policies.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from emporio_agent.clock import SystemClock
from emporio_agent.config import DATA_DIR, VAR_DIR
from emporio_agent.ingest.pipeline import TRANSFORMATIONS, prepare


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the generated files")
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        default=SystemClock().now().date(),
        help="date used by time-dependent checks (default: today in Campo Grande)",
    )
    args = parser.parse_args()

    report = prepare(DATA_DIR, VAR_DIR, apply=args.apply, reference_date=args.reference_date)

    print(f"Source: {DATA_DIR} (read-only)")
    print("Rows:", ", ".join(f"{k}={v}" for k, v in report.row_counts.items()))
    print("Policy sections:")
    for section in report.policy_sections:
        print(f"  {section}")
    print("Transformations:")
    for item in TRANSFORMATIONS:
        print(f"  - {item}")
    print(f"Findings ({len(report.findings)}):")
    for f in sorted(report.findings, key=lambda f: ("error", "warning", "info").index(f.severity)):
        print(f"  [{f.severity.upper():7}] {f.code}: {f.message}")

    if report.errors:
        print(f"\n{len(report.errors)} error(s): nothing written.", file=sys.stderr)
        return 1
    if not report.applied:
        print("\nDry-run: nothing written. Re-run with --apply to build.")
        return 0
    print("\nWritten:")
    for output in report.outputs:
        print(f"  {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
