import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data import ROOT, binary_experiment, load_data, split_data
from src.evaluation import BOOTSTRAPS, CONTACT_COST, MARGIN, POPULATION
from src.profit import (PROPENSITY, bootstrap_components, break_even_line, discount_limit,
                        policy_masks, policy_table, profit_difference, sensitivity_grid,
                        uplift_calibration)
from src.profit_plots import (plot_break_even, plot_calibration, plot_profit_intervals,
                              plot_sensitivity)


def main():
    report = ROOT / "reports"
    summary = json.loads((report / "summary.json").read_text())
    predictions = pd.read_csv(ROOT / "data/processed/test_predictions.csv", index_col="row_id")
    _, _, test = split_data(binary_experiment(load_data()))
    if not predictions.index.equals(test.index):
        raise ValueError("Saved predictions do not match the original test split")
    np.testing.assert_array_equal(predictions[["treatment", "conversion"]], test[["treatment", "conversion"]])
    data = predictions.assign(spend=test.spend)
    data.to_csv(ROOT / "data/processed/profit_test.csv")
    scores = data[summary["chosen_model"]].to_numpy()
    masks = policy_masks(scores)
    samples = bootstrap_components(data, masks)
    samples.to_csv(report / "bootstrap_components.csv", index=False)
    policies = policy_table(data, scores, samples)
    policies.to_csv(report / "policy_profit.csv", index=False)
    candidates = policies.loc[policies.policy != "mail_all"].reset_index(drop=True)
    grid = sensitivity_grid(candidates)
    grid.to_csv(report / "sensitivity_grid.csv", index=False)
    line = break_even_line(candidates)
    line.to_csv(report / "break_even.csv", index=False)
    calibration = uplift_calibration(data, scores)
    calibration.to_csv(report / "uplift_calibration.csv", index=False)
    difference = float(policies.loc[policies.policy == "top_30", "profit"].iloc[0]
                       - policies.loc[policies.policy == "mail_all", "profit"].iloc[0])
    difference_ci = profit_difference(samples)
    pd.DataFrame([{"comparison": "top_30_minus_mail_all", "population": POPULATION,
                   "contact_cost": CONTACT_COST, "discount": 0.0, "profit": difference,
                   "ci_low": difference_ci[0], "ci_high": difference_ci[1]}]).to_csv(
        report / "profit_difference.csv", index=False)
    results = {
        "currency": "USD", "population": POPULATION, "margin": MARGIN,
        "contact_cost": CONTACT_COST, "discount": 0.0, "propensity": PROPENSITY,
        "estimator": "Normalized IPW (Hajek) within the selected audience, relative to no mail",
        "bootstrap": {"resamples": BOOTSTRAPS, "seed": 42, "method": "Paired IID test-row percentile bootstrap",
                      "fixed_model": True, "fixed_policy_membership": True, "model_training_uncertainty": False},
        "model_sha256": hashlib.sha256((ROOT / "models/uplift.joblib").read_bytes()).hexdigest(),
        "model_code_sha256": hashlib.sha256((ROOT / "src/model.py").read_bytes()).hexdigest(),
        "chosen_model": summary["chosen_model"], "validation_share": summary["selected_share"],
        "test_n": len(data), "test_buyers": int(data.conversion.sum()),
        "top_30_minus_mail_all": {"profit": difference, "ci": difference_ci},
        "no_discount_mail_all_cost_limit": float(line.iloc[0].max_contact_cost_for_mail_all),
        "mail_all_discount_limit_at_zero_cost": discount_limit(candidates, 0),
        "mail_all_discount_limit_at_005_cost": discount_limit(candidates, 0.05),
        "default_grid_cell": grid.loc[(grid.contact_cost == CONTACT_COST) & (grid.discount == 0)].iloc[0].to_dict(),
        "negative_deciles": calibration.loc[calibration.negative_observed, "decile"].astype(int).tolist(),
        "negative_deciles_excluding_zero": calibration.loc[calibration.negative_ci_excludes_zero, "decile"].astype(int).tolist(),
        "calibration_bootstrap": {"resamples": BOOTSTRAPS, "seed": 42,
                                  "method": "IID test-row percentile bootstrap with fixed deciles",
                                  "pointwise": True, "model_training_uncertainty": False},
        "selection_note": "Sensitivity maxima and decision thresholds use test outcomes. They are exploratory and need a new experiment.",
    }
    (report / "profit_analysis.json").write_text(json.dumps(results, indent=2) + "\n")
    for language, suffix in [("en", ""), ("it", "_it")]:
        plot_profit_intervals(policies, report / f"policy_profit{suffix}.png", language)
        plot_sensitivity(grid, report / f"sensitivity_heatmap{suffix}.png", language)
        plot_break_even(line, report / f"break_even{suffix}.png", language)
        plot_calibration(calibration, report / f"uplift_calibration{suffix}.png", language)
    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    main()
