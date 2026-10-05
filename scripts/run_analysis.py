import hashlib
import json
import platform
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data import DATA_URL, FEATURES, ROOT, SEED, binary_experiment, load_data, make_features, split_data
from src.evaluation import (
    BOOTSTRAPS, CONTACT_COST, DISCOUNT, MARGIN, POPULATION, ab_test, balance_table,
    bootstrap_policies, curve_data, interval, model_metrics, policy_value, profit_curve,
)
from src.model import fit_response, fit_uplift, top_mask
from src.plots import plot_budget, plot_experiment, plot_policies, plot_qini


def main():
    for directory in ["reports/figures", "models", "data/processed"]:
        (ROOT / directory).mkdir(parents=True, exist_ok=True)
    raw = load_data()
    data = binary_experiment(raw)
    experiment = ab_test(data)
    balance = balance_table(data)
    balance.to_csv(ROOT / "reports/balance.csv", index=False)
    raw.groupby("segment").conversion.agg(["size", "sum", "mean"]).to_csv(ROOT / "reports/groups.csv")
    train, validation, test = split_data(data)
    split_rows = pd.concat([part.assign(split=name)[["split", "treatment", "conversion"]]
                            for name, part in [("train", train), ("validation", validation), ("test", test)]])
    split_rows.to_csv(ROOT / "data/processed/splits.csv")

    models = {}
    validation_metrics = {}
    validation_scores = {}
    for name in ["logistic", "forest"]:
        models[name] = fit_uplift(train, name)
        validation_scores[name] = models[name].predict(make_features(validation))
        validation_metrics[name] = model_metrics(validation, validation_scores[name])
    chosen_model = max(validation_metrics, key=lambda name: validation_metrics[name]["qini"])
    validation_curve = profit_curve(validation, validation_scores[chosen_model])
    selected_share = float(validation_curve.loc[validation_curve.profit.idxmax(), "budget"])
    validation_curve.to_csv(ROOT / "reports/validation_profit.csv", index=False)
    response_model = fit_response(train)
    joblib.dump({"model": models[chosen_model], "response_model": response_model,
                 "model_name": chosen_model, "share": selected_share, "features": FEATURES},
                ROOT / "models/uplift.joblib")

    test_scores = {name: model.predict(make_features(test)) for name, model in models.items()}
    test_scores["response"] = response_model.predict_proba(make_features(test))[:, 1]
    test_metrics = {name: model_metrics(test, scores) for name, scores in test_scores.items()}
    predictions = test[["treatment", "conversion"]].copy()
    for name, scores in test_scores.items():
        predictions[name] = scores
    predictions["selected"] = top_mask(test_scores[chosen_model], selected_share)
    predictions.to_csv(ROOT / "data/processed/test_predictions.csv")

    masks = {
        "none": np.zeros(len(test), dtype=bool), "all": np.ones(len(test), dtype=bool),
        "response_30": top_mask(test_scores["response"], 0.3),
        "uplift_30": top_mask(test_scores[chosen_model], 0.3),
        "selected": top_mask(test_scores[chosen_model], selected_share),
    }
    policies = {name: policy_value(test.conversion, test.treatment, mask) for name, mask in masks.items()}
    samples = bootstrap_policies(test, masks)
    for name in masks:
        policies[name]["ci"] = interval(samples[name])
    random_share = policies["uplift_30"]["share"]
    policies["random_30"] = {
        "share": random_share, "contacts": POPULATION * random_share,
        "extra_orders": policies["all"]["extra_orders"] * random_share,
        "profit": policies["all"]["profit"] * random_share,
        "ci": interval(samples["all"] * random_share),
    }
    differences = {}
    for name, comparator in [("uplift_30", "all"), ("selected", "all"),
                             ("uplift_30", "response_30")]:
        key = f"{name}_vs_{comparator}"
        differences[key] = {"profit": policies[name]["profit"] - policies[comparator]["profit"],
                            "ci": interval(samples[name] - samples[comparator])}
    differences["uplift_30_vs_random_30"] = {
        "profit": policies["uplift_30"]["profit"] - policies["random_30"]["profit"],
        "ci": interval(samples["uplift_30"] - samples["all"] * random_share),
    }

    curves = {name: curve_data(test, scores) for name, scores in test_scores.items()}
    for name, curve in curves.items():
        curve.to_csv(ROOT / f"reports/qini_{name}.csv", index=False)
    budgets = {"uplift": profit_curve(test, test_scores[chosen_model]),
               "response": profit_curve(test, test_scores["response"])}
    budgets["random"] = budgets["uplift"][["budget"]].copy()
    budgets["random"]["profit"] = budgets["random"].budget * policies["all"]["profit"]
    for name, curve in budgets.items():
        curve.to_csv(ROOT / f"reports/profit_{name}.csv", index=False)

    summary = {
        "source": DATA_URL, "source_sha256": hashlib.sha256((ROOT / "data/raw/hillstrom.csv.gz").read_bytes()).hexdigest(),
        "python": platform.python_version(), "seed": SEED, "raw_n": len(raw), "experiment_n": len(data),
        "missing_cells": int(raw.isna().sum().sum()), "identical_rows": int(raw.duplicated().sum()),
        "max_absolute_smd": float(balance.smd.abs().max()), "ab": experiment,
        "splits": {name: {"n": len(part), "orders": int(part.conversion.sum()),
                          "treated_n": int(part.treatment.sum())}
                   for name, part in [("train", train), ("validation", validation), ("test", test)]},
        "chosen_model": chosen_model, "selected_share": selected_share,
        "validation_metrics": validation_metrics, "test_metrics": test_metrics,
        "economics": {"population": POPULATION, "margin": MARGIN, "contact_cost": CONTACT_COST,
                      "discount": DISCOUNT, "bootstraps": BOOTSTRAPS, "currency": "USD"},
        "policies": policies, "differences": differences,
    }
    (ROOT / "reports/summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    figures = ROOT / "reports/figures"
    plot_experiment(experiment, figures / "experiment.png")
    plot_qini(curves, test_metrics, chosen_model, len(test), figures / "qini.png")
    plot_budget(budgets, selected_share, len(test), figures / "profit_curve.png")
    plot_policies(policies, figures / "profit_comparison.png")
    plot_experiment(experiment, figures / "experiment_it.png", language="it")
    plot_qini(curves, test_metrics, chosen_model, len(test), figures / "qini_it.png", language="it")
    plot_budget(budgets, selected_share, len(test), figures / "profit_curve_it.png", language="it")
    plot_policies(policies, figures / "profit_comparison_it.png", language="it")
    from scripts.extend_profit import main as extend_profit
    extend_profit()
    print(json.dumps({"chosen_model": chosen_model, "selected_share": selected_share,
                      "test_metrics": test_metrics, "policies": policies, "differences": differences},
                     ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
