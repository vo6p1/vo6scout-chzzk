import csv
from pathlib import Path

from common import sb_upsert

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "creators.csv"


def parse_bool(value, default=True):
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def main():
    rows = []

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            channel_id = (row.get("channel_id") or "").strip()
            if not channel_id or channel_id.startswith("#"):
                continue

            rows.append({
                "platform": "chzzk",
                "channel_id": channel_id,
                "channel_name": (row.get("channel_name") or "").strip() or None,
                "agency": (row.get("agency") or "").strip() or None,
                "is_vtuber": parse_bool(row.get("is_vtuber"), True),
                "is_active": parse_bool(row.get("is_active"), True),
            })

    if not rows:
        print("No creators found in data/creators.csv")
        return

    saved = sb_upsert(
        "creators",
        rows,
        ["platform", "channel_id"],
        return_rows=True,
    )
    print(f"Seeded/updated creators: {len(saved)}")


if __name__ == "__main__":
    main()
