# RESEARCH

작업 전에 현재 코드베이스를 읽고 근거를 남기는 문서다. 아직 구현하지 않는다.

## 1. Scope

- 작업 ID:
- 작업명:
- 관련 BC:
- 관련 API:

## 2. Project Structure

- 서버 엔트리포인트:
- 라우터:
- 유스케이스:
- 도메인 모델:
- 리포지토리:
- 마이그레이션:
- 테스트:

## 3. Current Flow

현재 요청/응답 흐름을 파일 경로 기준으로 적는다.

```text
request
-> api
-> application
-> domain
-> repository/infrastructure
-> response
```

## 4. Data Flow

- 입력 DTO:
- command/query:
- domain model/value object:
- ORM model:
- response schema:

## 5. Existing Constraints

- validation:
- DB constraints:
- unique/index:
- error handling:

## 6. Boundary Check

- cross-BC UUID reference:
- same-BC FK:
- cross-BC FK risk:
- delete propagation:

## 7. AI/OCR Trust Boundary Check

- draft extraction 위치:
- user review/correction 위치:
- final save 위치:
- 바로 저장되는 위험:

## 8. Similar Existing Logic

- 참고할 파일:
- 재사용할 패턴:
- 피해야 할 패턴:

## 9. Tests

- 기존 테스트:
- 추가할 테스트:
- 수동 확인:

## 10. Unknowns

- 확인 못한 것:
- 팀에 물어볼 것:
