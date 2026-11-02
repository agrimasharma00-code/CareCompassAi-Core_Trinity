import argparse, csv, json, random, time
from pathlib import Path
import numpy as np

def main():
    p=argparse.ArgumentParser(); p.add_argument("--model",choices=("custom","effnet","resnet50"),default="custom"); p.add_argument("--quick",action="store_true"); p.add_argument("--synthetic",action="store_true"); p.add_argument("--resume",action="store_true"); p.add_argument("--data-dir",default="ml/data/ham10000"); p.add_argument("--epochs",type=int,default=20); a=p.parse_args()
    try:
        import torch
        from PIL import Image
        from torch.utils.data import Dataset,DataLoader,WeightedRandomSampler
        from torchvision import transforms
        from sklearn.metrics import f1_score
    except ImportError as exc: raise SystemExit("Missing ML dependencies. Activate the isolated environment and install -r ml/requirements-ml.txt") from exc
    from .config import CLASSES,IMAGENET_MEAN,IMAGENET_STD,IMAGE_SIZE
    from .data import grouped_splits
    from .models import build_model
    from .synthetic import make_synthetic
    from .transforms import preprocess_eval,training_transform
    random.seed(17); np.random.seed(17); torch.manual_seed(17)
    root=Path(a.data_dir)
    if a.synthetic:
        rows=make_synthetic(root/"synthetic",20); import pandas as pd; df=pd.DataFrame(rows); train=pd.concat([group.iloc[:14] for _,group in df.groupby("dx")]);val=pd.concat([group.iloc[14:17] for _,group in df.groupby("dx")]);test=pd.concat([group.iloc[17:] for _,group in df.groupby("dx")])
        split_root=root/"splits";split_root.mkdir(parents=True,exist_ok=True)
        for name,part in (("train",train),("val",val),("test",test)):part.to_csv(split_root/f"{name}.csv",index=False)
    else:
        try: train,val,test=grouped_splits(root)
        except (FileNotFoundError,ValueError) as exc: raise SystemExit(str(exc))
    size=128 if a.quick else IMAGE_SIZE; epochs=2 if a.quick else (a.epochs)
    train_tf=training_transform(size); eval_tf=lambda image:preprocess_eval(image,size)
    class Rows(Dataset):
        def __init__(self,df,tf): self.df=df.reset_index(drop=True); self.tf=tf
        def __len__(self): return len(self.df)
        def __getitem__(self,i):
            row=self.df.iloc[i]
            with Image.open(row.image) as im: x=self.tf(im.convert("RGB"))
            return x,CLASSES.index(row.dx)
    if a.quick: train=train.sample(frac=.1,random_state=17) if len(train)>10 else train
    tr=Rows(train,train_tf); va=Rows(val,eval_tf); counts=train.dx.value_counts(); weights=[1/counts[x] for x in train.dx]
    sampler=WeightedRandomSampler(torch.tensor(weights,dtype=torch.double),len(weights),replacement=True)
    loaders={"train":DataLoader(tr,batch_size=16 if a.quick else 32,sampler=sampler),"val":DataLoader(va,batch_size=32)}
    model=build_model(a.model).to("cuda" if torch.cuda.is_available() else "cpu"); device=next(model.parameters()).device
    if a.model=="effnet":
        for param in model.features.parameters(): param.requires_grad=False
    elif a.model=="resnet50":
        for name,param in model.named_parameters(): param.requires_grad=name.startswith("fc.")
    optimizer=torch.optim.AdamW(filter(lambda p:p.requires_grad,model.parameters()),lr=1e-3); scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=max(1,epochs)); criterion=torch.nn.CrossEntropyLoss(label_smoothing=.05)
    out=Path("ml/artifacts/derma"); out.mkdir(parents=True,exist_ok=True); report=Path(f"ml/reports/derma/{a.model}"); report.mkdir(parents=True,exist_ok=True); checkpoints=Path("ml/artifacts/derma/checkpoints");checkpoints.mkdir(parents=True,exist_ok=True);latest=checkpoints/f"{a.model}_latest.pt"
    best=-1; history=[]; start_epoch=0;started=time.time(); stale=0; scaler=torch.amp.GradScaler("cuda",enabled=device.type=="cuda")
    if a.resume and latest.exists():
        state=torch.load(latest,map_location=device,weights_only=False);model.load_state_dict(state["state_dict"]);optimizer.load_state_dict(state["optimizer"]);history=state.get("history",[]);best=state.get("best",-1);start_epoch=state.get("epoch",0);print(f"Resumed {latest} at epoch {start_epoch}.")
    for epoch in range(start_epoch,epochs):
        if epoch==1 and a.model!="custom":
            layers=model.features if a.model=="effnet" else model.layer4
            for param in layers.parameters(): param.requires_grad=True
            optimizer=torch.optim.AdamW(filter(lambda p:p.requires_grad,model.parameters()),lr=1e-4);scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=max(1,epochs-1))
        for phase in ("train","val"):
            model.train(phase=="train"); ys=[]; ps=[]; total=0.; n=0
            for x,y in loaders[phase]:
                x,y=x.to(device),y.to(device); optimizer.zero_grad()
                with torch.set_grad_enabled(phase=="train"), torch.autocast(device_type=device.type,enabled=device.type=="cuda"):
                    z=model(x); loss=criterion(z,y)
                    if phase=="train":
                        scaler.scale(loss).backward();scaler.unscale_(optimizer);torch.nn.utils.clip_grad_norm_(model.parameters(),1.);scaler.step(optimizer);scaler.update()
                total+=loss.item()*len(y); n+=len(y); ys.extend(y.cpu().tolist()); ps.extend(z.argmax(1).cpu().tolist())
            score=f1_score(ys,ps,average="macro") if ys else 0.; history.append({"epoch":epoch+1,"phase":phase,"loss":total/max(1,n),"macro_f1":score})
            if phase=="val" and score>best:
                best=score;stale=0;torch.save({"state_dict":model.state_dict(),"model":a.model,"classes":CLASSES},out/"model.pt")
            elif phase=="val": stale+=1
        scheduler.step()
        torch.save({"state_dict":model.state_dict(),"optimizer":optimizer.state_dict(),"epoch":epoch+1,"history":history,"best":best},latest)
        with (report/"training_log.csv").open("w",newline="") as f: writer=csv.DictWriter(f,fieldnames=history[0].keys()); writer.writeheader(); writer.writerows(history)
        if stale>=5: print("Early stopping after validation macro-F1 stopped improving.");break
    (Path("ml/reports/derma")/f"architecture_{a.model}.txt").write_text(f"Model: {a.model}\nParameters: {sum(p.numel() for p in model.parameters()):,}\nInput: 3x{size}x{size}\n")
    (out/"model_meta.json").write_text(json.dumps({"architecture":a.model,"classes":CLASSES,"input_size":size,"mean":IMAGENET_MEAN,"std":IMAGENET_STD,"synthetic":a.synthetic,"trained_seconds":round(time.time()-started,2)},indent=2))
    print(f"Saved model to {out}; synthetic={a.synthetic}; macro-F1 (validation)={best:.4f}")
if __name__=="__main__": main()
