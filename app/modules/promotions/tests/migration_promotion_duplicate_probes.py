from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DuplicateProbe:
    name: str
    statement: str
    expected_constraint: str


def duplicate_probes() -> tuple[DuplicateProbe, ...]:
    return (
        DuplicateProbe(
            name="duplicate promotions monthly recharge business key",
            statement="""
                INSERT INTO promotions (
                    id, name, active, starts_at, benefit_feature_key, context, benefit_amount
                )
                VALUES ('00000000-0000-0000-0000-000000000102', 'duplicate monthly recharge', true,
                        '2026-06-30 15:00:00+00', 'ocr', 'recharge', 5)
            """,
            expected_constraint="uq_promotions_benefit_context_starts_at",
        ),
        DuplicateProbe(
            name="duplicate promotion_codes.code",
            statement="""
                INSERT INTO promotion_codes (id, promotion_id, code, active)
                VALUES ('00000000-0000-0000-0000-000000000203',
                        '00000000-0000-0000-0000-000000000101', 'WELCOME2026', true)
            """,
            expected_constraint="ix_promotion_codes_code_unique",
        ),
        DuplicateProbe(
            name="case-variant duplicate promotion_codes.code",
            statement="""
                INSERT INTO promotion_codes (id, promotion_id, code, active)
                VALUES ('00000000-0000-0000-0000-000000000204',
                        '00000000-0000-0000-0000-000000000101', 'welcome2026', true)
            """,
            expected_constraint="ix_promotion_codes_code_unique",
        ),
        DuplicateProbe(
            name="duplicate promotion_redemptions.idempotency_key",
            statement="""
                INSERT INTO promotion_redemptions (
                    id, promotion_id, promotion_code_id, user_id, status, idempotency_key
                )
                VALUES ('00000000-0000-0000-0000-000000000303',
                        '00000000-0000-0000-0000-000000000101',
                        '00000000-0000-0000-0000-000000000201',
                        '00000000-0000-0000-0000-000000000302', 'granted',
                        'promotionRedemption:demo')
            """,
            expected_constraint="uq_promotion_redemptions_idempotency_key",
        ),
        DuplicateProbe(
            name="duplicate promotion_redemptions.beneficiary_key",
            statement="""
                INSERT INTO promotion_redemptions (
                    id, promotion_id, promotion_code_id, user_id, beneficiary_key, status,
                    idempotency_key
                )
                VALUES ('00000000-0000-0000-0000-000000000304',
                        '00000000-0000-0000-0000-000000000101',
                        '00000000-0000-0000-0000-000000000201',
                        '00000000-0000-0000-0000-000000000304', 'signup:stable-subject', 'granted',
                        'promotionRedemption:beneficiary:duplicate')
            """,
            expected_constraint="uq_promotion_redemptions_promotion_beneficiary",
        ),
    )
