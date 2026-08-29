from datetime import datetime
from itertools import islice
from zoneinfo import ZoneInfo

from common import (
    CHZZK_BASE,
    CHZZK_HEADERS,
    get_tracked_creators,
    iso_utc,
    request_with_retry,
    sb_patch,
    sb_upsert,
    utc_now,
)


def chunks(seq, size):
    it = iter(seq)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk


def get_channels(channel_ids):
    # 공식 문서는 channelIds를 String[]로 정의한다.
    # requests에 같은 키를 반복 전달해 배열 쿼리 파라미터로 전송한다.
    params = [("channelIds", cid) for cid in channel_ids]
    r = request_with_retry(
        "GET",
        f"{CHZZK_BASE}/open/v1/channels",
        headers=CHZZK_HEADERS,
        params=params,
    )
    payload = r.json()
    return (payload.get("content") or {}).get("data") or []


def main():
    creators = get_tracked_creators()
    if not creators:
        print("No active VTuber creators in public.creators. Add channel_id rows first.")
        return

    creator_by_channel = {c["channel_id"]: c for c in creators}
    now = utc_now()
    kst_date = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()

    follower_rows = []

    for batch in chunks(list(creator_by_channel.keys()), 20):
        channels = get_channels(batch)

        for ch in channels:
            cid = ch["channelId"]
            creator = creator_by_channel.get(cid)
            if not creator:
                continue

            # creators 최신화
            sb_patch(
                "creators",
                {"id": f"eq.{creator['id']}"},
                {
                    "channel_name": ch.get("channelName"),
                    "channel_image_url": ch.get("channelImageUrl"),
                    "updated_at": iso_utc(now),
                },
            )

            follower_rows.append({
                "creator_id": creator["id"],
                "snapshot_date": kst_date,
                "follower_count": int(ch.get("followerCount") or 0),
                "captured_at": iso_utc(now),
            })

    sb_upsert(
        "follower_snapshots",
        follower_rows,
        ["creator_id", "snapshot_date"],
        return_rows=False,
    )

    print(f"Saved follower snapshots: {len(follower_rows)}")


if __name__ == "__main__":
    main()
