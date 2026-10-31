"""세 API(정부24, 지자체, 중앙부처)의 서비스 원문을 공통 형태(ServiceText)로 가져온다."""

import html
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field

Source = Literal["정부24", "지자체", "중앙부처"]

WELFARE_BASE = "https://apis.data.go.kr/B554287"
GOV24_BASE = "https://api.odcloud.kr/api/gov24/v3"
LOCAL_DETAIL = f"{WELFARE_BASE}/LocalGovernmentWelfareInformations/LcgvWelfaredetailed"
NATIONAL_DETAIL = f"{WELFARE_BASE}/NationalWelfareInformationsV001/NationalWelfaredetailedV001"


class ServiceText(BaseModel):
    """추출기 입력: 자격조건 판단에 필요한 원문 텍스트."""

    model_config = ConfigDict(extra="forbid")

    source: Source
    service_id: str
    name: str
    org: str
    target: str
    criteria: str
    content: str
    deadline: str

    def prompt_text(self) -> str:
        return (
            f"[서비스명] {self.name}\n[소관기관] {self.org}\n"
            f"[지원대상] {self.target}\n[선정기준] {self.criteria}\n"
            f"[지원내용] {self.content}\n[신청기한] {self.deadline}"
        )


def service_key() -> str:
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "DATA_GO_KR_KEY":
                return value.strip()
    return os.environ["DATA_GO_KR_KEY"]


def _clean(text: str | None) -> str:
    return html.unescape((text or "").replace("\r", "\n")).strip()


def _xml_fields(url: str, params: dict[str, str]) -> dict[str, str]:
    res = requests.get(url, params={"serviceKey": service_key(), **params}, timeout=30)
    res.raise_for_status()
    root = ET.fromstring(res.content)
    code = root.findtext("resultCode")
    if code not in (None, "0"):
        raise RuntimeError(f"API 오류 {code}: {root.findtext('resultMessage')}")
    # 반복 목록(신청방법 등)은 자격조건 판단에 쓰지 않으므로 단일 값 필드만 모은다
    return {child.tag: _clean(child.text) for child in root if not len(child)}


def local_detail(service_id: str) -> ServiceText:
    d = _xml_fields(LOCAL_DETAIL, {"servId": service_id})
    region = " ".join(v for v in (d.get("ctpvNm", ""), d.get("sggNm", "")) if v and v != "-")
    return ServiceText(
        source="지자체",
        service_id=service_id,
        name=d.get("servNm", ""),
        org=f"{region} {d.get('bizChrDeptNm', '')}".strip(),
        target=d.get("sprtTrgtCn", ""),
        criteria=d.get("slctCritCn", ""),
        content=d.get("alwServCn", ""),
        deadline=f"시행기간 {d.get('enfcBgngYmd', '')}~{d.get('enfcEndYmd', '')}",
    )


def national_detail(service_id: str) -> ServiceText:
    d = _xml_fields(NATIONAL_DETAIL, {"callTp": "D", "servId": service_id})
    return ServiceText(
        source="중앙부처",
        service_id=service_id,
        name=d.get("servNm", ""),
        org=d.get("jurMnofNm", ""),
        target=d.get("tgtrDtlCn", ""),
        criteria=d.get("slctCritCn", ""),
        content=d.get("alwServCn", ""),
        deadline=f"기준연도 {d.get('crtrYr', '')}",
    )


class _Gov24Detail(BaseModel):
    """정부24 serviceDetail 응답의 한 행 (필요한 필드만)."""

    name: str | None = Field(default=None, alias="서비스명")
    org: str | None = Field(default=None, alias="소관기관명")
    target: str | None = Field(default=None, alias="지원대상")
    criteria: str | None = Field(default=None, alias="선정기준")
    content: str | None = Field(default=None, alias="지원내용")
    deadline_type: str | None = Field(default=None, alias="신청기한유형")
    deadline: str | None = Field(default=None, alias="신청기한")


class _Gov24DetailPage(BaseModel):
    data: list[_Gov24Detail]


def gov24_details(service_ids: list[str], sleep: float = 0.1) -> list[ServiceText]:
    out = []
    for sid in service_ids:
        params = {"serviceKey": service_key(), "page": "1", "perPage": "1", "cond[서비스ID::EQ]": sid}
        res = requests.get(f"{GOV24_BASE}/serviceDetail", params=params, timeout=30)
        res.raise_for_status()
        page = _Gov24DetailPage.model_validate_json(res.content)
        if not page.data:
            raise RuntimeError(f"정부24 상세 없음: {sid}")
        d = page.data[0]
        out.append(
            ServiceText(
                source="정부24",
                service_id=sid,
                name=_clean(d.name),
                org=_clean(d.org),
                target=_clean(d.target),
                criteria=_clean(d.criteria),
                content=_clean(d.content),
                deadline=f"{_clean(d.deadline_type)} / {_clean(d.deadline)}",
            )
        )
        time.sleep(sleep)
    return out
