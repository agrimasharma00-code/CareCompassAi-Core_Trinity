from pathlib import Path
def read_iam(root):
    root=Path(root); found=list(root.rglob("words.txt")) if root.exists() else []; words=found[0] if found else None
    if words is None: raise FileNotFoundError(f"IAM words.txt missing under {root}; expected words.tgz and words.txt from https://fki.tic.heia-fr.ch/databases/iam-handwriting-database")
    image_root=words.parent.parent if words.parent.name.lower() in {"gt","ascii","labels"} else words.parent
    rows=[]; broken=0
    for line in words.read_text(encoding="utf-8",errors="ignore").splitlines():
        if not line or line.startswith("#"): continue
        parts=line.split()
        if len(parts)<9 or parts[1]=="err": continue
        wid=parts[0]; chunks=wid.split("-")
        p=image_root/"words"/chunks[0]/f"{chunks[0]}-{chunks[1]}"/f"{wid}.png" if len(chunks)>=4 else image_root/"words"/f"{wid}.png"
        if not p.exists():
            matches=list(root.rglob(f"{wid}.png"))
            if matches: p=matches[0]
        if p.exists() and p.stat().st_size: rows.append((str(p)," ".join(parts[8:])))
        else: broken+=1
    return rows,{"valid":len(rows),"broken":broken}
