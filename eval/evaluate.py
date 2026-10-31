import sys, re, json, pandas as pd
EV = sys.argv[1]
smp = pd.read_pickle(f"{EV}/sample50.pkl")
llm = pd.DataFrame(json.load(open(f"{EV}/llm_extract.json"))).set_index("i")
norm = lambda x: re.sub(r"\s+", " ", str(x)) if pd.notna(x) else ""
src = (smp.지원대상.map(norm) + " " + smp.선정기준.map(norm) + " " + smp.지원내용.map(norm))
tgt = (smp.지원대상.map(norm) + " " + smp.선정기준.map(norm))

# ---- 규칙 기반 추출기 (비교 기준선)
def rule(i):
    t = tgt[i]
    ages = re.findall(r"(\d{2,3})\s*세\s*이상", t)
    inc = set()
    if re.search(r"기초생활|생계급여|수급자", t): inc.add("기초생활수급")
    if re.search(r"차상위", t): inc.add("차상위")
    if re.search(r"의료급여", t): inc.add("의료급여")
    if re.search(r"기초\s*연금", t): inc.add("기초연금")
    if re.search(r"중위소득", t): inc.add("중위소득")
    if re.search(r"저소득", t): inc.add("저소득")
    res = "1년이상" if re.search(r"1년\s*이상", t) else ("관내" if re.search(r"관내|주민등록|주소|거주", t) else None)
    dt = smp.신청기한유형[i]; dl = norm(smp.신청기한[i])
    if dt == "상시신청": d = "상시"
    elif dt == "접수기관별상이": d = "기관별상이"
    elif re.search(r"예산|선착순", dl): d = "예산소진"
    elif re.search(r"20\d{2}\.\s*\d", dl): d = "기간"
    else: d = "기타"
    return dict(age_min=int(ages[0]) if ages else None, income=sorted(inc),
                household="Y" if re.search(r"독거|홀로", t) else None,
                ltc="Y" if re.search(r"장기\s*요양|등급", t) else None,
                veteran=bool(re.search(r"보훈|유공자|참전", t)), residency=res, deadline=d)
R = pd.DataFrame([rule(i) for i in smp.index], index=smp.index)
api_age = pd.to_numeric(smp.대상연령_시작, errors="coerce")

out = []
def pr(*a): print(*a); out.append(" ".join(map(str, a)))

pr("=== A. 노인 서비스 분류 (키워드/연령 기반 표본 선정의 정밀도)")
pr(llm.elderly.value_counts().to_dict())

pr("\n=== B. 근거 문장 검증 (LLM이 인용한 근거가 원문에 실제로 있는가)")
has_ev = llm.ev_age.notna()
grounded = [llm.ev_age[i] in src[i] for i in llm.index[has_ev]]
pr(f"근거 있음 {has_ev.sum()}건 중 원문 일치 {sum(grounded)}건 ({sum(grounded)/has_ev.sum():.0%})")
bad = [i for i in llm.index[has_ev] if llm.ev_age[i] not in src[i]]
pr("불일치:", bad)

pr("\n=== C. 최소연령: LLM vs 규칙 vs API 코드 (노인 대상 Y 건만)")
Y = llm.index[llm.elderly == "Y"]
def same(a, b): return (pd.isna(a) and pd.isna(b)) or (pd.notna(a) and pd.notna(b) and int(a) == int(b))
lr = [same(llm.age_min[i], R.age_min[i]) for i in Y]
la = [same(llm.age_min[i], api_age[i]) for i in Y]
pr(f"LLM=규칙 {sum(lr)}/{len(Y)}, LLM=API {sum(la)}/{len(Y)}")
pr("규칙 불일치:", [(i, llm.age_min[i], R.age_min[i]) for i, ok in zip(Y, lr) if not ok])
pr("API 불일치:", [(i, llm.age_min[i], api_age[i]) for i, ok in zip(Y, la) if not ok])

pr("\n=== D. 필드별 LLM vs 규칙 일치율 (전체 50건)")
cmp = {
 "income": lambda i: sorted(llm.income[i]) == R.income[i],
 "household(독거 언급)": lambda i: pd.notna(llm.household[i]) == pd.notna(R.household[i]),
 "ltc(장기요양 조건)": lambda i: pd.notna(llm.ltc[i]) == pd.notna(R.ltc[i]),
 "veteran(필수조건)": lambda i: bool(llm.veteran[i]) == R.veteran[i],
 "residency": lambda i: (None if pd.isna(llm.residency[i]) or llm.residency[i] == "기타" else llm.residency[i]) == (None if pd.isna(R.residency[i]) else R.residency[i]),
 "deadline": lambda i: llm.deadline[i] == R.deadline[i],
}
dis = {}
for k, f in cmp.items():
    ok = [f(i) for i in smp.index]; dis[k] = [i for i, o in zip(smp.index, ok) if not o]
    pr(f"{k}: {sum(ok)}/50 ({sum(ok)/50:.0%})  불일치 {dis[k]}")
for k in ["income", "veteran(필수조건)", "deadline"]:
    pr(f"\n-- {k} 불일치 상세")
    for i in dis[k]:
        col = {"income": "income", "veteran(필수조건)": "veteran", "deadline": "deadline"}[k]
        pr(f"  #{i} {smp.서비스명[i][:22]:22s} LLM={llm[col][i]}  규칙={R[col][i]}")

pr("\n=== E. LLM만 잡아낸 구조 정보")
pr("복수 경로(multi_path):", int(llm.multi_path.sum()), "건 / 특정연령(age_exact):", int((llm.age_exact.map(len) > 0).sum()),
   "건 / 연령 상한 있음:", int(llm.age_max.notna().sum()), "건 / 장기요양 '제외'·'등급외' 구분:", int(llm.ltc.isin(["제외", "등급외"]).sum()), "건")

# 사람 검토용 시트
sheet = smp[["서비스ID", "서비스명", "소관기관명", "지원대상", "선정기준", "신청기한"]].copy()
for c in ["elderly", "age_min", "age_max", "age_exact", "multi_path", "income", "household", "ltc", "mobility", "disease", "veteran", "residency", "deadline", "ev_age"]:
    sheet["LLM_" + c] = llm[c].values
for c in ["정답_elderly", "정답_age_min", "정답_income", "정답_기타", "검토자_메모"]:
    sheet[c] = ""
sheet.to_csv(f"{EV}/review_sheet.csv", index=False, encoding="utf-8-sig")
open(f"{EV}/eval_report.txt", "w").write("\n".join(out))
