import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

CHZZK_BASE = "https://openapi.chzzk.naver.com"

CHZZK_CLIENT_ID = os.environ["CHZZK_CLIENT_ID"]
CHZZK_CLIENT_SECRET = os.environ["CHZZK_CLIENT_SECRET"]
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

CHZZK_HEADERS = {
    "Client-Id": CHZZK_CLIENT_ID,
    "Client-Secret": CHZZK_CLIENT_SECRET,
    "Content-Type": "application/json",
}

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
    "Content-Type": "application/json",
}


def utc_now():
    return datetime.now(timezone.utc)


def iso_utc(dt=None):
    return (dt or utc_now()).isoformat()


def request_with_retry(method, url, *, max_attempts=5, **kwargs):
    """429/5xx를 짧은 지수 백오프로 재시도."""
    last_error = None
    for attempt in range(max_attempts):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                wait = min(2 ** attempt, 30)
                print(f"[retry] {r.status_code} {url} -> {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_error = e
            if attempt == max_attempts - 1:
                raise
            wait = min(2 ** attempt, 30)
            print(f"[retry] {e} -> {wait}s")
            time.sleep(wait)
    raise last_error


def sb_select(table, *, select="*", params=None):
    q = {"select": select}
    if params:
        q.update(params)
    r = request_with_retry(
        "GET",
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=SUPABASE_HEADERS,
        params=q,
    )
    return r.json()


def sb_upsert(table, rows, conflict_cols, *, return_rows=True):
    if not rows:
        return []
    headers = dict(SUPABASE_HEADERS)
    ret = "representation" if return_rows else "minimal"
    headers["Prefer"] = f"resolution=merge-duplicates,return={ret}"
    params = {"on_conflict": ",".join(conflict_cols)}
    r = request_with_retry(
        "POST",
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=rows,
    )
    if return_rows:
        return r.json()
    return []


def sb_patch(table, filters, values):
    params = dict(filters)
    headers = dict(SUPABASE_HEADERS)
    headers["Prefer"] = "return=minimal"
    request_with_retry(
        "PATCH",
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=values,
    )


def get_tracked_creators():
    return sb_select(
        "creators",
        select="id,channel_id,channel_name",
        params={
            "platform": "eq.chzzk",
            "is_vtuber": "eq.true",
            "is_active": "eq.true",
        },
    )


def get_all_chzzk_lives():
    """공식 CHZZK Open API 라이브 목록을 page.next가 없어질 때까지 전부 순회."""
    all_lives = []
    cursor = None
    seen_cursors = set()

    while True:
        params = {"size": 20}
        if cursor:
            params["next"] = cursor

        r = request_with_retry(
            "GET",
            f"{CHZZK_BASE}/open/v1/lives",
            headers=CHZZK_HEADERS,
            params=params,
        )
        payload = r.json()
        content = payload.get("content") or {}
        all_lives.extend(content.get("data") or [])

        page = content.get("page") or {}
        next_cursor = page.get("next")
        if not next_cursor:
            break
        if next_cursor in seen_cursors:
            raise RuntimeError("CHZZK pagination cursor repeated; aborting to avoid an infinite loop.")
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    return all_lives
