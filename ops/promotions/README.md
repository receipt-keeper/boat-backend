# 신규가입 환영 OCR 프로모션 운영

이 디렉터리의 SQL은 일시적인 신규가입 환영 프로모션을 운영자가 직접 등록하거나 기간만 바꿔 재실행할 때 쓴다. job, cron, 관리자 API, 공개 API 또는 과거 사용자 backfill은 제공하지 않는다.

## 실행 전제

- 데이터베이스는 `20260712_0024` 마이그레이션까지 적용되어 `promotions.context='signup'`과 `promotion_redemptions.beneficiary_key`를 지원해야 한다.
- `starts_at_kst`, `expires_at_kst`는 운영자가 반드시 `+09:00`이 붙은 ISO 8601 시각으로 넘긴다. 예: `2026-07-13T00:00:00+09:00`.
- 종료 시각은 시작 시각보다 뒤여야 한다. 누락, 형식 오류, 역전 또는 동일한 기간은 SQL이 실패하며 `promotions` row를 쓰지 않는다.
- 명령과 검증 조회에는 사용자 식별자, access token, 비밀값을 넣지 않는다.

## 실행

운영 PostgreSQL 접속 정보는 권한 제한된 libpq service 파일과 `PGPASSFILE` 또는 운영 비밀 주입으로 제공한다. 비밀번호가 포함된 URI를 명령 인자로 넘기거나 셸 히스토리에 남기지 않는다.

```bash
PGSERVICE=boat-production psql -X -v ON_ERROR_STOP=1 \
  -v starts_at_kst='2026-07-13T00:00:00+09:00' \
  -v expires_at_kst='2026-07-20T00:00:00+09:00' \
  -f ops/promotions/upsert_signup_welcome_promotion.sql
```

명령이 오류 없이 끝나면 고정 ID `8ee55542-0daa-4f2d-94f6-29bb2a71cc31`에 다음 캠페인 값을 보장한다.

| 필드 | 값 |
| --- | --- |
| `active` | `true` |
| `benefit_feature_key` | `ocr` |
| `context` | `signup` |
| `benefit_amount` | `5` |
| `max_redemptions` | `NULL` |
| `max_redemptions_per_user` | `1` |
| `name` | `보트랩 출시 기념 신규가입 OCR 5회` |

## 실행 후 확인

아래 조회는 프로모션 설정만 확인하며 PII나 비밀값을 출력하지 않는다.

```sql
SELECT
    id,
    name,
    active,
    starts_at AT TIME ZONE 'Asia/Seoul' AS starts_at_kst,
    expires_at AT TIME ZONE 'Asia/Seoul' AS expires_at_kst,
    max_redemptions,
    max_redemptions_per_user,
    benefit_feature_key,
    context,
    benefit_amount,
    times_redeemed
FROM promotions
WHERE id = '8ee55542-0daa-4f2d-94f6-29bb2a71cc31';
```

## 재실행 의미와 종료 정책

동일 ID로 재실행하면 기간과 위 표의 캠페인 설정만 갱신한다. `times_redeemed`, `created_at`, ID 및 `promotion_redemptions`의 수혜자/이력은 변경하지 않는다. 따라서 배포 재시도나 운영자 재실행은 안전하지만, 이미 시작된 프로모션의 기간을 바꾸는 것은 운영 판단이 필요하다.

이 방식은 출시 기념의 임시 운영 절차다. 자동 job/cron을 만들지 않으며, 종료 시에는 이 SQL을 재실행하지 않는다. 비활성화 또는 장기 운영 정책은 별도 승인된 작업으로 다룬다.

## 독립 검증

Docker와 `uv`가 있는 개발 환경에서는 PostgreSQL 16 컨테이너와 컨테이너 내 `psql`로 아래를 실행한다.

```bash
ops/promotions/verify_signup_welcome_promotion.sh
```

검증은 누락/잘못된/역전된 KST 입력이 row 없이 실패하는지, 첫 insert의 정확한 필드, 재실행 뒤 `times_redeemed=7` 및 synthetic redemption history 보존을 확인하고 컨테이너를 정리한다.
