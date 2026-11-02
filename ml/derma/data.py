from pathlib import Path
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold
from .config import CLASSES

def find_metadata(data_dir):
    root=Path(data_dir)
    found=list(root.rglob("HAM10000_metadata.csv")) if root.exists() else []
    if not found: raise FileNotFoundError(f"HAM10000 metadata not found under {root}; expected HAM10000_metadata.csv and image folders. See https://www.kaggle.com/datasets/kmader/skin-cancer-mnist-ham10000")
    return found[0]

def grouped_splits(data_dir, seed=17):
    meta_path=find_metadata(data_dir); df=pd.read_csv(meta_path); required={"lesion_id","dx","image_id"}
    if not required.issubset(df.columns): raise ValueError(f"Expected columns {sorted(required)} in {meta_path}")
    root=meta_path.parent; paths={p.stem:p for p in root.rglob("*.jpg")}
    df["image"] = df.image_id.map(lambda key: str(paths.get(key,"")))
    df=df[df.dx.isin(CLASSES) & df.image.ne("")].copy()
    # Two group-stratified folds approximate 70/15/15 while keeping lesion IDs apart.
    folds=list(StratifiedGroupKFold(n_splits=20,shuffle=True,random_state=seed).split(df,df.dx,groups=df.lesion_id))
    train=pd.concat([df.iloc[indices] for _,indices in folds[:14]]).sort_index()
    val=pd.concat([df.iloc[indices] for _,indices in folds[14:17]]).sort_index()
    test=pd.concat([df.iloc[indices] for _,indices in folds[17:]]).sort_index()
    out=Path(data_dir)/"splits"; out.mkdir(parents=True,exist_ok=True)
    for name,part in (("train",train),("val",val),("test",test)): part.to_csv(out/f"{name}.csv",index=False)
    return train,val,test
