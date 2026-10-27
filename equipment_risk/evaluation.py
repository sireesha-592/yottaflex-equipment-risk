from pathlib import Path
import json
import pandas as pd

def evaluate(input_dir):
    p=Path(input_dir)
    risk=pd.read_csv(p/"risk_assessments.csv")
    failures=pd.read_csv(p/"failure_events.csv")
    gt_path=p/"ground_truth.csv"
    gt=pd.read_csv(gt_path) if gt_path.exists() else pd.DataFrame()
    # Synthetic machine-level ground truth: machine had a generated labelled failure.
    actual=set(failures.machine_id.astype(str)) if not failures.empty else set()
    predicted=set(risk.loc[risk.decision.eq("HIGH"),"machine_id"].astype(str)) if not risk.empty else set()
    tp=len(actual & predicted); fp=len(predicted-actual); fn=len(actual-predicted)
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0.0
    result={"evaluation_scope":"synthetic machine-level classification; not real-world performance",
            "actual_failure_machines":len(actual),"predicted_high_risk_machines":len(predicted),
            "true_positives":tp,"false_positives":fp,"false_negatives":fn,
            "precision":round(precision,4),"recall":round(recall,4),"f1":round(f1,4),
            "risk_decision_counts":risk.decision.value_counts().to_dict() if not risk.empty else {},
            "known_injected_edge_cases":int(len(gt))}
    (p/"evaluation_summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result
