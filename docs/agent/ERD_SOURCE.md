# BOUT Backend ERD Source

이 문서는 BOUT 백엔드 ERD와 회의 결정에서 나온 현재 기준을 작업 전에 확인하기 위한 원천 메모다.

## Source Status

- 기준일: 2026-06-28
- 대상 레포: `receipt-keeper/boat-backend`
- DB: PostgreSQL
- 아키텍처: FastAPI 기반 모듈형 레이어드 구조
- 주의: 실제 ERD 이미지/DDL이 갱신되면 이 파일을 먼저 갱신한 뒤 `INVARIANTS.md`를 함께 점검한다.

## Bounded Contexts

현재 ERD는 다음 BC 경계를 전제로 한다.

- `users_bc`
- `auth_bc`
- `files_bc`
- `assets_bc`
- `ingestions_bc`

## Current Backend Ownership Snapshot

- OCR 분석 API와 영수증 등록/조회/수정/삭제 API는 receipt-side backend 작업으로 본다.
- 파일 업로드/스토리지 구현은 files BC가 담당한다.
- 영수증은 파일 업로드 결과로 받은 `receipt_file_ids`만 논리 참조한다.
- OCR API는 분석 전용이다. 이미지를 저장하지 않고, multipart `file`만 입력받는다.
- 최종 영수증 저장은 사용자가 OCR 결과를 확인/수정한 뒤 `POST /api/v1/receipts`에서 수행한다.

## Latest Receipt/OCR Flow

```text
앱에서 영수증 이미지 선택
-> POST /api/v1/ocr multipart/form-data file
-> OCR 후보값 반환
-> 사용자가 후보값 확인/수정
-> 필요한 경우 POST /api/v1/files 로 이미지 저장
-> POST /api/v1/receipts 로 최종 영수증 저장
   - item_name
   - payment_date
   - optional payment_location
   - optional total_amount
   - optional brand_name
   - optional period_months
   - requires_physical_receipt
   - receipt_file_ids
```

## Notes To Reconcile During Research

- 일부 초기 문서에는 `payment_location`, `total_amount`가 required로 적혀 있을 수 있다.
- 현재 MVP 구현 기준에서는 OCR 실패/불확실성을 고려해 `payment_location`, `total_amount`는 nullable로 둔다.
- `receipt_file_ids`는 최종 저장된 영수증의 파일 연결 계약이므로 1개 이상 필요하다.
- `serial_number`는 보증서 v2 범위로 보고 영수증 MVP 필수 필드에서 제외한다.
