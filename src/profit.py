import numpy as np
import pandas as pd

from src.evaluation import BOOTSTRAPS, MARGIN, POPULATION, interval
from src.model import top_mask


PROPENSITY = 0.5


def policy_components(data, mask, population=POPULATION, margin=MARGIN,
                      propensity=PROPENSITY):
    mask = np.asarray(mask, dtype=bool)
    if len(mask) != len(data) or not len(data):
        raise ValueError("Check data and policy lengths")
    if not 0 < propensity < 1:
        raise ValueError("Propensity must be between 0 and 1")
    if not np.isfinite([population, margin]).all() or min(population, margin) < 0:
        raise ValueError("Check population and margin")
    if not data.treatment.isin([0, 1]).all() or not data.conversion.isin([0, 1]).all():
        raise ValueError("Treatment and conversion must be binary")
    if not np.isfinite(data.spend).all() or (data.spend < 0).any():
        raise ValueError("Spend must be finite and nonnegative")
    share = float(mask.mean())
    contacts = population * share
    selected = data.loc[mask]
    treated = selected.treatment.to_numpy()
    y = selected.conversion.to_numpy()
    spend = selected.spend.to_numpy()
    if not mask.any():
        return dict(share=0.0, contacts=0.0, treated_n=0, control_n=0,
                    treated_rate=0.0, control_rate=0.0, uplift=0.0,
                    extra_orders=0.0, base_profit=0.0, treated_spend=0.0)
    w1 = treated / propensity
    w0 = (1 - treated) / (1 - propensity)
    if not w1.sum() or not w0.sum():
        raise ValueError("Selected audience needs both experiment groups")
    p1 = float(np.average(y, weights=w1))
    p0 = float(np.average(y, weights=w0))
    extra_orders = contacts * (p1 - p0)
    return dict(share=share, contacts=contacts, treated_n=int(treated.sum()),
                control_n=int(len(treated) - treated.sum()),
                treated_rate=p1, control_rate=p0, uplift=p1 - p0,
                extra_orders=float(extra_orders), base_profit=float(extra_orders * margin),
                treated_spend=float(contacts * np.average(spend, weights=w1)))


def net_profit(components, contact_cost=0.15, discount=0.0):
    if not np.isfinite([contact_cost, discount]).all() or contact_cost < 0 or not 0 <= discount <= 1:
        raise ValueError("Check contact cost and discount fraction")
    return (components["base_profit"] - components["contacts"] * contact_cost
            - components["treated_spend"] * discount)


def policy_value_ipw(data, mask, population=POPULATION, margin=MARGIN,
                     contact_cost=0.15, discount=0.0, propensity=PROPENSITY):
    result = policy_components(data, mask, population, margin, propensity)
    result["contact_spend"] = result["contacts"] * contact_cost
    result["discount_spend"] = result["treated_spend"] * discount
    result["profit"] = float(net_profit(result, contact_cost, discount))
    return result


def policy_masks(scores):
    masks = {"no_mail": top_mask(scores, 0), "mail_all": top_mask(scores, 1)}
    masks.update({f"top_{k}": top_mask(scores, k / 100) for k in range(10, 101, 10)})
    return masks


def bootstrap_components(data, masks, repeats=BOOTSTRAPS, seed=42,
                         population=POPULATION, margin=MARGIN, propensity=PROPENSITY):
    rng = np.random.default_rng(seed)
    rows = []
    for sample_id in range(repeats):
        indices = rng.integers(0, len(data), len(data))
        sample = data.iloc[indices]
        for name, mask in masks.items():
            result = policy_components(sample, mask[indices], population, margin, propensity)
            rows.append({"resample": sample_id, "policy": name,
                         "base_profit": result["base_profit"],
                         "contacts": result["contacts"], "treated_spend": result["treated_spend"]})
    return pd.DataFrame(rows)


def policy_table(data, scores, samples, contact_cost=0.15, discount=0.0,
                 population=POPULATION, margin=MARGIN):
    rows = []
    for name, mask in policy_masks(scores).items():
        result = policy_value_ipw(data, mask, population, margin, contact_cost, discount)
        values = samples.loc[samples.policy == name]
        low, high = interval(net_profit(values, contact_cost, discount))
        k = 0 if name == "no_mail" else 100 if name == "mail_all" else int(name.split("_")[1])
        rows.append({"policy": name, "k": k, **result, "ci_low": low, "ci_high": high})
    return pd.DataFrame(rows)


def profit_difference(samples, first="top_30", second="mail_all", contact_cost=0.15, discount=0.0):
    values = samples.assign(profit=net_profit(samples, contact_cost, discount))
    values = values.pivot(index="resample", columns="policy", values="profit")
    return interval(values[first] - values[second])


def sensitivity_grid(components):
    rows = []
    for cost in np.arange(11) * 0.05:
        for discount in np.arange(7) * 0.05:
            profits = net_profit(components, float(cost), float(discount))
            best = components.loc[profits.idxmax()]
            all_profit = float(profits.loc[components.k == 100].iloc[0])
            rows.append({"contact_cost": round(float(cost), 2),
                         "discount": round(float(discount), 2),
                         "optimal_k": int(best.k), "profit": float(profits.max()),
                         "mail_all_profit": all_profit, "gain_vs_mail_all": float(profits.max() - all_profit)})
    return pd.DataFrame(rows)


def break_even_line(components, discounts=None):
    discounts = np.linspace(0, 0.3, 301) if discounts is None else np.asarray(discounts)
    all_policy = components.loc[components.k == 100].iloc[0]
    others = components.loc[components.k < 100].copy()
    rows = []
    for discount in discounts:
        cost_limits = ((all_policy.base_profit - others.base_profit
                        - discount * (all_policy.treated_spend - others.treated_spend))
                       / (all_policy.contacts - others.contacts))
        binding = others.loc[cost_limits.idxmin()]
        limit = float(cost_limits.min())
        rows.append({"discount": float(discount), "max_contact_cost_for_mail_all": limit,
                     "binding_k": int(binding.k), "mail_all_possible": limit >= 0})
    return pd.DataFrame(rows)


def discount_limit(components, contact_cost):
    all_policy = components.loc[components.k == 100].iloc[0]
    lower, upper = 0.0, 1.0
    for _, other in components.loc[components.k < 100].iterrows():
        gain_at_zero = net_profit(all_policy, contact_cost, 0) - net_profit(other, contact_cost, 0)
        extra_coupon_spend = all_policy.treated_spend - other.treated_spend
        if extra_coupon_spend > 0:
            upper = min(upper, gain_at_zero / extra_coupon_spend)
        elif extra_coupon_spend < 0:
            lower = max(lower, gain_at_zero / extra_coupon_spend)
        elif gain_at_zero < 0:
            return None
    if upper < lower or upper < 0:
        return None
    return float(upper)


def uplift_calibration(data, scores, repeats=BOOTSTRAPS, seed=42):
    scores = np.asarray(scores)
    order = np.argsort(-scores, kind="stable")
    cuts = [int(np.floor(len(data) * k / 10)) for k in range(11)]
    deciles = np.empty(len(data), dtype=int)
    rows = []
    for decile in range(10):
        mask = np.zeros(len(data), dtype=bool)
        mask[order[cuts[decile]:cuts[decile + 1]]] = True
        deciles[mask] = decile
        observed = policy_components(data, mask)
        rows.append({"decile": decile + 1, "customers": int(mask.sum()),
                     "treated_n": observed["treated_n"], "control_n": observed["control_n"],
                     "treated_buyers": int(data.loc[mask & (data.treatment == 1), "conversion"].sum()),
                     "control_buyers": int(data.loc[mask & (data.treatment == 0), "conversion"].sum()),
                     "predicted_uplift": float(scores[mask].mean()),
                     "observed_uplift": observed["uplift"],
                     "negative_observed": observed["uplift"] < 0})
    w1 = data.treatment.to_numpy() / PROPENSITY
    w0 = (1 - data.treatment.to_numpy()) / (1 - PROPENSITY)
    y = data.conversion.to_numpy()
    rng = np.random.default_rng(seed)
    samples = np.empty((repeats, 10))
    for sample_id in range(repeats):
        indices = rng.integers(0, len(data), len(data))
        bins = deciles[indices]
        n1 = np.bincount(bins, weights=w1[indices], minlength=10)
        n0 = np.bincount(bins, weights=w0[indices], minlength=10)
        if (n1 == 0).any() or (n0 == 0).any():
            raise ValueError("A bootstrap decile needs both experiment groups")
        p1 = np.bincount(bins, weights=w1[indices] * y[indices], minlength=10) / n1
        p0 = np.bincount(bins, weights=w0[indices] * y[indices], minlength=10) / n0
        samples[sample_id] = p1 - p0
    table = pd.DataFrame(rows)
    table["observed_ci_low"], table["observed_ci_high"] = np.quantile(samples, [0.025, 0.975], axis=0)
    table["negative_ci_excludes_zero"] = table.negative_observed & (table.observed_ci_high < 0)
    return table
