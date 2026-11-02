"""Staged CRNN + CTC trainer. Synthetic data checks training plumbing only."""
import argparse,csv,json,random
from pathlib import Path
import numpy as np

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--stage",choices=("pretrain","finetune","bd_only"),default="bd_only");parser.add_argument("--quick",action="store_true");parser.add_argument("--synthetic",action="store_true");parser.add_argument("--resume",action="store_true");parser.add_argument("--epochs",type=int,default=20);parser.add_argument("--batch-size",type=int,default=32);args=parser.parse_args()
    try:
        import torch
        from torch.utils.data import Dataset,DataLoader,Subset
        from PIL import Image
    except ImportError: raise SystemExit("Missing PyTorch/Pillow. Install isolated dependencies: pip install -r ml/requirements-ml.txt")
    from .charset import build_charset
    from .data_iam import read_iam
    from .data_bd import read_bd
    from .lexicon import build_lexicon
    from .model import build_model
    from .transforms import preprocess
    from .synth import fake_words,render_words
    random.seed(17);np.random.seed(17);torch.manual_seed(17)
    samples=[];sample_splits=[];pre_state=None;pre_charset=[];charset_extra=""
    if args.synthetic:
        samples=render_words(fake_words(160 if args.quick else 2000))
        sample_splits=[""]*len(samples)
        train_stage="synthetic_demo"
    elif args.stage=="pretrain":
        try: samples,_=read_iam("ml/data/iam")
        except FileNotFoundError as exc: print(f"{exc} Skipping IAM pretrain: no IAM samples loaded.");return
        sample_splits=[""]*len(samples)
        train_stage="iam_pretrain"
    else:
        try:
            frame,label_col,_=read_bd("ml/data/rx_bd")
            samples=[(row["_image"],str(row[label_col])) for _,row in frame.iterrows()]
            sample_splits=frame["_split"].fillna("").astype(str).tolist()
        except (FileNotFoundError,ValueError) as exc:
            raise SystemExit(str(exc))
        if args.stage=="finetune" and Path("ml/artifacts/rx/pretrain.pt").exists():
            pre_state=torch.load("ml/artifacts/rx/pretrain.pt",map_location="cpu",weights_only=False)
            pre_charset=pre_state.get("charset",[])
            charset_extra="".join(pre_charset[1:]) if pre_charset else ""
            print("Found IAM pretraining checkpoint; transferring compatible CNN/LSTM weights and matching character rows.")
        elif args.stage=="finetune":
            pre_state=None;pre_charset=[];charset_extra=""
            print("IAM pretraining checkpoint missing; fine-tuning starts from scratch (= BD-only).")
        else: pre_state=None;pre_charset=[];charset_extra=""
        train_stage=args.stage
    filtered=[(path,text,split) for (path,text),split in zip(samples,sample_splits) if text.strip() and len(text)<=30]
    samples=[(path,text) for path,text,_ in filtered];sample_splits=[split for _,_,split in filtered]
    if len(samples)<4: raise SystemExit("Too few usable RxRead word images. Check the requested dataset folder and labels.")
    charset=build_charset([text for _,text in samples]+([charset_extra] if charset_extra else [])); chars={c:i for i,c in enumerate(charset)}
    height,width=32,128
    class Words(Dataset):
        def __init__(self,items): self.items=items
        def __len__(self): return len(self.items)
        def __getitem__(self,index):
            path,text=self.items[index]
            try:
                with Image.open(path) as im: x=preprocess(im,height,width)
            except (OSError,ValueError): x=np.full((1,height,width),-1,dtype=np.float32)
            ids=[chars[c] for c in text if c in chars];return torch.from_numpy(x),torch.tensor(ids,dtype=torch.long),text
    dataset=Words(samples)
    from sklearn.model_selection import GroupShuffleSplit,train_test_split
    official_train=[i for i,value in enumerate(sample_splits) if value=="train"]
    official_val=[i for i,value in enumerate(sample_splits) if value in {"val","validation"}]
    official_test=[i for i,value in enumerate(sample_splits) if value in {"test","testing"}]
    if train_stage!="iam_pretrain" and official_train and official_val:
        train_idx=np.asarray(official_train);val_idx=np.asarray(official_val)
        if official_test:
            split_dir=Path("ml/data/rx_bd/splits");split_dir.mkdir(parents=True,exist_ok=True)
            import pandas as pd
            pd.DataFrame([{"image":samples[i][0],"text":samples[i][1]} for i in official_test]).to_csv(split_dir/"test.csv",index=False)
        print(f"Using official BD splits: train={len(train_idx)}, val={len(val_idx)}, test={len(official_test)}")
    elif train_stage=="iam_pretrain":
        groups=[Path(path).stem.rsplit("-",2)[0] for path,_ in samples]
        train_idx,val_idx=next(GroupShuffleSplit(n_splits=1,test_size=.10,random_state=17).split(np.arange(len(samples)),groups=groups))
    else:
        indices=np.arange(len(samples));labels=[text for _,text in samples]
        try: train_idx,val_idx=train_test_split(indices,test_size=.15,random_state=17,stratify=labels)
        except ValueError: train_idx,val_idx=train_test_split(indices,test_size=.15,random_state=17)
    train_set,val_set=Subset(dataset,train_idx),Subset(dataset,val_idx)
    def collate(batch):
        images,labels,texts=zip(*batch);return torch.stack(images),torch.cat(labels),torch.tensor([len(x) for x in labels]),texts
    batch_size=8 if args.quick else args.batch_size
    train_loader=DataLoader(train_set,batch_size=batch_size,shuffle=True,collate_fn=collate);val_loader=DataLoader(val_set,batch_size=batch_size,shuffle=False,collate_fn=collate)
    model=build_model(len(charset),height,width)
    if train_stage=="finetune" and pre_state:
        target=model.state_dict();source=pre_state.get("state_dict",{})
        for key,value in source.items():
            if key in target and target[key].shape==value.shape and not key.startswith("head."): target[key]=value
        if "head.weight" in source:
            for old_idx,char in enumerate(pre_charset):
                new_idx=charset.index(char) if char in charset else None
                if new_idx is not None: target["head.weight"][new_idx]=source["head.weight"][old_idx]
        if "head.bias" in source:
            for old_idx,char in enumerate(pre_charset):
                new_idx=charset.index(char) if char in charset else None
                if new_idx is not None: target["head.bias"][new_idx]=source["head.bias"][old_idx]
        model.load_state_dict(target)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu");model.to(device)
    optimizer=torch.optim.Adam(model.parameters(),lr=.001 if train_stage=="iam_pretrain" else .0003);criterion=torch.nn.CTCLoss(blank=0,zero_infinity=True)
    epochs=2 if args.quick else args.epochs;logs=[];best=float("inf");artifacts=Path("ml/artifacts/rx");reports=Path("ml/reports/rx");artifacts.mkdir(parents=True,exist_ok=True);reports.mkdir(parents=True,exist_ok=True)
    checkpoint=artifacts/"pretrain.pt" if train_stage=="iam_pretrain" else artifacts/"model.pt"
    if args.resume and checkpoint.exists():
        state=torch.load(checkpoint,map_location=device,weights_only=False);model.load_state_dict(state["state_dict"]);optimizer.load_state_dict(state["optimizer"]);print(f"Resumed {checkpoint}")
    def run_epoch(loader,training):
        model.train(training);total=0.;count=0;errors=0;characters=0
        for images,labels,label_lengths,texts in loader:
            images=images.to(device);labels=labels.to(device);optimizer.zero_grad(set_to_none=True)
            with torch.set_grad_enabled(training):
                log_probs=model(images);t,b,c=log_probs.shape;input_lengths=torch.full((b,),t,dtype=torch.long,device=device)
                if torch.any(label_lengths>input_lengths-1): raise RuntimeError("CTC output has too few time steps for at least one label; reduce label length or increase input width.")
                loss=criterion(log_probs,labels,input_lengths,label_lengths.to(device))
                if training: loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);optimizer.step()
            total+=float(loss.detach())*b;count+=b
            if not training:
                from .decode import best_path
                for i,truth in enumerate(texts):
                    pred=best_path(log_probs[:,i,:].detach().cpu().numpy(),charset);errors+=_edit_distance(pred,truth);characters+=len(truth)
        return total/max(1,count),errors/max(1,characters)
    for epoch in range(epochs):
        train_loss,_=run_epoch(train_loader,True);val_loss,cer=run_epoch(val_loader,False);logs.append({"epoch":epoch+1,"train_loss":train_loss,"val_loss":val_loss,"val_cer":cer})
        print(f"epoch {epoch+1}/{epochs}: train_loss={train_loss:.4f} val_loss={val_loss:.4f} val_cer={cer:.4f}")
        state={"state_dict":model.state_dict(),"optimizer":optimizer.state_dict(),"epoch":epoch+1,"charset":charset}
        torch.save(state,checkpoint)
        if cer<best:
            best=cer
            if checkpoint.name!="model.pt": torch.save(state,artifacts/"best_pretrain.pt")
            else: torch.save(state,artifacts/"best_model.pt")
    (reports/"training_curves.csv").write_text("epoch,train_loss,val_loss,val_cer\n"+"".join(f"{r['epoch']},{r['train_loss']},{r['val_loss']},{r['val_cer']}\n" for r in logs))
    (reports/"architecture.txt").write_text(f"CRNN CNN + 2-layer bidirectional LSTM + CTC\nParameters: {sum(p.numel() for p in model.parameters()):,}\nInput: 1x{height}x{width}\nTime steps: {width//4}\nCharset entries including blank: {len(charset)}\n")
    lexicon=build_lexicon();(artifacts/"charset.json").write_text(json.dumps(charset,ensure_ascii=False,indent=2));(artifacts/"lexicon.json").write_text(json.dumps(lexicon,ensure_ascii=False,indent=2))
    meta={"architecture":"CRNN","height":height,"width":width,"mean":0,"std":1,"stage":train_stage,"trained":not args.synthetic and train_stage!="iam_pretrain","synthetic":args.synthetic,"data_used":"synthetic demo" if args.synthetic else args.stage,"validation_cer":None if args.synthetic else best,"version":"synthetic-bootstrap" if args.synthetic else "research-checkpoint"}
    (artifacts/"model_meta.json").write_text(json.dumps(meta,indent=2))
    print("Synthetic run only validates the CTC training path; its weights are marked untrained and will not load in the inference service." if args.synthetic else f"Saved trained-stage checkpoint at {checkpoint}; validation CER={best:.4f}. Independent test evaluation is still required.")

def _edit_distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        nxt=[i]
        for j,y in enumerate(b,1): nxt.append(min(nxt[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=nxt
    return row[-1]

if __name__=="__main__":main()
