# 노인 복지 추천 서비스 (welfare)

공공데이터포털(data.go.kr)의 복지서비스 API 3종에서 데이터를 모으고, 공고문 속 자격조건을 LLM으로 구조화해서,
어르신이 받을 수 있는 복지 혜택을 근거와 함께 추천하는 서비스를 만드는 프로젝트입니다.

> 현재 단계: **데이터 수집·분석과 자격조건 추출 파이프라인까지 구현**되어 있습니다.
> 대화형 추천 화면(Streamlit + React)과 판정 엔진은 아직 만들지 않았습니다. 전체 계획은 [개발계획서](https://claude.ai/artifact/MTyNTdMsDf7mRkfbSHutgE)에 있습니다.

## 구현된 기능

| 기능 | 위치 | 상태 |
|---|---|---|
| 복지서비스 API 3종 수집 → DataFrame | `welfare_api.ipynb` | 완료 |
| 수집 데이터 분석 (갱신 주기, 노인 관련 규모, 필드 결측) | `welfare_api.ipynb`, 아래 [분석 결과](#지금까지-확인한-사실) | 완료 |
| 자격조건 추출 스키마 (갈래별 조건, 제외 조건, 판정 불가 조건) | `welfare_extract/schema.py` | 완료 (v2) |
| 세 API의 상세 원문을 공통 형태로 가져오기 | `welfare_extract/sources.py` | 완료 |
| 노인 관련 표본 추출 | `welfare_extract/build_sample.py` | 완료 |
| LLM 조건 추출 (Claude API / 로컬 모델 선택) | `welfare_extract/extract.py`, `welfare_extract/llm.py`, `config/llm.toml` | 코드 완료, **실제 모델로는 아직 실행 전** |
| 추출 결과 검증 (근거 인용이 원문에 있는지, 판정 가능 여부) | `welfare_extract/validate.py` | 완료 |
| 평가용 표본과 추출 결과 | `eval/` | 50건 + 100건 |
| 테스트, 코드 품질 검사 (ruff, flake8 + anti-slop, mypy strict) | `tests/`, `pyproject.toml`, `.flake8` | 완료 |

### 아직 구현되지 않은 것

- 판정 엔진 (프로필 + 조건 → 해당 / 확인 필요 / 해당 없음)
- 대화형 질문 선택과 답변 해석
- 순위, 추천 설명, 독립 LLM 검증
- PostgreSQL 저장과 매일 자동 갱신
- Streamlit + React 화면

## 사용하는 API

| 이름 | 주소 | 형식 | 규모 (2026-10-31) |
|---|---|---|---|
| 한국사회보장정보원 중앙부처복지서비스 | `apis.data.go.kr/B554287/NationalWelfareInformationsV001` | XML | 461건 |
| 한국사회보장정보원 지자체복지서비스 | `apis.data.go.kr/B554287/LocalGovernmentWelfareInformations` | XML | 4,827건 |
| 행정안전부 정부24 공공서비스 정보 | `api.odcloud.kr/api/gov24/v3` (`serviceList`, `serviceDetail`, `supportConditions`) | JSON | 10,942건 |

세 API 모두 같은 data.go.kr 인증키를 사용합니다.

## 설치

[uv](https://docs.astral.sh/uv/)가 필요합니다. Python 3.14 가상환경과 의존성이 함께 설치됩니다.

```bash
uv sync
```

프로젝트 폴더에 `.env` 파일을 만들고 data.go.kr 인증키(**Decoding 키**)를 넣습니다. `.env`는 `.gitignore`에 들어 있어 커밋되지 않습니다.

```bash
DATA_GO_KR_KEY=발급받은_인증키
```

LLM 추출을 실행하려면 둘 중 하나가 필요합니다.

- **Claude API**: `ANTHROPIC_API_KEY` 환경변수 설정
- **로컬 모델**: OpenAI 호환 서버(Ollama, vLLM, llama.cpp server) 실행 후 `config/llm.toml`의 `model`, `base_url` 수정

> 이 셸에는 `pip`가 Homebrew Python을 가리키는 별칭이 걸려 있어서, 가상환경을 켜도 `pip install`이 `.venv`에 설치되지 않습니다. 패키지는 `uv add <패키지>`로 추가하세요.
> `uv sync`는 `pyproject.toml`에 없는 패키지를 `.venv`에서 지웁니다. 직접 설치한 패키지가 사라지지 않게 하려면 반드시 `uv add`로 추가하세요.

## 실행 방법

### 1. 데이터 수집과 분석 (노트북)

VS Code에서 `welfare_api.ipynb`를 열고 커널로 `.venv`를 선택한 뒤 전체 실행합니다(`ipykernel`은 개발 의존성에 포함되어 있습니다).
브라우저에서 열려면 `uv add --dev notebook` 후 `uv run jupyter notebook welfare_api.ipynb`를 실행합니다.

노트북은 세 API를 모두 받아 DataFrame으로 보여주고, 다음 CSV를 프로젝트 폴더에 저장합니다.
이 CSV들은 2단계(표본 추출)의 입력입니다.

- `welfare_national.csv`, `welfare_local.csv`, `welfare_all.csv`
- `gov24_service_list.csv`, `gov24_service_detail.csv`, `gov24_support_conditions.csv`

이 CSV들은 매일 바뀌고 다시 받을 수 있으므로 `.gitignore`에서 제외되어 있습니다.

### 2. 노인 관련 표본 추출

정부24 40건, 지자체 40건, 중앙부처 20건을 뽑아 상세 원문을 받아 JSONL로 저장합니다.
두 번째 인자는 제외할 서비스 ID 목록입니다(이전 표본과 겹치지 않게).

```bash
uv run python -m welfare_extract.build_sample eval/sample100.jsonl eval/sample50_ids.txt
```

### 3. LLM 조건 추출

공급자는 `config/llm.toml`의 `[tasks] extraction` 설정을 따르고, `--provider`로 바꿀 수 있습니다.

```bash
uv run python -m welfare_extract.extract eval/sample100.jsonl eval/extract_claude.jsonl                   # 설정대로 (Claude)
uv run python -m welfare_extract.extract eval/sample100.jsonl eval/extract_local.jsonl --provider local  # 로컬 모델
```

결과 한 줄마다 서비스 ID, 출처, 사용한 모델 이름, 추출 결과가 들어갑니다.

### 4. 추출 결과 검증

근거 인용이 원문에 글자 그대로 있는지 확인하고, 노인 관련성·판정 불가 조건·추천 준비 상태를 요약합니다.

```bash
uv run python -m welfare_extract.validate eval/sample100.jsonl eval/extract_v2_manual.jsonl
```

### 5. 테스트와 코드 품질 검사

```bash
uv run pytest                                   # 테스트 (로컬 모델은 가짜 서버로 검사)
uv run ruff check welfare_extract tests
uv run flake8 welfare_extract tests             # anti-slop 규칙(ASP, ASD, PYD)
uv run mypy welfare_extract tests
uv run nbqa flake8 welfare_api.ipynb            # 노트북 검사
```

## LLM 공급자 설정 (`config/llm.toml`)

LLM을 쓰는 작업마다 Claude API와 로컬 모델 중 하나를 고릅니다.
두 공급자 모두 같은 pydantic 스키마로 출력 형식을 강제하고, 받은 결과를 같은 스키마로 다시 검증합니다.

| 작업 | 기본 공급자 | 이유 |
|---|---|---|
| `extraction` 조건 추출 | claude | 가장 어려운 작업. 로컬 모델이 같은 표본에서 기준을 넘으면 전환 |
| `answer_parsing` 답변 해석 | local | 건강·소득 등 민감정보가 외부로 나가지 않음 |
| `question_wording` 질문 문장화 | local | 난이도 낮음 |
| `explanation` 추천 설명 | local | 사실 검사 실패 시 템플릿 문장으로 대체 예정 |
| `verification` 독립 검증 | claude | 추출과 다른 모델이어야 같은 실수를 반복하지 않음 |

- **Claude**: Anthropic SDK의 `beta.messages.parse`, 기본 모델 `claude-opus-5-5`. 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도하는 서버 측 fallback이 켜져 있습니다.
- **로컬**: `/v1/chat/completions`에 `response_format`(JSON 스키마)을 보냅니다. 서버 연결 실패, 출력 잘림, 형식 불일치는 오류로 멈춥니다.

현재 `answer_parsing` 등은 아직 코드에서 쓰는 곳이 없고, 판정 엔진·대화 기능을 만들 때 연결됩니다.

## 폴더 구조

```text
welfare/
├─ welfare_api.ipynb          # API 3종 수집·분석 노트북
├─ welfare_extract/           # 자격조건 추출 파이프라인
│  ├─ schema.py               # 추출 스키마 (갈래별 조건 묶음)
│  ├─ sources.py              # 세 API 상세 원문 → ServiceText
│  ├─ build_sample.py         # 노인 관련 표본 추출
│  ├─ llm.py                  # LLM 공급자 (Claude / 로컬) 선택
│  ├─ extract.py              # LLM 조건 추출 CLI
│  └─ validate.py             # 근거 인용 검증과 요약
├─ config/llm.toml            # 작업별 LLM 공급자 설정
├─ eval/                      # 평가 표본과 결과
│  ├─ sample50.*, llm_extract.json, evaluate.py, review_sheet.csv   # 1차 평가 (50건, v1 형식)
│  └─ sample100.*, extract_v2_manual.jsonl, manual_extract_v2.py    # 2차 평가 (100건, v2 형식)
├─ tests/test_llm.py          # LLM 공급자 테스트
├─ pyproject.toml, uv.lock    # 의존성, ruff·mypy·pytest 설정
└─ .flake8                    # anti-slop flake8 규칙
```

## 지금까지 확인한 사실

2026-10-31 수집분과 표본 150건 분석 결과입니다.

| 항목 | 결과 |
|---|---|
| 정부24 최근 7일 변경 | 1,291건 / 10,942건 (12%) → **매일 수집**이 필요 |
| API 연령 코드와 원문 연령 일치 | 27/39 (69%) → 연령은 원문에서 추출한 값을 우선 |
| 대상이 여러 갈래인 서비스 | 35/95 (37%) |
| 판정 불가 조건 (건강보험료 기준, 담당자 재량, 재산) | 24/95 (25%) |
| 데이터만으로 자동 판정 가능 | 27/95 (28%) → 나머지는 질문이나 문의처 확인 필요 |
| 생애주기 "노년" 표시인데 실제 노인 연령 조건이 있는 중앙부처 서비스 | 6/20 |
| 추출 결과의 근거 인용이 원문과 일치 | 187/187 |

### 이 결과를 읽을 때 주의할 점

- `eval/`의 추출 결과(`llm_extract.json`, `extract_v2_manual.jsonl`)는 API 키가 없어서 **Claude Code 세션 안에서 직접 작성**한 것입니다. 실제 API로 추출한 결과가 아닙니다.
- 정확도는 아직 **사람 검토를 거치지 않았습니다**. `eval/review_sheet.csv`의 `정답_*` 칸을 채우면 사람 기준 정확도를 계산할 수 있습니다.
- `eval/sample50.py`는 세션 중 임시 폴더에 저장한 수집 데이터(pickle)를 입력으로 썼기 때문에, 그대로는 다시 실행되지 않습니다. 같은 표본은 `eval/sample50.pkl`에 저장되어 있습니다.

## 다음 단계

1. **판정 엔진 시제품** (API 키 없이 가능): v3 스키마, 3값 판정과 trace, 가상 어르신 5명으로 질문 효과 측정
2. **실제 LLM 추출**: Claude 또는 로컬 모델로 100건 추출, 사람 검토로 정확도 확정
3. **데이터 기반**: 노인 후보 약 3,200건 추출, PostgreSQL 적재, 매일 갱신
4. **대화형 추천 MVP**: Streamlit + React
5. **시범 운영**

자세한 설계(추천 엔진 구성, 질문과 매칭, 원문 대조 검증, DB 설계)는 [개발계획서](https://claude.ai/artifact/MTyNTdMsDf7mRkfbSHutgE)를 참고하세요.
