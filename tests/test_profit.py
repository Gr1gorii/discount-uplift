import numpy as np
import pandas as pd
import pytest

from src.data import ROOT
from src.evaluation import policy_value
from src.model import top_mask
from src.profit import (bootstrap_components, break_even_line, net_profit, policy_masks,
                        policy_value_ipw, profit_difference, sensitivity_grid, uplift_calibration)


@pytest.fixture
def test_data():
    return pd.read_csv(ROOT / "data/processed/profit_test.csv")


def test_top_100_equals_mail_all_in_estimate_and_bootstrap(test_data):
    masks = policy_masks(test_data.logistic)
    assert policy_value_ipw(test_data, masks["top_100"]) == policy_value_ipw(test_data, masks["mail_all"])
    samples = pd.read_csv(ROOT / "reports/bootstrap_components.csv")
    values = samples.pivot(index="resample", columns="policy", values="base_profit")
    np.testing.assert_array_equal(values.top_100, values.mail_all)
    assert profit_difference(samples, "top_100", "mail_all") == [0, 0]


def test_top_0_equals_no_mail(test_data):
    result = policy_value_ipw(test_data, top_mask(test_data.logistic, 0), contact_cost=0.5, discount=0.3)
    assert result["profit"] == 0
    assert result["contacts"] == 0
    samples = pd.read_csv(ROOT / "reports/bootstrap_components.csv")
    assert (net_profit(samples.loc[samples.policy == "no_mail"], 0.5, 0.3) == 0).all()


def test_zero_discount_and_cost_preserve_current_result(test_data):
    for k in range(0, 101, 10):
        mask = top_mask(test_data.logistic, k / 100)
        previous = policy_value(test_data.conversion, test_data.treatment, mask, contact_cost=0, discount=0)
        current = policy_value_ipw(test_data, mask, contact_cost=0, discount=0)
        assert current["profit"] == pytest.approx(previous["profit"])
    top_30 = policy_value_ipw(test_data, top_mask(test_data.logistic, 0.3))
    assert top_30["profit"] == pytest.approx(406.1874294400996)


def test_percentage_coupon_is_charged_on_all_treated_spend():
    data = pd.DataFrame({"treatment": [1, 1, 0, 0], "conversion": [1, 0, 1, 0],
                         "spend": [100, 0, 50, 0]})
    result = policy_value_ipw(data, np.ones(4, dtype=bool), population=1000,
                              contact_cost=0.1, discount=0.2)
    assert result["extra_orders"] == 0
    assert result["discount_spend"] == 10000
    assert result["profit"] == -10100
    with pytest.raises(ValueError, match="discount"):
        policy_value_ipw(data, np.ones(4, dtype=bool), discount=20)


def test_bootstrap_resamples_rows_and_keeps_policies_paired():
    data = pd.DataFrame({"treatment": [1] * 20 + [0] * 20,
                         "conversion": [1] * 6 + [0] * 14 + [1] * 3 + [0] * 17,
                         "spend": [100] * 6 + [0] * 14 + [50] * 3 + [0] * 17})
    mask = np.ones(len(data), dtype=bool)
    samples = bootstrap_components(data, {"first": mask, "second": mask}, repeats=30)
    values = samples.pivot(index="resample", columns="policy", values="base_profit")
    np.testing.assert_array_equal(values["first"], values["second"])
    assert values["first"].std() > 0
    draw = np.random.default_rng(42).integers(0, len(data), len(data))
    first = policy_value_ipw(data.iloc[draw], mask, contact_cost=0, discount=0)
    assert values["first"].iloc[0] == pytest.approx(first["profit"])


def test_sensitivity_grid_and_break_even_agree():
    components = pd.read_csv(ROOT / "reports/policy_profit.csv")
    components = components.loc[components.policy != "mail_all"]
    grid = sensitivity_grid(components)
    assert len(grid) == 77
    assert (grid.gain_vs_mail_all >= -1e-9).all()
    assert ((grid.optimal_k == 0) == (grid.profit == 0)).all()
    line = break_even_line(components, [0, 0.05, 0.1])
    for row in line.itertuples():
        for offset, mail_all_best in [(-0.001, True), (0.001, False)]:
            profits = net_profit(components, row.max_contact_cost_for_mail_all + offset, row.discount)
            all_profit = profits.loc[components.k == 100].iloc[0]
            assert bool(all_profit >= profits.max() - 1e-8) == mail_all_best


def test_calibration_covers_test_once_and_flags_negative_deciles(test_data):
    table = uplift_calibration(test_data, test_data.logistic)
    assert len(table) == 10
    assert table.customers.sum() == len(test_data)
    assert table.treated_buyers.sum() + table.control_buyers.sum() == 78
    assert table.predicted_uplift.is_monotonic_decreasing
    assert table.loc[table.negative_observed, "decile"].tolist() == [5, 6]
    np.testing.assert_array_equal(table.negative_observed, table.observed_uplift < 0)
    assert np.isfinite(table[["observed_ci_low", "observed_ci_high"]]).all().all()
    assert (table.observed_ci_low <= table.observed_ci_high).all()
    middle = table.loc[table.decile.isin([5, 6])]
    assert (middle.observed_ci_low < 0).all()
    assert (middle.observed_ci_high > 0).all()
    assert not table.negative_ci_excludes_zero.any()


def test_calibration_intervals_match_bootstrapped_arm_means(test_data):
    repeats, seed = 40, 23
    table = uplift_calibration(test_data, test_data.logistic, repeats=repeats, seed=seed)
    order = np.argsort(-test_data.logistic.to_numpy(), kind="stable")
    fixed = np.zeros(len(test_data), dtype=bool)
    fixed[order[len(test_data) * 4 // 10:len(test_data) * 5 // 10]] = True
    treatment = test_data.treatment.to_numpy()
    conversion = test_data.conversion.to_numpy()
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(repeats):
        draw = rng.integers(0, len(test_data), len(test_data))
        treated = conversion[draw][fixed[draw] & (treatment[draw] == 1)]
        control = conversion[draw][fixed[draw] & (treatment[draw] == 0)]
        estimates.append(treated.mean() - control.mean())
    expected = np.quantile(estimates, [0.025, 0.975])
    actual = table.loc[table.decile == 5, ["observed_ci_low", "observed_ci_high"]].iloc[0]
    np.testing.assert_allclose(actual.to_numpy(), expected)
