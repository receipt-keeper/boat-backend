# Boat Backend 기여 가이드

이 문서는 Boatlab 백엔드를 개발하는 팀원이 로컬 환경을 준비하고, 기능을 구현하고,
Pull Request(PR)를 병합하기까지 따라야 할 공통 절차를 정리합니다.

프로젝트는 Python 3.12, FastAPI, SQLAlchemy 2.0(async), PostgreSQL, Alembic,
[uv](https://docs.astral.sh/uv/)를 사용합니다.

## 기본 개발 흐름

일반 기능과 버그 수정은 항상 `develop`에서 시작해 `develop`으로 병합합니다.

```text
develop
  -> 작업 브랜치
  -> 로컬 개발 및 검증
  -> Pull Request to develop
  -> CI 및 리뷰 스레드 해결
  -> merge commit
```

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feat/receipt-search

# 코드 작성 후
make check
git add <변경한 파일>
git commit -m "feat(receipts): 영수증 검색 API 추가"
git push -u origin feat/receipt-search
```

PR 대상 브랜치는 `develop`으로 지정합니다. `main`으로 일반 작업 PR을 보내면 브랜치 정책
검사가 실패합니다.

## 로컬 환경 준비

### 1. 저장소 및 의존성 준비

uv는 [공식 설치 가이드](https://docs.astral.sh/uv/getting-started/installation/)를 따라
설치합니다. Python 버전은 `.python-version`을 기준으로 맞춰집니다.

```bash
git clone https://github.com/receipt-keeper/boat-backend.git
cd boat-backend
git switch develop
make install
```

`make install`은 전체 개발 의존성을 설치하고 pre-commit 훅을 등록합니다.

### 2. 환경변수 준비

```bash
cp .env.example .env
```

- `.env`와 실제 비밀값은 Git에 커밋하지 않습니다.
- Firebase 인증이 필요한 경우 서비스 계정 JSON은 저장소 밖에 보관하고
  `FIREBASE_CREDENTIALS_PATH`에 절대 경로를 지정합니다.
- 팀원이 사용하는 API Key나 운영 Secret을 PR, 이슈, 로그에 붙이지 않습니다.

### 3. PostgreSQL 실행 및 마이그레이션

로컬에 PostgreSQL이 없다면 Docker로 실행합니다.

```bash
docker run -d \
  --name boat-postgres \
  -e POSTGRES_USER=boat \
  -e POSTGRES_PASSWORD=boat \
  -e POSTGRES_DB=boat \
  -p 5432:5432 \
  postgres:17

uv run alembic upgrade head
```

이미 컨테이너를 생성했다면 `docker start boat-postgres`로 다시 실행합니다.

### 4. API 서버 실행

```bash
uv run fastapi dev app/main.py
```

- API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Swagger UI: `http://localhost:8000/docs`

## 브랜치 규칙

### 브랜치별 역할

| 브랜치 | 역할 | 직접 push |
| --- | --- | --- |
| `main` | 운영 릴리스 기준 | 금지 |
| `develop` | 다음 릴리스 개발 기준 | 금지 |
| `release/vX.Y.Z` | 릴리스 안정화 | 금지 |
| 작업 브랜치 | 기능, 수정, 문서 등 실제 개발 | 허용 |

### 일반 작업 브랜치

일반 작업은 아래 형식을 사용합니다.

| 형식 | 용도 | 예시 |
| --- | --- | --- |
| `feat/*` | 새 기능 | `feat/receipt-search` |
| `fix/*` | 버그 수정 | `fix/expired-token` |
| `refactor/*` | 동작 변경 없는 구조 개선 | `refactor/file-storage` |
| `test/*` | 테스트 추가 및 수정 | `test/receipt-service` |
| `docs/*` | 문서 변경 | `docs/contributing-guide` |
| `chore/*` | 설정 및 기타 작업 | `chore/update-dependencies` |
| `ci/*` | CI 변경 | `ci/cache-uv` |

`feature/*`가 아니라 `feat/*`를 사용합니다.

### Riido 브랜치

Riido에서 복사한 `<작업키>-<제목>` 형식도 그대로 사용할 수 있습니다.

```text
58-248-소셜-회원가입-API-추가
ID-1234-영수증-검색-조건-추가
```

Riido 브랜치 제목에는 한글, 영문, 숫자, `-`, `_`, `.`을 사용할 수 있습니다. 공백,
슬래시, 제어 문자, 분해형 Unicode는 허용하지 않습니다.

### Stacked PR

선행 작업에 의존하는 작업은 브랜치를 연속으로 만들고 PR 대상을 바로 아래 부모
브랜치로 지정합니다.

```text
develop
  <- 58-247-소셜-로그인-분리
       <- 58-248-소셜-회원가입-API-추가
```

- `58-247-...` PR 대상: `develop`
- `58-248-...` PR 대상: `58-247-...`
- 자식 PR을 부모 브랜치에 먼저 병합한 뒤 부모 PR을 `develop`에 병합합니다.
- 부모 브랜치를 변경하거나 rebase할 때는 의존하는 팀원과 먼저 맞춥니다.

### 허용되는 PR 경로

| PR 대상 | 허용 source |
| --- | --- |
| `develop` | 일반 작업 브랜치, Riido 브랜치, `dependabot/**`, 동일 저장소의 `main` |
| `release/vX.Y.Z` | `fix/*`, `test/*`, `docs/*`, `chore/*`, `ci/*`, Riido 브랜치 |
| `main` | `release/vX.Y.Z`, `hotfix/*` |
| 그 외 작업 브랜치 | stacked PR을 위해 허용 |

## 코드 작성 규칙

### 모듈 구조

새 도메인 기능은 `app/modules/<도메인>/` 아래에 둡니다.

```text
app/modules/<domain>/
├── api/             # Router, 요청 및 응답 schema
├── application/     # Command, Query, Use Case
├── domain/          # Entity, Value Object, Domain exception
├── infrastructure/  # Repository, 외부 서비스 adapter
└── tests/           # 모듈 단위 테스트
```

다음 경계를 지킵니다.

- Domain 계층에서 FastAPI, SQLAlchemy, 외부 SDK를 import하지 않습니다.
- Application 계층에서 자기 모듈 또는 다른 모듈의 infrastructure를 직접 import하지 않습니다.
- 런타임 환경변수는 `app/core/config/settings.py`의 `Settings`로 읽습니다.
- API 성공 응답은 `CommonResponse[T]`, 실패 응답은 `CommonResponse[ApiErrorData]`를 사용합니다.
- 모든 함수 인자와 반환값에 타입 힌트를 작성합니다.
- 사용자에게 노출되는 검증 메시지와 OpenAPI 설명은 한글로 작성합니다.
- async endpoint에서 동기 파일 I/O나 동기 SDK를 직접 실행하지 않습니다.

### 의존성 추가

의존성 테이블을 직접 편집하지 말고 uv 명령을 사용합니다.

```bash
uv add <패키지>
uv add --dev <개발용-패키지>
```

`pyproject.toml`과 `uv.lock`을 함께 커밋합니다.

### DB 스키마 변경

ORM 모델을 변경했다면 Alembic migration을 함께 추가합니다.

```bash
uv run alembic revision --autogenerate -m "add receipt table"
uv run alembic upgrade head
```

자동 생성된 migration은 그대로 믿지 말고 컬럼 타입, nullable, index, foreign key,
upgrade 및 downgrade 내용을 직접 검토합니다.

## 테스트 및 검증

| 명령어 | 설명 |
| --- | --- |
| `make lint` | Ruff lint 검사 |
| `make format` | Ruff 자동 포맷팅 |
| `make typecheck` | Pyright 타입 검사 |
| `make test` | Pytest 및 coverage 실행 |
| `make check` | lint, format 검사, typecheck, test 전체 실행 |

개발 중에는 변경 범위의 테스트를 먼저 실행할 수 있습니다.

```bash
uv run pytest app/modules/receipts/tests
uv run pytest path/to/test_file.py::test_name
```

PR을 올리기 전에는 반드시 전체 검사를 실행합니다.

```bash
make check
```

- 새 기능과 버그 수정에는 해당 동작을 검증하는 테스트를 추가합니다.
- 모듈 테스트는 `app/modules/<도메인>/tests/`에 둡니다.
- 앱 조립, 공통 계약, bounded context 간 검증은 최상위 `tests/`에 둡니다.
- 테스트 경고는 오류로 처리되며 coverage 하한은 82%입니다.
- pre-commit이 파일을 수정하면 변경분을 다시 staging한 뒤 커밋합니다.

## 커밋 및 PR 컨벤션

커밋 메시지와 PR 제목은 모두 Conventional Commits 형식을 사용합니다.

```text
<type>(<scope>): <한글 설명>
```

`scope`는 선택 사항이며 변경한 도메인이나 영역을 짧게 적습니다.

| type | 용도 |
| --- | --- |
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변경 없는 구조 개선 |
| `test` | 테스트 추가 및 수정 |
| `docs` | 문서 변경 |
| `chore` | 빌드, 의존성, 설정 등 기타 작업 |
| `ci` | GitHub Actions 등 CI 변경 |

좋은 예시는 다음과 같습니다.

```text
feat(receipts): 영수증 검색 API 추가
fix(auth): 만료 토큰 재발급 오류 수정
docs: 팀 개발 가이드 보강
chore(release): Boatlab v1.0.1 릴리스
fix(ci): main 이미지 publish 경합 차단
chore(git): main 변경사항을 develop에 역병합
```

다음처럼 한글 분류만 앞에 붙이는 제목은 사용하지 않습니다.

```text
릴리스: Boatlab v1.0.1
긴급 수정: main 이미지 publish 경합 차단
병합: main 변경을 develop에 반영
```

커밋 하나에는 함께 되돌려야 하는 하나의 변경만 담는다. 코드 변경과 직접 관련된
테스트 및 migration은 같은 커밋에 포함할 수 있습니다.

## Pull Request 작성 및 병합

PR 본문에는 최소한 다음 내용을 적습니다.

```markdown
## 변경 사항
- 무엇을 왜 변경했는지

## 검증
- 실행한 명령과 결과

## 영향 범위
- API, DB migration, 환경변수, 배포 영향
```

PR 생성 전 체크리스트:

- [ ] PR 대상 브랜치가 Git Flow에 맞는지 확인했습니다.
- [ ] PR 제목을 Conventional Commits 형식으로 작성했습니다.
- [ ] 변경 범위에 필요한 테스트를 추가했습니다.
- [ ] `make check`가 통과했습니다.
- [ ] 스키마 변경 시 Alembic migration을 포함했습니다.
- [ ] 새 환경변수 추가 시 `.env.example`과 설정 계약을 갱신했습니다.
- [ ] API 계약 변경 시 OpenAPI 설명과 관련 테스트를 갱신했습니다.
- [ ] Secret, `.env`, Firebase JSON, 사용자 데이터가 포함되지 않았습니다.

보호 브랜치 PR은 다음 필수 체크를 통과해야 합니다.

- `Branch policy`: 브랜치 이름과 source/base 경로 검사
- `quality`: lint, format, typecheck, test 검사
- `Docker image`: 컨테이너 이미지 build 검사

리뷰 스레드를 모두 해결한 뒤 GitHub의 **Create a merge commit**으로 병합합니다. 보호
브랜치에서는 squash merge와 rebase merge를 사용하지 않습니다. 병합된 작업 브랜치는
GitHub가 자동 삭제합니다.

## 릴리스 및 핫픽스

이 절차는 릴리스 담당자가 수행합니다. 일반 기능 개발자는 작업 브랜치를 `develop`에
병합하는 단계까지만 진행합니다.

### 정식 릴리스

```text
develop
  -> release/vX.Y.Z
  -> 버전 및 릴리스 후보 검증
  -> main
  -> annotated tag vX.Y.Z
  -> main을 develop에 역병합
```

- 릴리스 안정화 중에는 `release/vX.Y.Z`에 새 기능을 추가하지 않습니다.
- 릴리스 수정은 허용된 `fix/*`, `test/*`, `docs/*`, `chore/*`, `ci/*` 또는 Riido
  브랜치에서 진행합니다.
- 버전은 `pyproject.toml`과 `uv.lock`에서 일치해야 합니다.
- `vX.Y.Z` tag CI가 release image와 GitHub Release를 생성합니다.
- 릴리스 후 `main`을 `develop`에 반드시 역병합합니다.

### 긴급 수정

```text
main
  -> hotfix/<설명>
  -> main
  -> 필요 시 patch release tag
  -> main을 develop에 역병합
```

`fix/*`를 `main`으로 직접 병합하지 않습니다. 운영 긴급 수정은 `hotfix/*`를 사용하고,
완료 후 `develop`에도 같은 변경이 남도록 역병합합니다.
