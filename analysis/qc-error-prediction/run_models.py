#!/usr/bin/env python3
"""Run preregistered classifier and predictive-band evaluations."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

SEED=294
ROOT=Path(__file__).resolve().parent; TABLES=ROOT/"tables"
CACHE=Path(os.environ.get("AXIOM_QC_ERROR_CACHE",Path.home()/".cache/axiom-oracles/qc-error-pilot"))/"features.parquet"
META={"estimator":"scikit-learn HistGradientBoosting", "seed":SEED,
      "classifier":{"max_iter":200,"learning_rate":0.05,"max_leaf_nodes":15,"l2_regularization":1.0},
      "quantile":{"max_iter":250,"learning_rate":0.05,"max_leaf_nodes":15,"l2_regularization":1.0}}

NONFEATURE={"case_id","label_error","status","error_amount","issued_benefit","verified_benefit","weight","excluded_universe"}
RAW=["state","yrmonth","household_size","member_count","child_count","elderly_count","disabled_or_elderly",
     "earned_income","unearned_income","shelter_expense","utility_amount","utility_tier","medical_expenses",
     "dependent_care_expense","child_support_expense","homeless","categorically_eligible","liquid_resources"]

def matrix(df, cols):
    x=pd.get_dummies(df[cols],columns=[c for c in cols if not pd.api.types.is_numeric_dtype(df[c])],dtype=float)
    return x.astype(float).replace([np.inf,-np.inf],np.nan)
def fold_id(case): return int(hashlib.sha256((str(SEED)+case).encode()).hexdigest()[:8],16)%5
def clf(): return HistGradientBoostingClassifier(random_state=SEED,max_iter=200,learning_rate=.05,max_leaf_nodes=15,l2_regularization=1.)
def qreg(q): return HistGradientBoostingRegressor(loss="quantile",quantile=q,random_state=SEED,max_iter=250,learning_rate=.05,max_leaf_nodes=15,l2_regularization=1.)
def metrics(y,p): return {"auc_roc":roc_auc_score(y,p),"pr_auc":average_precision_score(y,p),"brier":brier_score_loss(y,p),"n":len(y),"errors":int(y.sum())}
def clean(v):
    if isinstance(v,(np.floating,float)): return round(float(v),6)
    if isinstance(v,(np.integer,)): return int(v)
    return v
def dump(name,obj): (TABLES/f"{name}.json").write_text(json.dumps(obj,indent=2,sort_keys=True,default=clean)+"\n")
def md_table(headers,rows):
    return "| "+" | ".join(headers)+" |\n|"+"|".join(["---"]*len(headers))+"|\n"+"".join("| "+" | ".join(map(str,r))+" |\n" for r in rows)

def classifier_results(df):
    folds=np.array([fold_id(x) for x in df.case_id]); y=df.label_error.to_numpy()
    sets={"raw":RAW,"raw_plus_engine":RAW+[c for c in df if c.startswith("engine_")]}
    result={"metadata":META,"cv":[],"cv_summary":[],"leave_one_state_out":[]}
    for name,cols in sets.items():
        X=matrix(df,cols); fold_metrics=[]
        for f in range(5):
            tr=folds!=f; te=~tr; m=clf().fit(X.loc[tr],y[tr]); z=metrics(y[te],m.predict_proba(X.loc[te])[:,1]); z.update(feature_set=name,fold=f); fold_metrics.append(z); result["cv"].append(z)
        s={"feature_set":name}
        for metric in ("auc_roc","pr_auc","brier"):
            vals=[x[metric] for x in fold_metrics]; s[metric+"_mean"]=np.mean(vals);s[metric+"_sd"]=np.std(vals,ddof=1)
        result["cv_summary"].append(s)
        for state in sorted(df.state.unique()):
            te=df.state.eq(state).to_numpy(); m=clf().fit(X.loc[~te],y[~te]); z=metrics(y[te],m.predict_proba(X.loc[te])[:,1]);z.update(feature_set=name,held_out_state=state);result["leave_one_state_out"].append(z)
    a,b=result["cv_summary"]
    result["delta"]={k.replace("_mean",""):b[k]-a[k] for k in ("auc_roc_mean","pr_auc_mean","brier_mean")}
    return result

def bands(df):
    folds=np.array([fold_id(x) for x in df.case_id]); y=df.verified_benefit.to_numpy(); issued=df.issued_benefit.to_numpy(); err=df.label_error.to_numpy().astype(bool)
    X=matrix(df,RAW); qs=(.01,.05,.10,.90,.95,.99); pred={q:np.zeros(len(df)) for q in qs}
    for f in range(5):
        tr=folds!=f;te=~tr
        for q in qs: pred[q][te]=qreg(q).fit(X.loc[tr],y[tr]).predict(X.loc[te])
    result={"metadata":META,"design":"5-fold out-of-fold verified-input predictive bands; issued RAWBEN flagged","overall":[],"per_state":[]}
    for lo,hi in ((.05,.95),(.10,.90),(.01,.99)):
        flag=(issued<pred[lo])|(issued>pred[hi]); covered=(y>=pred[lo])&(y<=pred[hi])
        def row(mask,label):
            return {"group":label,"band":f"q{int(lo*100)}-q{int(hi*100)}","n":int(mask.sum()),"errors":int((err&mask).sum()),
                    "non_error_coverage":float(covered[mask&~err].mean()),"error_flag_rate_recall":float(flag[mask&err].mean()),
                    "flagged":int((flag&mask).sum()),"error_flagged":int((flag&mask&err).sum())}
        result["overall"].append(row(np.ones(len(df),bool),"all"))
        for state in sorted(df.state.unique()): result["per_state"].append(row(df.state.eq(state).to_numpy(),state))
    return result

def labels(df):
    rows=[]
    for s,g in df.groupby("state",sort=True): rows.append({"state":s,"loaded":len(g),"errors":int(g.label_error.sum()),"correct":int((1-g.label_error).sum()),"excluded":int(g.excluded_universe.iloc[0])})
    return {"definition":"STATUS in {2,3} and AMTERR > 0","rows":rows,"total":{"loaded":len(df),"errors":int(df.label_error.sum()),"correct":int((1-df.label_error).sum()),"excluded":sum(x["excluded"] for x in rows)}}

def main():
    TABLES.mkdir(parents=True,exist_ok=True);df=pd.read_parquet(CACHE).sort_values(["state","case_id"]).reset_index(drop=True)
    l=labels(df);c=classifier_results(df);q=bands(df);dump("label_counts",l);dump("lift",c);dump("qrf_coverage",q)
    (TABLES/"label_counts.md").write_text(md_table(["State","Loaded","Errors","Correct","Excluded"],[[r[k] for k in ("state","loaded","errors","correct","excluded")] for r in l["rows"]]))
    rows=[]
    for r in c["cv_summary"]: rows.append([r["feature_set"],f'{r["auc_roc_mean"]:.3f}±{r["auc_roc_sd"]:.3f}',f'{r["pr_auc_mean"]:.3f}±{r["pr_auc_sd"]:.3f}',f'{r["brier_mean"]:.3f}±{r["brier_sd"]:.3f}'])
    rows += [[f'LOSO {r["held_out_state"]} {r["feature_set"]}',f'{r["auc_roc"]:.3f}',f'{r["pr_auc"]:.3f}',f'{r["brier"]:.3f}'] for r in c["leave_one_state_out"]]
    (TABLES/"lift.md").write_text(md_table(["Evaluation / features","AUC-ROC","PR-AUC","Brier"],rows))
    rows=[[r["group"],r["band"],r["n"],r["errors"],f'{r["non_error_coverage"]:.3f}',f'{r["error_flag_rate_recall"]:.3f}',r["flagged"],r["error_flagged"]] for r in q["overall"]+q["per_state"]]
    (TABLES/"qrf_coverage.md").write_text(md_table(["Group","Band","N","Errors","Non-error coverage","Error recall","Flagged","Errors flagged"],rows))
if __name__=="__main__": main()
