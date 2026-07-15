# 기여 가이드

boat-backend(Receipt Keeper backend API)에 기여하기 위한 안내 문서입니다.
FastAPI + SQLAlchemy 2.0(async) + PostgreSQL + Alembic 기반이며, Python 3.12와 [uv](https://docs.astral.sh/uv/)를 사용합니다.

## 개발 환경 셋업

1. **uv 설치** — [공식 설치 가이드](https://docs.astral.sh/uv/getting-started/installation/)를 참고하세요. Python 버전은 `.python-version` 파일을 통해 자동으로 맞춰집니다.

2. **의존성 설치 및 pre-commit 훅 등록**

   ```bash
   make install
   ```

   내부적으로 `uv sync --all-groups`와 `uv run pre-commit install`을 실행합니다.

3. **환경 변수 설정**

   ```bash
   cp .env.example .env
   ```

   기본값은 로컬 PostgreSQL(`postgresql+asyncpg://boat:boat@localhost:5432/boat`)을 가리킵니다.

4. **PostgreSQL 로컬 실행** (Docker 사용 시)

   ```bash
   docker run -d --name boat-postgres -e POSTGRES_USER=boat -e POSTGRES_PASSWORD=boat -e POSTGRES_DB=boat -p 5432:5432 postgres:17
   ```

## 개발 워크플로우

모든 작업은 Makefile 타겟을 기준으로 합니다.

| 명령어 | 설명 |
| --- | --- |
| `make install` | 의존성 설치 + pre-commit 훅 등록 |
| `make lint` | `ruff check` 린트 검사 |
| `make format` | `ruff format` 코드 포맷팅 |
| `make typecheck` | `pyright` 타입 검사 |
| `make test` | `pytest` 테스트 실행 (커버리지 포함) |
| `make check` | lint + format 검사 + typecheck + test 일괄 실행 |

pre-commit 훅이 등록되어 있으므로 **커밋 시 ruff 린트/포맷과 기본 검사(trailing whitespace, EOF, YAML 등)가 자동 실행**됩니다. 훅에서 파일이 수정되면 다시 스테이징한 뒤 재커밋하세요.

## 브랜치 / 커밋 컨벤션

- 일반 작업은 `develop`을 기준으로 브랜치를 생성하고 완료 후 `develop`으로 PR을 보냅니다.
- 일반 브랜치는 `feat/*`, `fix/*`, `refactor/*`, `test/*`, `docs/*`, `chore/*`, `ci/*` 형식을 사용합니다.
- Riido에서 복사한 `<작업키>-<제목>` 형식의 브랜치도 허용합니다. 브랜치명은 NFC 정규형이어야 하며 제목에는 한글, ASCII 영문·숫자, `-`, `_`, `.`을 사용할 수 있습니다.
- `dependabot/**` 브랜치는 `develop`으로 PR을 보냅니다.
- Riido stacked PR은 작업 브랜치끼리 연결할 수 있으며, 최하단 브랜치만 `develop`을 대상으로 합니다.
- `main`에는 `release/vX.Y.Z` 또는 `hotfix/*` 브랜치만 병합할 수 있습니다. `X`, `Y`, `Z`에는 ASCII 숫자를 사용하며, 병합 후 `main`을 `develop`에 역병합합니다.
- `release/vX.Y.Z`에는 릴리스 안정화 목적의 `fix/*`, `test/*`, `docs/*`, `chore/*`, `ci/*` 또는 Riido 브랜치만 병합합니다.
- 커밋 메시지: [Conventional Commits](https://www.conventionalcommits.org/)를 따릅니다.

  | 타입 | 용도 |
  | --- | --- |
  | `feat` | 새 기능 |
  | `fix` | 버그 수정 |
  | `refactor` | 동작 변경 없는 구조 개선 |
  | `test` | 테스트 추가/수정 |
  | `docs` | 문서 변경 |
  | `chore` | 빌드/설정 등 기타 작업 |

  예: `feat: 영수증 업로드 API 추가`

## 코드 스타일

ruff가 다음 룰셋을 강제합니다 (line-length 100, Python 3.12 대상).

- `E`, `F` — pycodestyle / Pyflakes 기본 오류
- `I` — import 정렬 (isort)
- `UP` — 최신 Python 문법 권장 (pyupgrade)
- `B` — 흔한 버그 패턴 (flake8-bugbear)
- `SIM`, `C4` — 코드 단순화, comprehension 개선
- `RUF` — Ruff 자체 룰
- `PT` — pytest 스타일
- `ASYNC` — async 코드의 블로킹 호출 등 비동기 안티패턴 검출
- `S` — 보안 취약 패턴 (flake8-bandit). 단, 테스트 디렉토리(`**/tests/**`)에서는 `S101`(assert 사용)과 `S106`(더미 비밀번호)이 허용됩니다.

포맷팅은 `ruff format`(`make format`)으로 통일합니다. 수동 포맷팅은 하지 마세요.

**타입 힌트는 필수**입니다. pyright `standard` 모드로 검사하며, `strict` 모드 전환이 로드맵에 있으므로 새 코드는 가능한 한 엄격하게 타입을 작성해 주세요.

### 프로젝트 구조

```
app/
├── core/                # 공유 인프라 (config, db, domain, http, observability)
└── modules/<도메인>/     # 도메인 모듈
    ├── api/             # 라우터, 요청/응답 스키마
    ├── application/     # 서비스 (유스케이스)
    ├── domain/          # 엔티티, 도메인 예외
    └── infrastructure/  # 리포지토리 등 외부 연동
```

새 도메인 기능은 `app/modules/` 아래에 위 계층 구조를 따라 추가합니다.

## 테스트 작성 규칙

- **새 기능에는 반드시 테스트를 동반**합니다. 모듈 테스트는 해당 모듈의 `app/modules/<이름>/tests/`에, 앱 수준 통합 테스트는 최상위 `tests/`에 작성합니다.
- `asyncio_mode = "auto"` 설정으로 async 테스트 함수에 별도 데코레이터가 필요 없습니다.
- 커버리지가 측정되며(`--cov=app`), 설정된 `fail_under` 기준 아래로 떨어지면 테스트가 실패합니다. 기준을 유지하거나 끌어올리는 방향으로 작성하세요.
- `filterwarnings = ["error"]` 설정으로 **모든 경고(deprecation 포함)가 테스트 실패로 처리**됩니다. 외부 라이브러리의 불가피한 경고는 targeted ignore를 추가하되, 사유를 함께 남기세요.

```bash
make test
```

## DB 마이그레이션

스키마(모델) 변경 시 Alembic 마이그레이션을 함께 커밋합니다.

```bash
# 모델 변경 후 마이그레이션 자동 생성
uv run alembic revision --autogenerate -m "add receipt table"

# 로컬 DB에 적용
uv run alembic upgrade head
```

`app/core/db/base.py`의 naming convention 덕분에 인덱스/유니크/FK 등 **제약조건 이름이 자동으로 일관되게 생성**되므로 수동으로 이름을 지정할 필요가 없습니다. 자동 생성된 마이그레이션 파일은 반드시 내용을 검토한 뒤 커밋하세요.

## PR 체크리스트

PR을 올리기 전에 다음을 확인해 주세요.

- [ ] `make check` 통과 (lint + format 검사 + typecheck + test)
- [ ] 새 기능/버그 수정에 대한 테스트 추가
- [ ] 스키마 변경 시 Alembic 마이그레이션 포함
- [ ] 관련 문서(README, docs/) 갱신 여부 확인
- [ ] 커밋 메시지가 Conventional Commits 형식인지 확인

CI(GitHub Actions)가 main 브랜치 push와 PR에서 동일한 검사를 실행하므로, 로컬에서 `make check`를 통과하면 CI도 통과합니다.
