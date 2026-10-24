import sys, json
from pathlib import Path
import numpy as np
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import FeatureUnion,Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import f1_score,confusion_matrix,recall_score
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.loaders import load_dataset
from app.core.normalize import normalize_text
from app.core.triage import URGENCY,keyword_rule

def data():
 rows=load_dataset(); X=[normalize_text(r["request"]["user_input"]) for r in rows]; y=[r["response"]["care_type"] or "followup" for r in rows]; groups=X
 return rows,X,np.array(y),np.array(groups)
def make():
 features=FeatureUnion([("char",TfidfVectorizer(analyzer="char_wb",ngram_range=(2,5),min_df=1)),("word",TfidfVectorizer(ngram_range=(1,2),min_df=1))])
 return Pipeline([("features",features),("clf",LogisticRegression(max_iter=1500,class_weight="balanced"))])
def main():
 rows,X,y,g=data(); folds=GroupKFold(n_splits=5); pred=np.empty(len(y),dtype=object); svc_oof=np.empty(len(y),dtype=object); ur_model=np.empty(len(y),dtype=object); log_conf=np.zeros(len(y)); svc_conf=np.zeros(len(y))
 augpath=Path(__file__).resolve().parents[1]/"data"/"augment"/"paraphrases.jsonl"
 aug=[json.loads(line) for line in augpath.read_text(encoding="utf-8").splitlines()] if augpath.exists() else []
 for fold,(tr,te) in enumerate(folds.split(X,y,g),1):
  train_text=[X[i] for i in tr];train_y=list(y[tr]); train_groups=set(g[tr])
  fold_aug=[a for a in aug if normalize_text(a["source_text"]) in train_groups]
  train_text.extend(normalize_text(a["text"]) for a in fold_aug);train_y.extend(a["care_type"] for a in fold_aug)
  m=make();m.fit(train_text,train_y); p=m.predict([X[i] for i in te]); pred[te]=p
  urgency_train=[URGENCY.get(c,"same_day") for c in train_y]; um=make();um.fit(train_text,urgency_train); ur_model[te]=um.predict([X[i] for i in te])
  svc=Pipeline([("features",make().named_steps["features"]),("clf",CalibratedClassifierCV(LinearSVC(class_weight="balanced"),cv=3))]);svc.fit(train_text,train_y); ps=svc.predict([X[i] for i in te]);svc_oof[te]=ps
  svc_probs=svc.predict_proba([X[i] for i in te]);svc_conf[te]=svc_probs.max(axis=1)
  print(f"fold {fold}: logistic macro-F1={f1_score(y[te],p,average='macro',zero_division=0):.3f}, calibrated SVC macro-F1={f1_score(y[te],ps,average='macro',zero_division=0):.3f}")
  probs=m.predict_proba([X[i] for i in te]);log_conf[te]=probs.max(axis=1)
 # report group split metrics from out-of-fold predictions only
 use_svc=f1_score(y,svc_oof,average="macro",zero_division=0)>f1_score(y,pred,average="macro",zero_division=0); chosen=svc_oof if use_svc else pred
 confidence=svc_conf if use_svc else log_conf; prior=chosen.copy()
 for i,txt in enumerate(X):
  rule=keyword_rule(txt)
  if rule and rule!=prior[i] and confidence[i]<.65:prior[i]=rule
 urgency_y=np.array([URGENCY.get(c,"same_day") for c in y]); baseline=np.array([URGENCY.get(c,"same_day") for c in prior]);print("care_type macro-F1 (selected OOF head)",f1_score(y,chosen,average="macro",zero_division=0));print("care_type macro-F1 with keyword prior",f1_score(y,prior,average="macro",zero_division=0));print("logistic OOF macro-F1",f1_score(y,pred,average="macro",zero_division=0));print("calibrated SVC OOF macro-F1",f1_score(y,svc_oof,average="macro",zero_division=0));print("urgency model macro-F1",f1_score(urgency_y,ur_model,average="macro",zero_division=0));print("predicted care_type default-map urgency macro-F1",f1_score(urgency_y,baseline,average="macro",zero_division=0));print("confusion matrix\n",confusion_matrix(y,chosen,labels=sorted(set(y))));print("emergency recall",recall_score(y=="emergency_112",prior=="emergency_112",zero_division=0));print("under-triage count",sum((y=="emergency_112")&(prior!="emergency_112")))
 final_x=list(X); final_y=list(y); final_x.extend(normalize_text(a["text"]) for a in aug); final_y.extend(a["care_type"] for a in aug)
 if f1_score(y,svc_oof,average="macro",zero_division=0)>f1_score(y,pred,average="macro",zero_division=0):
  final=Pipeline([("features",make().named_steps["features"]),("clf",CalibratedClassifierCV(LinearSVC(class_weight="balanced"),cv=3))]);print("Selected calibrated LinearSVC by group-split care macro-F1")
 else: final=make();print("Selected LogisticRegression by group-split care macro-F1")
 final.fit(final_x,final_y)
 urgency_final=make(); urgency_final.fit(final_x,[URGENCY.get(c,"same_day") for c in final_y])
 use_urgency=f1_score(urgency_y,ur_model,average="macro",zero_division=0)>f1_score(urgency_y,baseline,average="macro",zero_division=0)
 print("Selected urgency head:","trained model" if use_urgency else "care-type default map")
 import joblib; out=Path(__file__).resolve().parents[1]/"models"/"triage.joblib";out.parent.mkdir(exist_ok=True);joblib.dump({"care_model":final,"urgency_model":urgency_final if use_urgency else None},out);print("saved",out)
if __name__=="__main__":main()
