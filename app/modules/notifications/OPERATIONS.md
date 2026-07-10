# Notifications 운영 가이드

## 예약 푸시 알림 스케줄러

예약 푸시 알림은 앱 lifespan에 의존하지 않는 외부 스케줄러가 실행한다. 운영 cron, Kubernetes CronJob, EventBridge-equivalent에서 아래 명령을 자주 실행해 due schedule rule을 스캔한다.

```bash
uv run python -m app.modules.notifications.jobs.schedule_push_notifications --target-date 2026-07-09 --dry-run=false
```

권장 주기는 5분마다 또는 그보다 짧은 주기다. 같은 시각에 겹쳐 실행되지 않도록 Kubernetes CronJob을 쓴다면 `concurrencyPolicy: Forbid`를 둔다. 다른 스케줄러도 동일하게 single-flight 실행을 보장한다.

스케줄러는 stdout JSON과 info 로그에 `candidates`, `created`, `skipped`, `failed` 집계를 남긴다. stdout JSON의 `rules` 배열은 schedule rule별 `campaignKey`, 후보 수, 생성/스킵/실패 수를 담는다. 운영 알림은 `failed > 0` 또는 후보가 장시간 0으로 고정되는 경우를 우선 감시한다.

정책 데이터 변경은 DB의 schedule rule 값을 갱신한다. `day_offset`, `first_delay_days`, `repeat_interval_days`, `lookback_days`, `send_time_local`, `requires_marketing_consent`, `title_template`, `body_template`가 보증 D-day, 가입 지연, 반복 간격, 조회 기간, 발송 시각, 동의 필터, 카피를 결정한다. 코드 배포 없이 정책을 바꾸되, 변경 전후 dry-run으로 후보 수를 확인한다.

이 잡은 occurrence row, notification row, transactional outbox row를 같은 트랜잭션에 만든다. occurrence의 `(campaign_key, target_type, target_id, occurrence_on)` 복합 키가 중복 실행을 막는다. 실제 푸시 발송은 outbox relay가 처리하므로 API process의 outbox poller 또는 동등한 outbox relay가 실행 중이어야 한다. 외부 message bus/Kafka 연동은 이 모듈의 운영 전제가 아니다.

## 수동 QA

재현 가능한 QA 드라이버는 testcontainers PostgreSQL에 schedule rule과 후보 사용자를 seed하고 scheduler를 dry-run, 첫 실행, 동일 재실행 순서로 돌린다.

```bash
PYTHONPATH=. uv run python .omo/evidence/push-notification-scheduler/task_6_cli_qa.py
```

기대 결과는 첫 실제 실행에서 `first_created=1`, occurrence/outbox/notification이 각 1건이고, 동일한 두 번째 실행에서 `rerun_created=0`, `rerun_skipped=1`인 것이다.
