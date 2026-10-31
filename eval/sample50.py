import sys, re, json, pandas as pd
D, OUT = sys.argv[1], sys.argv[2]
gov=pd.read_pickle(f"{D}/gov.pkl"); gc=pd.read_pickle(f"{D}/gov_cond.pkl")
KW=r"노인|어르신|노년|고령|65세|60세|70세|75세|80세|기초연금|치매|장기요양|경로"
s=pd.to_numeric(gc["대상연령_시작"],errors="coerce")
e=gov[(gov.서비스명+" "+gov.지원대상.fillna("")+" "+gov.서비스목적요약.fillna("")).str.contains(KW)|gov.서비스ID.isin(gc[s>=55].서비스ID)].copy()
e=e[e.사용자구분.str.contains("개인|가구",na=False)]
t=(e.지원대상.fillna("")+" "+e.선정기준.fillna(""))
multi=t.str.findall(r"(\d{2})\s*세\s*이상").apply(lambda x: len(set(x))>1)
hard=e[multi].sample(8,random_state=7)
rest=e.drop(hard.index).sample(42,random_state=7)
smp=pd.concat([hard,rest]).sample(frac=1,random_state=1).reset_index(drop=True)
smp=smp.merge(gc[["서비스ID","대상연령_시작","대상연령_종료"]],on="서비스ID",how="left")
cols=["서비스ID","서비스명","소관기관명","지원대상","선정기준","지원내용","신청기한유형","신청기한","대상연령_시작","대상연령_종료"]
smp[cols].to_pickle(f"{OUT}/sample50.pkl")
for i,r in smp.iterrows():
    c=lambda x: re.sub(r"\s+"," ",str(x)) if pd.notna(x) else ""
    print(f"### {i} | {r.서비스ID} | {r.서비스명} | {r.소관기관명}")
    print(f"[대상] {c(r.지원대상)[:600]}")
    if c(r.선정기준): print(f"[선정] {c(r.선정기준)[:300]}")
    print(f"[내용] {c(r.지원내용)[:250]}")
    print(f"[기한] {r.신청기한유형} / {c(r.신청기한)[:100]}")
