# VO6SCOUT CHZZK Collector

CHZZK Open API를 주기적으로 조회하여 Supabase PostgreSQL에
동시시청자, 방송, 팔로워 데이터를 누적하는 GitHub Actions 수집기입니다.

## 1. GitHub Secrets

Repository → Settings → Secrets and variables → Actions 에 다음 4개를 추가합니다.

- `CHZZK_CLIENT_ID`
- `CHZZK_CLIENT_SECRET`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

`SUPABASE_URL` 예:
`https://xxxxxxxxxxxxxxxxxxxx.supabase.co`

서버용 Supabase Secret Key는 코드/CSV/커밋에 절대 넣지 않습니다.

## 2. 추적 대상 추가

`data/creators.csv`에 CHZZK channel_id를 넣습니다.

예:

```csv
channel_id,channel_name,agency,is_vtuber,is_active
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,Creator A,,true,true
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,Creator B,Agency,true,true
```

커밋한 뒤 Actions → `Seed Creators` → `Run workflow`를 한 번 실행합니다.

또는 Supabase Table Editor에서 `creators` 테이블에 직접 넣어도 됩니다.

필수값:
- platform = `chzzk`
- channel_id
- is_vtuber = true
- is_active = true

## 3. 최초 테스트

Actions에서 아래를 수동 실행합니다.

1. `Seed Creators`
2. `CHZZK Follower Collector`
3. 대상 중 현재 방송 중인 채널이 있으면 `CHZZK Live Collector`

Supabase Table Editor에서 데이터가 들어오는지 확인합니다.

- creators
- follower_snapshots
- streams
- viewer_snapshots

## 4. 자동 실행 주기

- Live Collector: 10분마다
- Follower Collector: 하루 1회

GitHub schedule은 정확히 정각에 실행된다는 보장은 없고 지연될 수 있습니다.

## 5. GitHub Actions 비용 주의

10분마다 실행하면 월 약 4,320회입니다.

- **Public repository + standard GitHub-hosted runner:** Actions 사용료 무료
- **Private repository:** 실행 시간이 월 무료 minute quota를 빠르게 소진할 수 있음

Private repo를 반드시 써야 하고 무료 범위를 우선하려면
`.github/workflows/chzzk-live.yml`의 cron을 30분 간격으로 바꾸는 것을 권장합니다.

```yaml
- cron: "*/30 * * * *"
```

## 6. 수집 방식

### Live

CHZZK `/open/v1/lives`를 `page.next`가 끝날 때까지 순회한 다음,
`creators`에 등록된 채널만 저장합니다.

저장:
- live_id
- title
- category
- openDate
- concurrentUserCount
- captured_at

방송이 전체 라이브 목록에서 15분 이상 사라지면 종료로 판단합니다.

### Followers

CHZZK `/open/v1/channels`를 최대 20개 channel_id씩 조회합니다.

저장:
- follower_count
- snapshot_date (Asia/Seoul 기준)

## 7. 보안

- Supabase server Secret Key는 GitHub Secret에만 저장
- CHZZK Client Secret도 GitHub Secret에만 저장
- `.env`를 커밋하지 않음
- 노출된 기존 service_role 키가 있다면 회전/폐기 후 새 Secret Key 사용
