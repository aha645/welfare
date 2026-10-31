"""노인 관련 후보 서비스 표본을 뽑아 원문을 받아 JSONL로 저장한다.

입력: 노트북이 저장한 CSV (gov24_service_list.csv, welfare_local.csv, welfare_national.csv)
사용법: uv run python -m welfare_extract.build_sample eval/sample100.jsonl [제외할 ID 파일]
"""

import sys
from pathlib import Path

import pandas as pd

from welfare_extract.sources import gov24_details, local_detail, national_detail

ELDERLY_KEYWORDS = r"노인|어르신|노년|고령|65세|60세|70세|75세|80세|기초연금|치매|장기요양|경로"
SEED = 2026


def _candidates(df: pd.DataFrame, text_cols: list[str], life_col: str | None) -> pd.DataFrame:
    text = df[text_cols].fillna("").agg(" ".join, axis=1)
    mask = text.str.contains(ELDERLY_KEYWORDS)
    if life_col:
        mask |= df[life_col].fillna("").str.contains("노년")
    return df[mask]


def main(out_path: Path, exclude_path: Path | None) -> None:
    exclude = set(exclude_path.read_text().split()) if exclude_path else set()

    gov = pd.read_csv("gov24_service_list.csv", dtype=str)
    gov = gov[gov["사용자구분"].str.contains("개인|가구", na=False) & ~gov["서비스ID"].isin(exclude)]
    gov_ids = _candidates(gov, ["서비스명", "지원대상", "서비스목적요약"], None).sample(40, random_state=SEED)["서비스ID"]

    loc = pd.read_csv("welfare_local.csv", dtype=str)
    loc_ids = _candidates(loc, ["servNm", "servDgst"], "lifeNmArray").sample(40, random_state=SEED)["servId"]

    nat = pd.read_csv("welfare_national.csv", dtype=str)
    nat_ids = _candidates(nat, ["servNm", "servDgst"], "lifeArray").sample(20, random_state=SEED)["servId"]

    services = gov24_details(list(gov_ids))
    services += [local_detail(sid) for sid in loc_ids]
    services += [national_detail(sid) for sid in nat_ids]

    with out_path.open("w", encoding="utf-8") as f:
        for svc in services:
            f.write(svc.model_dump_json() + "\n")
    print(f"{len(services)}건 저장: {out_path}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
