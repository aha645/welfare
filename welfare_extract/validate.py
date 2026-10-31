"""추출 결과 검증과 요약.

- 근거 문장(evidence)이 원문에 실제로 있는지 확인한다.
- 노인 추천에 바로 쓸 수 있는지(자동 판정 가능 / 확인 필요)를 서비스별로 분류한다.
사용법: uv run python -m welfare_extract.validate eval/sample100.jsonl eval/extract_v2_manual.jsonl
"""

import re
import sys
from collections import Counter
from pathlib import Path

from welfare_extract.extract import Extracted
from welfare_extract.schema import ServiceEligibility
from welfare_extract.sources import ServiceText


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def ungrounded(svc: ServiceText, result: ServiceEligibility) -> list[str]:
    source = _norm(f"{svc.name} {svc.target} {svc.criteria} {svc.content} {svc.deadline}")
    quotes = [q for p in result.paths for q in p.evidence] + [e.evidence for e in result.exclusions]
    return [q for q in quotes if _norm(q) not in source]


def readiness(result: ServiceEligibility) -> str:
    """노인 추천 판정에 필요한 조건이 모두 구조화됐는지."""
    if result.elderly_relevance == "비노인":
        return "제외"
    free_text = any(p.conditions.other for p in result.paths)
    if result.undecidable or result.discretionary or result.exclusions:
        return "확인 필요"
    if free_text:
        return "확인 필요(기타 조건)"
    return "자동 판정 가능"


def main(sample_path: Path, extract_path: Path) -> None:
    services = {
        s.service_id: s
        for s in (ServiceText.model_validate_json(line) for line in sample_path.read_text(encoding="utf-8").splitlines())
    }
    rows = [Extracted.model_validate_json(line) for line in extract_path.read_text(encoding="utf-8").splitlines()]

    total_quotes = sum(len(p.evidence) for r in rows for p in r.result.paths) + sum(len(r.result.exclusions) for r in rows)
    bad = {r.service_id: miss for r in rows if (miss := ungrounded(services[r.service_id], r.result))}
    print(f"[근거 검증] 인용 {total_quotes}개 중 원문 불일치 {sum(map(len, bad.values()))}개")
    for sid, miss in bad.items():
        print(f"  {sid} {services[sid].name}: {miss}")

    print("\n[노인 관련성] 출처별")
    for source in ("정부24", "지자체", "중앙부처"):
        counts = Counter(r.result.elderly_relevance for r in rows if r.source == source)
        print(f"  {source}: {dict(counts)}")

    relevant = [r for r in rows if r.result.elderly_relevance != "비노인"]
    n = len(relevant)
    paths = [p for r in relevant for p in r.result.paths]
    multi = sum(len(r.result.paths) > 1 for r in relevant)
    print(f"\n[구조] 노인 관련 {n}건, 갈래 {len(paths)}개, 갈래 2개 이상 {multi}건 ({multi / n:.0%})")

    def share(pred_count: int) -> str:
        return f"{pred_count}건 ({pred_count / n:.0%})"

    print("\n[판정을 어렵게 하는 요소] 노인 관련 서비스 기준")
    und = Counter(g for r in relevant for g in r.result.undecidable)
    print(f"  판정 불가 조건 있음: {share(sum(bool(r.result.undecidable) for r in relevant))} {dict(und)}")
    print(f"  제외 조건 있음: {share(sum(bool(r.result.exclusions) for r in relevant))}")
    print(f"  담당자 재량: {share(sum(r.result.discretionary for r in relevant))}")
    print(f"  구조화 안 된 '기타' 조건 있음: {share(sum(any(p.conditions.other for p in r.result.paths) for r in relevant))}")
    no_age = sum(
        all(p.conditions.age_min is None and not p.conditions.age_exact for p in r.result.paths)
        and any("연령 기준 원문에 없음" in o for p in r.result.paths for o in p.conditions.other)
        for r in relevant
    )
    print(f"  '노인/고령자'라고만 하고 연령 기준 없음: {share(no_age)}")

    print("\n[추천 준비 상태]")
    for state, count in Counter(readiness(r.result) for r in rows).most_common():
        print(f"  {state}: {count}건")

    print("\n[신청기한 유형]", dict(Counter(r.result.deadline.type for r in rows)))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
