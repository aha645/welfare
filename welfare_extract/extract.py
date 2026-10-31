"""LLM으로 자격조건을 추출한다. 공급자(Claude API / 로컬 모델)는 config/llm.toml 의 extraction 설정을 따른다.

사용법: uv run python -m welfare_extract.extract eval/sample100.jsonl eval/extract_api.jsonl [--provider local]
인증: Claude는 ANTHROPIC_API_KEY (또는 `ant auth login` 프로필), 로컬은 OpenAI 호환 서버 실행 필요
"""

import argparse
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from welfare_extract.llm import LLMClient, client_for
from welfare_extract.schema import ServiceEligibility
from welfare_extract.sources import ServiceText

SYSTEM = """당신은 한국 복지서비스 공고문에서 자격조건을 구조화하는 추출기입니다.
목적: 노인(65세 이상) 복지 추천 시스템이 "이 사람이 받을 수 있는가"를 판정할 수 있게 하는 것.

규칙:
- 원문에 있는 내용만 추출한다. 추측하지 않는다. 언급 없는 조건은 null 또는 빈 리스트.
- 대상이 "A 또는 B 또는 C" 형태로 나열되면 각각을 별도 갈래(paths)로 만든다.
  나열된 다른 대상(예: 장애인, 국가유공자)의 조건을 노인 갈래에 섞지 않는다.
- 하위 사업마다 조건이 다르면(예: 경로식당 60세, 도시락배달 65세) 하위 사업별 갈래로 나눈다.
- 노인이 해당될 수 없는 갈래(임산부, 청소년, 다자녀 부모 등)는 만들지 않는다.
  elderly_relevance가 "비노인"이면 paths는 비워도 된다.
- evidence와 exclusions.evidence는 원문 구절을 글자 그대로 복사한다.
- "구청장이 인정하는 자", 위원회 심사 등 재량이 있으면 discretionary=true.
- "저소득"만 있고 기준이 없으면 income_any_of에 "저소득_정의없음", undecidable에도 추가한다.
- 건강보험료 기준은 "건강보험료"로 표시하고 undecidable에 "건강보험료기준"을 추가한다.
- 신청기한은 원문의 날짜를 YYYY-MM-DD로 바꾸고, 날짜가 없으면 유형만 고른다.
"""


class Extracted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_id: str
    source: str
    model: str
    result: ServiceEligibility


def extract_one(llm: LLMClient, svc: ServiceText) -> ServiceEligibility:
    return llm.parse(SYSTEM, svc.prompt_text(), ServiceEligibility)


def main(sample_path: Path, out_path: Path, provider: str | None) -> None:
    llm = client_for("extraction", provider)
    print(f"추출 모델: {llm.name}")
    services = [ServiceText.model_validate_json(line) for line in sample_path.read_text(encoding="utf-8").splitlines()]
    with out_path.open("w", encoding="utf-8") as f:
        for i, svc in enumerate(services, 1):
            result = extract_one(llm, svc)
            row = Extracted(service_id=svc.service_id, source=svc.source, model=llm.name, result=result)
            f.write(row.model_dump_json() + "\n")
            print(f"[{i}/{len(services)}] {svc.source} {svc.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sample", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--provider", help="config/llm.toml 의 공급자 이름 (예: claude, local)")
    args = parser.parse_args()
    try:
        main(args.sample, args.out, args.provider)
    except (RuntimeError, ValueError) as e:
        raise SystemExit(f"오류: {e}") from e
