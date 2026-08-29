import csv
from pathlib import Path

from common import sb_upsert

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "creators.csv"


def parse_bool(value, default=True):
    if value is None or value == "":
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y"
    }


def main():

    # channel_id 기준으로 중복 제거
    creators_by_channel = {}

    duplicate_count = 0

    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for line_number, row in enumerate(reader, start=2):

            channel_id = (
                row.get("channel_id") or ""
            ).strip()

            # 빈 행 / 주석 행 무시
            if not channel_id:
                continue

            if channel_id.startswith("#"):
                continue


            creator = {
                "platform": "chzzk",

                "channel_id": channel_id,

                "channel_name": (
                    row.get("channel_name") or ""
                ).strip() or None,

                "agency": (
                    row.get("agency") or ""
                ).strip() or None,

                "is_vtuber": parse_bool(
                    row.get("is_vtuber"),
                    True
                ),

                "is_active": parse_bool(
                    row.get("is_active"),
                    True
                ),
            }


            if channel_id in creators_by_channel:

                duplicate_count += 1

                print(
                    f"[duplicate] line {line_number}: "
                    f"{channel_id}"
                )


            # 같은 channel_id가 여러 번 나오면
            # 마지막 행을 사용
            creators_by_channel[channel_id] = creator


    rows = list(creators_by_channel.values())


    if not rows:

        print(
            "No valid creators found "
            "in data/creators.csv"
        )

        return


    print(
        f"Valid unique creators: {len(rows)}"
    )

    print(
        f"Duplicate rows removed: {duplicate_count}"
    )


    saved = sb_upsert(
        "creators",
        rows,
        [
            "platform",
            "channel_id"
        ],
        return_rows=True,
    )


    print(
        f"Seeded/updated creators: {len(saved)}"
    )


if __name__ == "__main__":
    main()
