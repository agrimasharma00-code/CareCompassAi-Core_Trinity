from pathlib import Path
import pandas as pd

SPLIT_NAMES={"training":"train","train":"train","validation":"val","valid":"val","val":"val","testing":"test","test":"test"}

def read_bd(root):
    root=Path(root);files=list(root.rglob("*.csv")) if root.exists() else []
    if not files:raise FileNotFoundError(f"No BD CSV found in {root}; expected CSV label file and image folders (medicine image + MEDICINE_NAME).")
    frames=[];label_names=[];generic_names=[];searched=[]
    for csv_path in files:
        try:df=pd.read_csv(csv_path)
        except Exception:continue
        cols={str(c).strip().lower():c for c in df.columns}
        label=next((cols[x] for x in ("medicine_name","label","name") if x in cols),None)
        image_col=next((cols[x] for x in ("image","image_path","filename","path") if x in cols),None)
        if not label or not image_col:continue
        searched.append(str(csv_path))
        def locate(value):
            value=str(value).strip();candidate=(csv_path.parent/value).resolve()
            if candidate.is_file():return str(candidate)
            hits=list(root.rglob(Path(value).name))
            return str(hits[0].resolve()) if hits else ""
        df["_image"]=df[image_col].astype(str).map(locate);df=df[df._image.map(lambda p:Path(p).is_file())].copy()
        if not len(df):continue
        split=next((SPLIT_NAMES[p.lower()] for p in reversed(csv_path.parts) if p.lower() in SPLIT_NAMES),"")
        if "_split" not in df.columns:df["_split"]=split
        frames.append(df);label_names.append(label);generic_names.append(cols.get("generic_name"))
    if not frames:
        raise FileNotFoundError(f"No usable BD image rows found under {root}; searched CSVs: {searched or files}. Expected IMAGE + MEDICINE_NAME columns and image files.")
    label_col=next((name for name in label_names if name in frames[0].columns),label_names[0])
    generic_col=next((name for name in generic_names if name and name in frames[0].columns),None)
    combined=pd.concat(frames,ignore_index=True)
    print(f"BD data: {len(combined)} readable images, labels={label_col}, csv_files={len(frames)}, splits={combined['_split'].value_counts().to_dict()}")
    return combined,label_col,generic_col
