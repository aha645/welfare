"""복지서비스 자격조건 추출 스키마 (갈래별 조건 묶음).

한 서비스는 여러 '갈래(path)'를 가질 수 있다. 갈래 중 하나의 조건을 모두 만족하면 지원 대상이다.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IncomeBasis = Literal[
    "기초생활수급",  # 생계·의료·주거·교육급여 구분이 없는 수급자
    "생계급여",
    "의료급여",
    "주거급여",
    "차상위",
    "기초연금",
    "중위소득",  # median_income_pct_max 와 함께
    "건강보험료",  # 보험료 하한액 이하 등, 사용자가 직접 답하기 어려움
    "저소득_정의없음",
]
Household = Literal["독거", "노인부부", "조손", "한부모", "다자녀", "1인가구"]
LongTermCare = Literal["등급자", "등급외", "무관"]
DeadlineType = Literal[
    "상시", "기간", "정기", "예산소진", "자동선정", "별도공지", "기관별상이", "운영중단", "기타"
]
ElderlyRelevance = Literal["노인대상", "노인포함", "특정직업", "비노인"]
ExclusionType = Literal["유사서비스", "기수혜", "시설입소", "소득재산", "기타"]
Gap = Literal["건강보험료기준", "저소득_정의없음", "재산기준", "재량심사", "예산소진", "기타"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Residency(_Strict):
    scope: Literal["관내", "시도"] = Field(description="관내=해당 시군구, 시도=해당 광역시도")
    min_years: float | None = Field(description="최소 거주기간(년). 없으면 null")


class Conditions(_Strict):
    """한 갈래 안에서 모두(AND) 만족해야 하는 조건. 언급 없는 조건은 null 또는 빈 리스트."""

    age_min: int | None
    age_max: int | None
    age_exact: list[int] = Field(description="'만 80, 90, 100세'처럼 특정 연령만 대상일 때")
    income_any_of: list[IncomeBasis] = Field(description="이 중 하나에 해당하면 소득조건 충족")
    median_income_pct_max: int | None
    household_any_of: list[Household]
    long_term_care: LongTermCare | None
    health_any_of: list[str] = Field(description="치매, 백내장, 거동불편 등 건강상태 요건")
    disability: bool | None
    veteran: bool | None
    occupation_any_of: list[str] = Field(description="농업인, 어업인 등 직업 요건")
    residency: Residency | None
    other: list[str] = Field(description="위 필드로 표현 못 한 조건(원문 그대로 짧게)")


class EligibilityPath(_Strict):
    label: str = Field(description="갈래 이름. 예: '경로우대', '도시락배달'")
    conditions: Conditions
    benefit: str | None = Field(description="이 갈래의 혜택. 예: '이용료 30% 감면'")
    evidence: list[str] = Field(description="조건 근거가 되는 원문 구절(원문 그대로 복사)")


class Exclusion(_Strict):
    type: ExclusionType
    text: str
    evidence: str = Field(description="원문 그대로 복사한 구절")


class Deadline(_Strict):
    type: DeadlineType
    start: str | None = Field(description="YYYY-MM-DD, 알 수 없으면 null")
    end: str | None = Field(description="YYYY-MM-DD, 알 수 없으면 null")


class ServiceEligibility(_Strict):
    elderly_relevance: ElderlyRelevance = Field(
        description=(
            "노인대상=노인이 주 대상, 노인포함=65세 이상 갈래가 있거나 연령 제한 없이 노인도 받을 수 있음, "
            "특정직업=노인도 받을 수 있으나 농업인 등 직업 요건 필요, 비노인=노인은 대상 아님(paths는 비워도 됨)"
        )
    )
    paths: list[EligibilityPath]
    exclusions: list[Exclusion]
    discretionary: bool = Field(description="'인정하는 자', 위원회 심사 등 담당자 재량이 있으면 true")
    undecidable: list[Gap] = Field(description="데이터만으로 판정할 수 없는 조건 종류")
    deadline: Deadline
