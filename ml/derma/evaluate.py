import argparse,json
from pathlib import Path
import numpy as np

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--model",choices=("custom","effnet","resnet50"),default="custom");parser.add_argument("--synthetic",action="store_true");args=parser.parse_args()
    try:
        import torch
        from PIL import Image
        from sklearn.metrics import accuracy_score,balanced_accuracy_score,f1_score,precision_recall_fscore_support,confusion_matrix,classification_report,roc_auc_score
        import matplotlib.pyplot as plt
        from sklearn.preprocessing import label_binarize
    except ImportError as exc: raise SystemExit("Install the isolated ML dependencies: pip install -r ml/requirements-ml.txt") from exc
    from .config import CLASSES,IMAGENET_MEAN,IMAGENET_STD,HIGH_RISK
    from .models import build_model
    from .transforms import preprocess_eval
    root=Path("ml/artifacts/derma");meta_path=root/"model_meta.json";checkpoint=root/"model.pt";split=Path("ml/data/ham10000/splits/test.csv")
    if not meta_path.exists() or not checkpoint.exists(): raise SystemExit("No DermaScan checkpoint. Train first: python -m ml.derma.train --synthetic --quick")
    meta=json.loads(meta_path.read_text())
    if meta.get("synthetic") and not args.synthetic: raise SystemExit("Checkpoint is synthetic-only; pass --synthetic to label its evaluation honestly.")
    if not split.exists(): raise SystemExit("No test split CSV. Train first so ml/data/ham10000/splits/test.csv is created.")
    import pandas as pd
    df=pd.read_csv(split);size=int(meta.get("input_size",224));model=build_model(meta.get("architecture",args.model),pretrained=False);state=torch.load(checkpoint,map_location="cpu",weights_only=False);model.load_state_dict(state.get("state_dict",state));model.eval()
    truths=[];predictions=[];probabilities=[];tensors=[];images=[]
    for _,row in df.iterrows():
        try:
            with Image.open(row.image) as opened: image=opened.convert("RGB").copy()
            x=preprocess_eval(image,size).unsqueeze(0)
            with torch.no_grad(): probs=model(x).softmax(1)[0].numpy()
            truths.append(CLASSES.index(row.dx));predictions.append(int(probs.argmax()));probabilities.append(probs);tensors.append(x);images.append(image)
        except (OSError,ValueError,KeyError): continue
    if not truths: raise SystemExit(f"No readable test images in {split}.")
    y=np.asarray(truths);pred=np.asarray(predictions);probs=np.asarray(probabilities);pr,rc,f1,support=precision_recall_fscore_support(y,pred,labels=list(range(7)),zero_division=0)
    high_ids=[CLASSES.index(code) for code in HIGH_RISK];high_mask=np.isin(y,high_ids); high_recall=float(np.isin(pred[high_mask],high_ids).mean()) if high_mask.any() else None
    try: auc=float(roc_auc_score(label_binarize(y,classes=list(range(7))),probs,average="macro",multi_class="ovr"))
    except ValueError: auc=None
    metrics={"evaluation_kind":"synthetic_demo_only" if meta.get("synthetic") or args.synthetic else "held_out_test_split","dataset":"synthetic colored blobs" if meta.get("synthetic") else "HAM10000","samples":len(y),"accuracy":float(accuracy_score(y,pred)),"balanced_accuracy":float(balanced_accuracy_score(y,pred)),"macro_f1":float(f1_score(y,pred,average="macro")),"high_risk_recall_mel_bcc_akiec":high_recall,"roc_auc_ovr_macro":auc,"per_class":{code:{"precision":float(pr[i]),"recall":float(rc[i]),"f1":float(f1[i]),"support":int(support[i])} for i,code in enumerate(CLASSES)}}
    out=Path(f"ml/reports/derma/{args.model}");out.mkdir(parents=True,exist_ok=True);(out/"metrics.json").write_text(json.dumps(metrics,indent=2));(out/"classification_report.txt").write_text(classification_report(y,pred,labels=list(range(7)),target_names=list(CLASSES),zero_division=0))
    fig,ax=plt.subplots(figsize=(7,6));cm=confusion_matrix(y,pred,labels=list(range(7)));im=ax.imshow(cm,cmap="Blues");ax.set(xticks=range(7),yticks=range(7),xticklabels=CLASSES,yticklabels=CLASSES,xlabel="Predicted",ylabel="True");fig.colorbar(im,ax=ax);fig.tight_layout();fig.savefig(out/"confusion_matrix.png");plt.close(fig)
    training_log=Path(f"ml/reports/derma/{args.model}/training_log.csv")
    if training_log.exists():
        logs=pd.read_csv(training_log);fig,ax=plt.subplots();ax.plot(logs[logs.phase=="train"].epoch,logs[logs.phase=="train"].loss,label="train");ax.plot(logs[logs.phase=="val"].epoch,logs[logs.phase=="val"].loss,label="validation");ax.legend();ax.set(xlabel="epoch",ylabel="loss");fig.savefig(out/"training_curves.png",bbox_inches="tight");plt.close(fig)
    fig,ax=plt.subplots()
    for i,code in enumerate(CLASSES):
        binary=(y==i).astype(int)
        if binary.min()==binary.max():continue
        from sklearn.metrics import roc_curve,auc
        fpr,tpr,_=roc_curve(binary,probs[:,i]);ax.plot(fpr,tpr,label=f"{code} AUC={auc(fpr,tpr):.2f}")
    ax.plot([0,1],[0,1],"--",color="gray");ax.legend(fontsize=7);ax.set(xlabel="False positive rate",ylabel="True positive rate");fig.savefig(out/"roc_curves.png",bbox_inches="tight");plt.close(fig)
    try:
        from .config import IMAGENET_MEAN,IMAGENET_STD
        from ml.common.gradcam import gradcam
        layer=next(module for module in reversed(list(model.modules())) if isinstance(module,torch.nn.Conv2d));count=min(8,len(tensors));fig,axes=plt.subplots(2,4,figsize=(12,6))
        for ax in axes.flat: ax.axis("off")
        for i in range(count):
            cam=gradcam(model,tensors[i],layer);ax=axes.flat[i];ax.imshow(images[i]);ax.imshow(cam,cmap="jet",alpha=.35);ax.set_title(f"true {CLASSES[y[i]]} / pred {CLASSES[pred[i]]}",fontsize=8)
        fig.tight_layout();fig.savefig(out/"gradcam_samples.png");plt.close(fig)
    except Exception as exc: print(f"Grad-CAM sample rendering skipped: {exc}")
    comparison=["# DermaScan model comparison","","| Model | Evaluation set | Samples | Accuracy | Balanced accuracy | Macro-F1 | High-risk recall |","|---|---:|---:|---:|---:|---:|---:|"]
    for model_name in ("custom","effnet","resnet50"):
        metrics_file=Path(f"ml/reports/derma/{model_name}/metrics.json")
        if not metrics_file.exists():continue
        item=json.loads(metrics_file.read_text())
        comparison.append(f"| {model_name} | {item.get('evaluation_kind','unknown')} | {item.get('samples','—')} | {item.get('accuracy','—')} | {item.get('balanced_accuracy','—')} | {item.get('macro_f1','—')} | {item.get('high_risk_recall_mel_bcc_akiec','—')} |")
    comparison.extend(["","Accuracy alone can hide weak recall on the rarer high-risk classes; inspect the actual balanced accuracy, macro-F1 and high-risk recall above. Synthetic-demo results are not clinical or real-image evidence."])
    Path("ml/reports/derma/comparison.md").write_text("\n".join(comparison)+"\n",encoding="utf-8")
    print(json.dumps(metrics,indent=2))
if __name__=="__main__":main()
