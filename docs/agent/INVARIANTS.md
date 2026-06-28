# BOUT Backend Invariants

이 문서는 BOUT 백엔드 작업 중 깨지면 안 되는 규칙이다. 코드 수정 전에 먼저 읽고, 계획 단계에서 어떤 규칙을 지키는지 명시한다.

## 1. Architecture Boundary Rules

- PostgreSQL을 기준으로 설계한다.
- DB 스키마는 BC 단위로 사고한다.
- BC 간 DB foreign key는 만들지 않는다.
- 같은 BC 내부 foreign key만 허용한다.
- 다른 BC를 참조해야 하면 UUID 값만 저장하고 application/service/event layer에서 검증한다.
- `app/core`는 `app/modules`에 의존하지 않는다.

## 2. Delete Policy

- 삭제 정책은 hard delete다.
- `deleted_at`, `is_deleted` 같은 soft delete 필드는 명시 승인 전까지 추가하지 않는다.
- 같은 BC 내부 cascade는 ERD에서 허용한 경우에만 사용한다.
- BC 간 삭제 전파는 DB cascade가 아니라 application event 또는 application service에서 처리한다.

## 3. users_bc Rules

- `users`는 서비스 회원 프로필 데이터를 소유한다.
- 인증 자격 증명은 `users`가 소유하지 않는다.
- 대표 이메일은 사용자 표시/조회용 성격이고, 외부 로그인 식별자는 auth BC가 소유한다.

## 4. auth_bc Rules

- `user_credentials`는 auth BC의 aggregate root다.
- `user_credentials.user_id`는 `users.id`를 논리 참조하지만 DB FK를 걸지 않는다.
- `external_identities.credentials_id`는 같은 BC 내부 FK를 걸 수 있다.
- `refresh_tokens.credentials_id`는 같은 BC 내부 FK를 걸 수 있다.
- refresh token 원문은 저장하지 않고 hash만 저장한다.
- 외부 로그인 식별자는 `(issuer, subject)` 기준으로 중복을 막는다.

## 5. files_bc Rules

- `files`는 논리 파일 aggregate root다.
- `file_objects`는 실제 저장소 객체를 나타낸다.
- `file_objects.file_id`는 같은 BC 내부 FK를 걸 수 있다.
- `storage_key`는 unique여야 한다.
- bucket, region 같은 인프라 설정값은 DB가 아니라 설정으로 관리한다.

## 6. assets_bc Rules

- `receipts`와 `warranties`는 별도 aggregate다.
- 영수증과 보증서를 하나의 테이블로 합치지 않는다.
- `receipt_attachments.receipt_id`는 같은 BC의 `receipts.id`에 FK를 걸 수 있다.
- `receipt_attachments.file_id`는 files BC의 `files.id`를 논리 참조한다. DB FK를 걸지 않는다.
- `warranty_attachments.file_id`도 files BC를 논리 참조한다.

## 7. Receipt Rules

- 영수증 MVP의 필수 저장값은 `item_name`, `payment_date`, `receipt_file_ids`다.
- `payment_location`, `total_amount`, `brand_name`, `category`, `memo`는 nullable이다.
- `period_months`는 미입력 시 기본 12개월로 계산한다.
- `expires_on`은 `payment_date + period_months` 기준으로 서버가 계산한다.
- `requires_physical_receipt`는 사용자가 선택하는 저장값이다. OCR 추출값으로 취급하지 않는다.

## 8. Warranty Rules

- 보증서는 v2 범위다.
- 보증서는 영수증과 분리된 aggregate로 구현한다.
- `serial_number`, `model_name` 등 보증서 중심 필드는 영수증 MVP 필수값으로 끌어오지 않는다.

## 9. ingestions_bc Rules

- `ingestion_documents`는 추천/검색 색인을 위한 파생 데이터 aggregate root다.
- `source_type`, `source_id`는 원천 데이터를 논리 참조한다.
- source 테이블로 cross-BC DB FK를 만들지 않는다.
- `ingestion_chunks.document_id`는 같은 BC 내부 FK를 걸 수 있다.
- embedding은 PGVector를 사용한다.

## 10. AI/OCR Trust Boundary

- OCR/AI 결과는 사용자 확인 전까지 final receipt/warranty data가 아니다.
- OCR 결과를 곧바로 `receipts` 또는 `warranties`에 저장하지 않는다.
- 기본 흐름은 다음과 같다.

```text
file input
-> OCR draft extraction
-> user review/correction
-> final save
-> optional ingestion update
```

- 자동 추출값과 사용자 확정 저장값의 경계를 흐리지 않는다.
