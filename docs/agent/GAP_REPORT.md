# GAP_REPORT

`ERD_SOURCE.md`와 `INVARIANTS.md` 기준으로 현재 코드와의 차이를 정리한다. 아직 구현하지 않는다.

## 1. Summary

- 일치하는 부분:
- 불일치하는 부분:
- 가장 위험한 차이:

## 2. Table/Model Comparison

| 대상 | ERD/규칙 | 현재 코드 | 차이 | 우선순위 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## 3. BC Boundary Violations

- BC 간 DB FK:
- cross-BC cascade:
- logical reference여야 하는데 FK인 곳:

## 4. Delete Policy Violations

- soft delete 필드:
- hard delete 미준수:
- application event 없이 cross-BC 정리하는 곳:

## 5. AI/OCR Trust Boundary Violations

- OCR 결과를 final data로 바로 저장하는 곳:
- 사용자 검수/수정 단계가 없는 곳:
- draft와 final이 섞인 곳:

## 6. Priority

### P0

- 데이터 깨짐:
- BC 경계 위반:
- 보안 위반:

### P1

- ERD/PRD 불일치:
- index/unique 누락:
- validation 누락:

### P2

- 네이밍:
- 문서화:
- 테스트 보강:
