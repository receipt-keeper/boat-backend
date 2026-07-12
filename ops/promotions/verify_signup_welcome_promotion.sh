#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly SQL_PATH="$REPO_ROOT/ops/promotions/upsert_signup_welcome_promotion.sql"
readonly PROMOTION_ID='8ee55542-0daa-4f2d-94f6-29bb2a71cc31'
readonly CONTAINER_NAME="boat-signup-welcome-promotion-qa-$$"

container_started=false
created_at_before=''

cleanup() {
    local exit_code=$?
    if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
        echo "CLEANUP: PostgreSQL 16 컨테이너 제거 완료 ($CONTAINER_NAME)"
    fi
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

psql_in_container() {
    docker exec -i "$CONTAINER_NAME" psql -X -v ON_ERROR_STOP=1 -U boat -d boat "$@"
}

run_upsert() {
    local starts_at_kst=$1
    local expires_at_kst=$2
    psql_in_container \
        -v "starts_at_kst=$starts_at_kst" \
        -v "expires_at_kst=$expires_at_kst" \
        -f - <"$SQL_PATH"
}

run_upsert_without_start() {
    local expires_at_kst=$1
    psql_in_container -v "expires_at_kst=$expires_at_kst" -f - <"$SQL_PATH"
}

run_upsert_without_expiry() {
    local starts_at_kst=$1
    psql_in_container -v "starts_at_kst=$starts_at_kst" -f - <"$SQL_PATH"
}

promotion_count() {
    psql_in_container -Atqc "SELECT count(*) FROM promotions WHERE id = '$PROMOTION_ID'"
}

assert_promotion_absent() {
    local scenario=$1
    [[ "$(promotion_count)" == '0' ]] || fail "$scenario 뒤 promotion row가 생성되었다"
    echo "PASS: $scenario 는 promotion row 없이 거부됨"
}

assert_schema_contract() {
    local revision
    revision="$(psql_in_container -Atqc 'SELECT version_num FROM alembic_version')"
    [[ -n "$revision" ]] || fail 'stale schema: alembic_version이 비어 있다'

    local required_column_count
    required_column_count="$(psql_in_container -Atqc "
        SELECT count(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND (table_name, column_name) IN (
              ('promotions', 'context'),
              ('promotion_redemptions', 'beneficiary_key')
          )
    ")"
    [[ "$required_column_count" == '2' ]] || fail 'stale schema: signup 운영에 필요한 컬럼이 없다'

    local context_constraint
    context_constraint="$(psql_in_container -Atqc "
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'promotions'::regclass
          AND conname = 'ck_promotions_context_allowed'
    ")"
    [[ "$context_constraint" == *"signup"* ]] || fail 'stale schema: signup context 제약이 없다'
    echo "PASS: schema revision=$revision, signup context/beneficiary schema 확인"
}

assert_exact_initial_row() {
    local actual
    actual="$(psql_in_container -Atqc "
        SELECT concat_ws('|', id, name, active,
            starts_at = '2026-07-13T00:00:00+09:00'::timestamptz,
            expires_at = '2026-07-20T00:00:00+09:00'::timestamptz,
            COALESCE(max_redemptions::text, 'NULL'), max_redemptions_per_user,
            benefit_feature_key, context, benefit_amount, times_redeemed)
        FROM promotions
        WHERE id = '$PROMOTION_ID'
    ")"
    [[ "$actual" == "$PROMOTION_ID|보트랩 출시 기념 신규가입 OCR 5회|t|t|t|NULL|1|ocr|signup|5|0" ]] \
        || fail "초기 insert 필드 불일치: $actual"
    echo "PASS: initial insert exact fields=$actual"
}

print_manual_data_surface() {
    echo "MANUAL COMMAND: PGSERVICE=boat-production psql -X -v ON_ERROR_STOP=1 -v starts_at_kst='2026-07-13T00:00:00+09:00' -v expires_at_kst='2026-07-20T00:00:00+09:00' -f ops/promotions/upsert_signup_welcome_promotion.sql"
    echo 'MANUAL QUERY OUTPUT:'
    psql_in_container -c "
        SELECT id, name, active,
            starts_at AT TIME ZONE 'Asia/Seoul' AS starts_at_kst,
            expires_at AT TIME ZONE 'Asia/Seoul' AS expires_at_kst,
            max_redemptions, max_redemptions_per_user,
            benefit_feature_key, context, benefit_amount, times_redeemed
        FROM promotions
        WHERE id = '$PROMOTION_ID'
    "
}

assert_upsert_preserves_history() {
    local actual history
    actual="$(psql_in_container -Atqc "
        SELECT concat_ws('|', id, name, active,
            starts_at = '2026-07-14T00:00:00+09:00'::timestamptz,
            expires_at = '2026-07-21T00:00:00+09:00'::timestamptz,
            COALESCE(max_redemptions::text, 'NULL'), max_redemptions_per_user,
            benefit_feature_key, context, benefit_amount, times_redeemed)
        FROM promotions
        WHERE id = '$PROMOTION_ID'
    ")"
    [[ "$actual" == "$PROMOTION_ID|보트랩 출시 기념 신규가입 OCR 5회|t|t|t|NULL|1|ocr|signup|5|7" ]] \
        || fail "rerun upsert 필드 또는 times_redeemed 불일치: $actual"

    local created_at_after
    created_at_after="$(psql_in_container -Atqc "
        SELECT created_at::text FROM promotions WHERE id = '$PROMOTION_ID'
    ")"
    [[ "$created_at_after" == "$created_at_before" ]] \
        || fail "rerun upsert가 created_at을 변경했다: $created_at_before -> $created_at_after"

    history="$(psql_in_container -Atqc "
        SELECT concat_ws('|', promotion_id, beneficiary_key, status, idempotency_key)
        FROM promotion_redemptions
        WHERE id = '8ee55542-0daa-4f2d-94f6-29bb2a71cc32'
    ")"
    [[ "$history" == "$PROMOTION_ID|signup:qa-subject|granted|signup-welcome-qa-history" ]] \
        || fail "rerun upsert가 redemption history를 변경했다: $history"
    echo "PASS: rerun preserved times_redeemed=7 and synthetic redemption history=$history"
}

wait_for_postgres() {
    local attempt
    for attempt in $(seq 1 30); do
        if docker exec "$CONTAINER_NAME" pg_isready -U boat -d boat >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    docker logs "$CONTAINER_NAME" >&2 || true
    fail 'PostgreSQL 16 컨테이너가 30초 안에 준비되지 않았다'
}

docker info >/dev/null 2>&1 || fail 'Docker daemon을 사용할 수 없다'
docker run --rm --name "$CONTAINER_NAME" \
    -e POSTGRES_USER=boat \
    -e POSTGRES_PASSWORD=boat \
    -e POSTGRES_DB=boat \
    -p 127.0.0.1::5432 \
    -d postgres:16-alpine >/dev/null
container_started=true
wait_for_postgres

POSTGRES_PORT="$(docker port "$CONTAINER_NAME" 5432/tcp | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p')"
readonly POSTGRES_PORT
[[ -n "$POSTGRES_PORT" ]] || fail 'PostgreSQL 16 호스트 포트를 찾지 못했다'

(
    cd "$REPO_ROOT"
    DATABASE_URL="postgresql+asyncpg://boat:boat@127.0.0.1:$POSTGRES_PORT/boat" \
        uv run alembic upgrade head
)
assert_schema_contract

if run_upsert_without_start '2026-07-20T00:00:00+09:00'; then
    fail 'starts_at_kst 누락 입력이 성공했다'
fi
assert_promotion_absent 'starts_at_kst 누락'

if run_upsert_without_expiry '2026-07-13T00:00:00+09:00'; then
    fail 'expires_at_kst 누락 입력이 성공했다'
fi
assert_promotion_absent 'expires_at_kst 누락'

if run_upsert 'not-a-kst-timestamp' '2026-07-20T00:00:00+09:00'; then
    fail '잘못된 starts_at_kst 입력이 성공했다'
fi
assert_promotion_absent '잘못된 starts_at_kst'

if run_upsert '2026-07-13T00:00:00+09:00' 'not-a-kst-timestamp'; then
    fail '잘못된 expires_at_kst 입력이 성공했다'
fi
assert_promotion_absent '잘못된 expires_at_kst'

if run_upsert '2026-07-21T00:00:00+09:00' '2026-07-20T00:00:00+09:00'; then
    fail '역전된 기간 입력이 성공했다'
fi
assert_promotion_absent 'reversed window'

if run_upsert '2026-07-20T00:00:00+09:00' '2026-07-20T00:00:00+09:00'; then
    fail '동일한 시작/종료 시각 입력이 성공했다'
fi
assert_promotion_absent 'non-positive window'

psql_in_container -qc "
    INSERT INTO promotions (
        id, name, active, starts_at, expires_at, max_redemptions,
        max_redemptions_per_user, benefit_feature_key, context, benefit_amount
    ) VALUES (
        '$PROMOTION_ID', 'wrong fixed-id campaign', true,
        '2026-07-01T00:00:00+09:00', '2026-07-02T00:00:00+09:00', NULL,
        1, 'ocr', 'recharge', 5
    );
"
if run_upsert '2026-07-13T00:00:00+09:00' '2026-07-20T00:00:00+09:00'; then
    fail '다른 campaign이 고정 promotion id를 사용한 상태에서 upsert가 성공했다'
fi
[[ "$(psql_in_container -Atqc "
    SELECT concat_ws('|', name, context, times_redeemed)
    FROM promotions WHERE id = '$PROMOTION_ID'
")" == 'wrong fixed-id campaign|recharge|0' ]] \
    || fail '다른 campaign이 고정 promotion id를 사용한 row가 변경되었다'
psql_in_container -qc "DELETE FROM promotions WHERE id = '$PROMOTION_ID'"

run_upsert '2026-07-13T00:00:00+09:00' '2026-07-20T00:00:00+09:00'
assert_exact_initial_row
print_manual_data_surface
created_at_before="$(psql_in_container -Atqc "
    SELECT created_at::text FROM promotions WHERE id = '$PROMOTION_ID'
")"

psql_in_container -qc "
    UPDATE promotions SET times_redeemed = 7 WHERE id = '$PROMOTION_ID';
    INSERT INTO promotion_redemptions (
        id, promotion_id, user_id, beneficiary_key, status, idempotency_key
    ) VALUES (
        '8ee55542-0daa-4f2d-94f6-29bb2a71cc32', '$PROMOTION_ID',
        '8ee55542-0daa-4f2d-94f6-29bb2a71cc33', 'signup:qa-subject',
        'granted', 'signup-welcome-qa-history'
    );
"
run_upsert '2026-07-14T00:00:00+09:00' '2026-07-21T00:00:00+09:00'
run_upsert '2026-07-14T00:00:00+09:00' '2026-07-21T00:00:00+09:00'
assert_upsert_preserves_history

echo 'PASS: PostgreSQL 16 / psql signup welcome promotion SQL QA 완료'
