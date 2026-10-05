import numpy as np
import pandas as pd
from scipy.stats import chisquare, norm
from sklift.metrics import qini_auc_score, qini_curve

from src.model import top_mask


MARGIN = 30.0
CONTACT_COST = 0.15
DISCOUNT = 0.0
POPULATION = 10000
BOOTSTRAPS = 1000


def ab_test(data):
    treated = data.loc[data.treatment == 1, "conversion"]
    control = data.loc[data.treatment == 0, "conversion"]
    effect = treated.mean() - control.mean()
    se = np.sqrt(treated.mean() * (1 - treated.mean()) / len(treated)
                 + control.mean() * (1 - control.mean()) / len(control))
    z = norm.ppf(0.975)
    srm = chisquare([len(treated), len(control)]).pvalue
    return {
        "treated_n": len(treated), "control_n": len(control),
        "treated_orders": int(treated.sum()), "control_orders": int(control.sum()),
        "treated_rate": float(treated.mean()), "control_rate": float(control.mean()),
        "effect": float(effect), "ci_low": float(effect - z * se),
        "ci_high": float(effect + z * se), "p_value": float(2 * norm.sf(abs(effect / se))),
        "srm_p_value": float(srm),
    }


def balance_table(data):
    numeric = ["recency", "history", "mens", "womens", "newbie"]
    features = pd.concat([data[numeric], pd.get_dummies(data[["zip_code", "channel"]], dtype=int)], axis=1)
    treated = features.loc[data.treatment == 1]
    control = features.loc[data.treatment == 0]
    sd = np.sqrt((treated.var() + control.var()) / 2)
    return pd.DataFrame({
        "feature": features.columns,
        "treated_mean": treated.mean().values,
        "control_mean": control.mean().values,
        "smd": ((treated.mean() - control.mean()) / sd).values,
    })


def policy_value(y, treatment, mask, population=POPULATION, margin=MARGIN,
                 contact_cost=CONTACT_COST, discount=DISCOUNT, share=None):
    y = np.asarray(y)
    treatment = np.asarray(treatment)
    mask = np.asarray(mask, dtype=bool)
    if len(y) != len(treatment) or len(y) != len(mask):
        raise ValueError("Array lengths do not match")
    if not np.isin(y, [0, 1]).all() or not np.isin(treatment, [0, 1]).all():
        raise ValueError("Outcome and treatment must be binary")
    if min(population, margin, contact_cost, discount) < 0:
        raise ValueError("Economic parameters cannot be negative")
    share = float(mask.mean()) if share is None else float(share)
    if not 0 <= share <= 1:
        raise ValueError("Audience share must be between 0 and 1")
    if not mask.any():
        return dict(share=0.0, contacts=0.0, treated_n=0, control_n=0,
                    treated_rate=0.0, control_rate=0.0, uplift=0.0,
                    extra_orders=0.0, treated_orders=0.0, contact_spend=0.0,
                    discount_spend=0.0, profit=0.0)
    selected_treated = y[mask & (treatment == 1)]
    selected_control = y[mask & (treatment == 0)]
    if not len(selected_treated) or not len(selected_control):
        raise ValueError("Selected audience needs both experiment groups")
    p1, p0 = selected_treated.mean(), selected_control.mean()
    contacts = population * share
    extra_orders = contacts * (p1 - p0)
    treated_orders = contacts * p1
    contact_spend = contacts * contact_cost
    discount_spend = treated_orders * discount
    return {
        "share": share, "contacts": contacts,
        "treated_n": len(selected_treated), "control_n": len(selected_control),
        "treated_rate": float(p1), "control_rate": float(p0), "uplift": float(p1 - p0),
        "extra_orders": float(extra_orders), "treated_orders": float(treated_orders),
        "contact_spend": float(contact_spend), "discount_spend": float(discount_spend),
        "profit": float(extra_orders * margin - contact_spend - discount_spend),
    }


def profit_curve(data, scores, **economics):
    rows = []
    for share in np.arange(0, 1.01, 0.1):
        mask = top_mask(scores, round(float(share), 1))
        result = policy_value(data.conversion, data.treatment, mask, **economics)
        result["budget"] = round(float(share), 1)
        rows.append(result)
    return pd.DataFrame(rows)


def model_metrics(data, scores):
    mask = top_mask(scores, 0.3)
    policy = policy_value(data.conversion, data.treatment, mask)
    return {"qini": float(qini_auc_score(data.conversion, scores, data.treatment)),
            "uplift_at_30": policy["uplift"]}


def curve_data(data, scores):
    count, gain = qini_curve(data.conversion, scores, data.treatment)
    return pd.DataFrame({"share": count / len(data), "gain": gain})


def bootstrap_policies(data, masks, population=POPULATION, margin=MARGIN,
                       contact_cost=CONTACT_COST, discount=DISCOUNT,
                       repeats=BOOTSTRAPS, seed=42):
    y = data.conversion.to_numpy()
    treatment = data.treatment.to_numpy()
    treated_idx = np.flatnonzero(treatment == 1)
    control_idx = np.flatnonzero(treatment == 0)
    rng = np.random.default_rng(seed)
    samples = {name: [] for name in masks}
    for _ in range(repeats):
        indices = np.concatenate([
            rng.choice(treated_idx, len(treated_idx), replace=True),
            rng.choice(control_idx, len(control_idx), replace=True),
        ])
        for name, mask in masks.items():
            sample = policy_value(
                y[indices], treatment[indices], mask[indices], population=population,
                margin=margin, contact_cost=contact_cost, discount=discount,
                share=float(mask.mean()),
            )
            samples[name].append(sample["profit"])
    return {name: np.asarray(values) for name, values in samples.items()}


def interval(values):
    return [float(value) for value in np.quantile(values, [0.025, 0.975])]
