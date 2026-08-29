from datetime import datetime, timedelta, timezone

from common import (
    get_all_chzzk_lives,
    get_tracked_creators,
    iso_utc,
    sb_patch,
    sb_select,
    sb_upsert,
    utc_now,
)

END_GRACE_MINUTES = 15


def parse_dt(value):
    if not value:
        return None
    # ISO 8601 문자열을 최대한 보존하면서 Python datetime으로 변환
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_stream_metrics(stream_id, started_at, ended_at):
    snapshots = sb_select(
        "viewer_snapshots",
        select="captured_at,concurrent_viewers",
        params={
            "stream_id": f"eq.{stream_id}",
            "order": "captured_at.asc",
        },
    )

    if not snapshots:
        duration_minutes = max((ended_at - started_at).total_seconds() / 60, 0)
        return {
            "duration_minutes": round(duration_minutes, 2),
            "avg_viewers": None,
            "peak_viewers": None,
            "viewer_hours": None,
        }

    pts = [(parse_dt(x["captured_at"]), int(x["concurrent_viewers"])) for x in snapshots]
    pts = [(t, v) for t, v in pts if t is not None]
    pts.sort(key=lambda x: x[0])

    peak = max(v for _, v in pts)
    duration_minutes = max((ended_at - started_at).total_seconds() / 60, 0)

    if len(pts) == 1:
        return {
            "duration_minutes": round(duration_minutes, 2),
            "avg_viewers": float(pts[0][1]),
            "peak_viewers": peak,
            "viewer_hours": 0.0,
        }

    # 스냅샷 사이를 사다리꼴 적분. 수집된 구간에 대해서만 Viewer Hours를 계산.
    viewer_seconds = 0.0
    covered_seconds = 0.0

    for (t1, v1), (t2, v2) in zip(pts, pts[1:]):
        seconds = max((t2 - t1).total_seconds(), 0)
        # 비정상적으로 긴 공백은 데이터 누락으로 보고 30분까지만 반영
        seconds = min(seconds, 30 * 60)
        viewer_seconds += ((v1 + v2) / 2.0) * seconds
        covered_seconds += seconds

    avg = viewer_seconds / covered_seconds if covered_seconds else float(pts[-1][1])
    viewer_hours = viewer_seconds / 3600.0

    return {
        "duration_minutes": round(duration_minutes, 2),
        "avg_viewers": round(avg, 2),
        "peak_viewers": peak,
        "viewer_hours": round(viewer_hours, 2),
    }


def main():
    now = utc_now()
    creators = get_tracked_creators()
    if not creators:
        print("No active VTuber creators in public.creators. Add channel_id rows first.")
        return

    creator_by_channel = {c["channel_id"]: c for c in creators}

    # 전체 CHZZK 라이브 목록을 끝까지 정상 조회한 뒤에만 종료 판정을 수행한다.
    lives = get_all_chzzk_lives()
    tracked_lives = [x for x in lives if x.get("channelId") in creator_by_channel]

    print(f"CHZZK live total={len(lives)}, tracked live={len(tracked_lives)}")

    active_live_ids = set()

    for live in tracked_lives:
        creator = creator_by_channel[live["channelId"]]
        live_id = str(live["liveId"])
        active_live_ids.add(live_id)

        category = live.get("liveCategoryValue") or live.get("liveCategory")
        started_at = live.get("openDate")
        now_iso = iso_utc(now)

        stream_row = {
            "creator_id": creator["id"],
            "platform": "chzzk",
            "live_id": live_id,
            "title": live.get("liveTitle"),
            "category": category,
            "started_at": started_at,
            "ended_at": None,
            "last_seen_at": now_iso,
            "duration_minutes": None,
            "avg_viewers": None,
            "peak_viewers": None,
            "viewer_hours": None,
            "updated_at": now_iso,
        }

        saved = sb_upsert(
            "streams",
            [stream_row],
            ["platform", "live_id"],
            return_rows=True,
        )
        if not saved:
            raise RuntimeError(f"Failed to upsert stream {live_id}")

        stream_id = saved[0]["id"]

        sb_upsert(
            "viewer_snapshots",
            [{
                "creator_id": creator["id"],
                "stream_id": stream_id,
                "captured_at": now_iso,
                "concurrent_viewers": int(live.get("concurrentUserCount") or 0),
                "title": live.get("liveTitle"),
                "category": category,
            }],
            ["stream_id", "captured_at"],
            return_rows=False,
        )

    # 현재 열려 있으나 이번 전체 스캔에서 보이지 않은 추적 방송을 종료 처리
    open_streams = sb_select(
        "streams",
        select="id,creator_id,live_id,started_at,last_seen_at",
        params={
            "platform": "eq.chzzk",
            "ended_at": "is.null",
        },
    )

    cutoff = now - timedelta(minutes=END_GRACE_MINUTES)

    for stream in open_streams:
        live_id = str(stream["live_id"])
        if live_id in active_live_ids:
            continue

        last_seen = parse_dt(stream.get("last_seen_at"))
        started = parse_dt(stream.get("started_at"))
        if not last_seen or not started:
            continue

        if last_seen > cutoff:
            continue

        ended = last_seen
        metrics = compute_stream_metrics(stream["id"], started, ended)

        sb_patch(
            "streams",
            {"id": f"eq.{stream['id']}"},
            {
                "ended_at": iso_utc(ended),
                "duration_minutes": metrics["duration_minutes"],
                "avg_viewers": metrics["avg_viewers"],
                "peak_viewers": metrics["peak_viewers"],
                "viewer_hours": metrics["viewer_hours"],
                "updated_at": iso_utc(now),
            },
        )
        print(f"Closed stream {live_id}: {metrics}")


if __name__ == "__main__":
    main()
