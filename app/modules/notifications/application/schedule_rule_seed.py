from collections.abc import Sequence
from typing import Final

from app.modules.notifications.application.ports.schedule_rule_repository import (
    NotificationScheduleRuleRepository,
)
from app.modules.notifications.domain.schedule_rule import NotificationScheduleRule
from app.modules.notifications.schedule_rule_seed_data import (
    DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS,
    ScheduleRuleSeed,
)


def _rule_from_seed(seed: ScheduleRuleSeed) -> NotificationScheduleRule:
    return NotificationScheduleRule.create(
        campaign_key=seed.campaign_key,
        enabled=seed.enabled,
        target_kind=seed.target_kind,
        day_offset=seed.day_offset,
        first_delay_days=seed.first_delay_days,
        repeat_interval_days=seed.repeat_interval_days,
        lookback_days=seed.lookback_days,
        send_time_local=seed.send_time_local,
        requires_marketing_consent=seed.requires_marketing_consent,
        title_template=seed.title_template,
        body_template=seed.body_template,
    )


DEFAULT_NOTIFICATION_SCHEDULE_RULES: Final[tuple[NotificationScheduleRule, ...]] = (
    *(_rule_from_seed(seed) for seed in DEFAULT_NOTIFICATION_SCHEDULE_RULE_SEEDS),
)


async def upsert_default_notification_schedule_rules(
    repository: NotificationScheduleRuleRepository,
) -> None:
    await repository.upsert_many(rules=DEFAULT_NOTIFICATION_SCHEDULE_RULES)


def default_notification_schedule_rules() -> Sequence[NotificationScheduleRule]:
    return DEFAULT_NOTIFICATION_SCHEDULE_RULES
