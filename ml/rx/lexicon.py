import re
def normalize_name(value):
    value=str(value or "").lower().strip()
    value=re.sub(r"\([^)]*\)"," ",value); value=re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|%)\b"," ",value,flags=re.I)
    value=re.sub(r"\b(tablet|tab|capsule|cap|syrup|injection|inj|drop|cream)\b"," ",value,flags=re.I)
    return " ".join(re.sub(r"[^a-z0-9 ]"," ",value).split())
def lexicon_correct(text, lexicon, k=3):
    try: from rapidfuzz import process,fuzz
    except ImportError:
        from difflib import SequenceMatcher
        scores=sorted(((SequenceMatcher(None,normalize_name(text),x["normalized"]).ratio()*100,x) for x in lexicon),reverse=True)
    else:
        names=[x["normalized"] for x in lexicon]; scores=[(score,lexicon[idx]) for _,score,idx in process.extract(normalize_name(text),names,scorer=fuzz.WRatio,limit=k)]
    return [{**item,"score":round(float(score),1)} for score,item in scores[:k]]

def build_lexicon(root="ml/data/lexicon", bd_root="ml/data/rx_bd"):
    from pathlib import Path
    import pandas as pd
    entries={}; root=Path(root)
    for path in sorted(root.rglob("*.csv")) if root.exists() else []:
        try: df=pd.read_csv(path)
        except Exception: continue
        columns={str(c).strip().lower():c for c in df.columns}; name_col=columns.get("name") or columns.get("medicine_name")
        if not name_col: continue
        comp_cols=[c for key,c in columns.items() if "composition" in key or "salt" in key]
        for _,row in df.iterrows():
            name=str(row.get(name_col,"" )).strip()
            normalized=normalize_name(name)
            if not normalized or normalized in entries: continue
            composition=" + ".join(str(row.get(c,"")).strip() for c in comp_cols if str(row.get(c,"" )).strip() and str(row.get(c)).lower()!="nan")
            entries[normalized]={"name":name,"normalized":normalized,"composition":composition,"source":"az_medicine_csv"}
    bd=Path(bd_root); found_bd=False
    for path in sorted(bd.rglob("*.csv")) if bd.exists() else []:
        try: df=pd.read_csv(path)
        except Exception: continue
        columns={str(c).strip().lower():c for c in df.columns}; name_col=columns.get("medicine_name"); generic_col=columns.get("generic_name")
        if not name_col: continue
        found_bd=True
        for _,row in df.iterrows():
            for col in (name_col,generic_col):
                if not col: continue
                name=str(row.get(col,"" )).strip(); normalized=normalize_name(name)
                if normalized and normalized not in entries: entries[normalized]={"name":name,"normalized":normalized,"composition":"","source":"bd_dataset"}
    if not any(item["source"]=="az_medicine_csv" for item in entries.values()): print("Warning: A-Z medicine CSV not found/readable; lexicon contains BD names only (brand matching will be weak).")
    return list(entries.values())
