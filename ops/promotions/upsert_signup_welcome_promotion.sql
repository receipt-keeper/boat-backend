\set ON_ERROR_STOP on

\if :{?starts_at_kst}
\else
DO $$ BEGIN RAISE EXCEPTION 'starts_at_kst is required and must be an ISO timestamp with +09:00'; END $$;
\endif

\if :{?expires_at_kst}
\else
DO $$ BEGIN RAISE EXCEPTION 'expires_at_kst is required and must be an ISO timestamp with +09:00'; END $$;
\endif

SELECT
    (
        :'starts_at_kst' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?\+09:00$'
    ) AS starts_at_kst_is_valid,
    (
        :'expires_at_kst' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?\+09:00$'
    ) AS expires_at_kst_is_valid
\gset

\if :starts_at_kst_is_valid
\else
DO $$ BEGIN RAISE EXCEPTION 'starts_at_kst must be an ISO timestamp with +09:00'; END $$;
\endif

\if :expires_at_kst_is_valid
\else
DO $$ BEGIN RAISE EXCEPTION 'expires_at_kst must be an ISO timestamp with +09:00'; END $$;
\endif

SELECT (:'starts_at_kst')::timestamptz < (:'expires_at_kst')::timestamptz AS promotion_window_is_positive
\gset

\if :promotion_window_is_positive
\else
DO $$ BEGIN RAISE EXCEPTION 'expires_at_kst must be later than starts_at_kst'; END $$;
\endif

WITH upsert AS (
INSERT INTO promotions (
    id,
    name,
    active,
    starts_at,
    expires_at,
    max_redemptions,
    max_redemptions_per_user,
    benefit_feature_key,
    context,
    benefit_amount
)
VALUES (
    '8ee55542-0daa-4f2d-94f6-29bb2a71cc31',
    '보트랩 출시 기념 신규가입 OCR 5회',
    true,
    (:'starts_at_kst')::timestamptz,
    (:'expires_at_kst')::timestamptz,
    NULL,
    1,
    'ocr',
    'signup',
    5
)
ON CONFLICT (id) DO UPDATE
SET
    name = EXCLUDED.name,
    active = EXCLUDED.active,
    starts_at = EXCLUDED.starts_at,
    expires_at = EXCLUDED.expires_at,
    max_redemptions = EXCLUDED.max_redemptions,
    max_redemptions_per_user = EXCLUDED.max_redemptions_per_user,
    benefit_feature_key = EXCLUDED.benefit_feature_key,
    context = EXCLUDED.context,
    benefit_amount = EXCLUDED.benefit_amount,
    updated_at = now()
WHERE promotions.context = 'signup'
  AND promotions.benefit_feature_key = 'ocr'
RETURNING id
)
SELECT EXISTS (SELECT 1 FROM upsert) AS promotion_upserted
\gset

\if :promotion_upserted
\else
DO $$ BEGIN RAISE EXCEPTION 'fixed promotion id belongs to a different campaign'; END $$;
\endif
