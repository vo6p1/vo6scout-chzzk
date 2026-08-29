import os
import time
import requests
from datetime import datetime, timezone

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


# ---------------------------------------------------------
# Supabase 인증
#
# 신형 sb_secret_* 키:
#   apikey 헤더만 사용
#
# 구형 service_role JWT (eyJ...):
#   apikey + Authorization Bearer 사용
# ---------------------------------------------------------

SUPABASE_HEADERS = {
    "apikey": SUPABASE_SECRET_KEY,
    "Content-Type": "application/json",
}

if not SUPABASE_SECRET_KEY.startswith("sb_secret_"):
    SUPABASE_HEADERS["Authorization"] = (
        f"Bearer {SUPABASE_SECRET_KEY}"
    )


def utc_now():
    return datetime.now(timezone.utc)


def iso_utc(dt=None):
    return (dt or utc_now()).isoformat()


def request_with_retry(
    method,
    url,
    *,
    max_attempts=5,
    **kwargs
):
    for attempt in range(1, max_attempts + 1):

        try:
            response = requests.request(
                method,
                url,
                timeout=30,
                **kwargs
            )

        except requests.RequestException as exc:

            if attempt >= max_attempts:
                raise

            wait = min(2 ** (attempt - 1), 30)

            print(
                f"[network retry {attempt}/{max_attempts}] "
                f"{exc} -> {wait}s"
            )

            time.sleep(wait)
            continue


        # 성공
        if 200 <= response.status_code < 300:
            return response


        # 오류 내용을 GitHub Actions 로그에 표시
        print("")
        print("========== HTTP ERROR ==========")
        print("Method:", method)
        print("URL:", url)
        print("Status:", response.status_code)
        print("Body:", response.text)
        print("================================")
        print("")


        # 429 / 서버 오류만 재시도
        if (
            response.status_code == 429
            or response.status_code >= 500
        ):

            if attempt < max_attempts:

                wait = min(2 ** (attempt - 1), 30)

                print(
                    f"[retry {attempt}/{max_attempts}] "
                    f"{response.status_code} -> {wait}s"
                )

                time.sleep(wait)
                continue


        # 실제 HTTP 오류를 그대로 발생시킴
        response.raise_for_status()

    raise RuntimeError(
        f"Request failed after {max_attempts} attempts: {url}"
    )


def sb_select(
    table,
    *,
    select="*",
    params=None
):

    query = {
        "select": select
    }

    if params:
        query.update(params)

    response = request_with_retry(
        "GET",
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=SUPABASE_HEADERS,
        params=query,
    )

    return response.json()


def sb_upsert(
    table,
    rows,
    conflict_cols,
    *,
    return_rows=True
):

    if not rows:
        return []

    headers = dict(SUPABASE_HEADERS)

    if return_rows:
        headers["Prefer"] = (
            "resolution=merge-duplicates,"
            "return=representation"
        )
    else:
        headers["Prefer"] = (
            "resolution=merge-duplicates,"
            "return=minimal"
        )

    params = {
        "on_conflict": ",".join(conflict_cols)
    }

    response = request_with_retry(
        "POST",
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=params,
        json=rows,
    )

    if return_rows:
        return response.json()

    return []


def sb_patch(
    table,
    filters,
    values
):

    headers = dict(SUPABASE_HEADERS)
    headers["Prefer"] = "return=minimal"

    request_with_retry(
        "PATCH",
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        params=filters,
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

    all_lives = []

    cursor = None
    seen_cursors = set()

    while True:

        params = {
            "size": 20
        }

        if cursor:
            params["next"] = cursor

        response = request_with_retry(
            "GET",
            f"{CHZZK_BASE}/open/v1/lives",
            headers=CHZZK_HEADERS,
            params=params,
        )

        payload = response.json()

        content = payload.get("content") or {}

        lives = content.get("data") or []

        all_lives.extend(lives)

        page = content.get("page") or {}

        next_cursor = page.get("next")

        if not next_cursor:
            break

        if next_cursor in seen_cursors:
            raise RuntimeError(
                "CHZZK pagination cursor repeated."
            )

        seen_cursors.add(next_cursor)

        cursor = next_cursor

    return all_lives
