import numpy as np
import pandas as pd
import pytest

from src.data import FEATURES, binary_experiment, load_data, make_features, split_data
from src.evaluation import ab_test, bootstrap_policies, policy_value
from src.model import fit_uplift, top_mask


def test_profit_subtracts_discount_from_all_treated_purchases():
    y = np.array([1, 1, 0, 0, 1, 0, 0, 0])
    treatment = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    result = policy_value(y, treatment, np.ones(8, dtype=bool),
                          population=1000, margin=30, contact_cost=0.1, discount=5)
    assert result["extra_orders"] == 250
    assert result["discount_spend"] == 2500
    assert result["profit"] == 4900


def test_discount_costs_money_even_without_incremental_orders():
    y = np.array([1, 0, 1, 0])
    treatment = np.array([1, 1, 0, 0])
    result = policy_value(y, treatment, np.ones(4, dtype=bool),
                          population=1000, margin=30, contact_cost=0, discount=5)
    assert result["extra_orders"] == 0
    assert result["profit"] == -2500


def test_empty_policy_and_missing_control():
    assert policy_value([1, 0], [1, 0], [False, False])["profit"] == 0
    with pytest.raises(ValueError, match="both experiment groups"):
        policy_value([1, 0], [1, 0], [True, False])


def test_top_mask_handles_ties_and_budget():
    scores = [0.3, 0.3, -0.1, 0.2]
    np.testing.assert_array_equal(top_mask(scores, 0.5), [True, True, False, False])
    assert not top_mask(scores, 0).any()
    assert top_mask(scores, 1).all()
    with pytest.raises(ValueError):
        top_mask(scores, 1.1)


def test_split_is_disjoint_and_features_have_no_outcomes():
    data = binary_experiment(load_data())
    train, validation, test = split_data(data)
    assert set(train.index).isdisjoint(validation.index)
    assert set(train.index).isdisjoint(test.index)
    assert set(validation.index).isdisjoint(test.index)
    assert len(train) + len(validation) + len(test) == len(data)
    assert set(make_features(data).columns) == set(FEATURES)
    assert not {"treatment", "segment", "visit", "conversion", "spend"} & set(FEATURES)
    changed = data.copy()
    changed[["visit", "conversion", "spend", "treatment"]] = 999
    pd.testing.assert_frame_equal(make_features(data), make_features(changed))


def test_ab_effect_matches_manual_difference():
    data = pd.DataFrame({"treatment": [1] * 100 + [0] * 100,
                         "conversion": [1] * 20 + [0] * 80 + [1] * 10 + [0] * 90})
    result = ab_test(data)
    assert result["effect"] == pytest.approx(0.1)
    assert result["ci_low"] < result["effect"] < result["ci_high"]


def test_uplift_model_fits_and_handles_new_category():
    data = binary_experiment(load_data())
    train, _, test = split_data(data)
    model = fit_uplift(train)
    features = make_features(test.head(20))
    features["channel"] = "new_channel"
    scores = model.predict(features)
    assert scores.shape == (20,)
    assert np.isfinite(scores).all()
    assert np.abs(scores).max() <= 1


def test_paired_bootstrap_keeps_identical_policies_equal():
    data = pd.DataFrame({"treatment": [1] * 20 + [0] * 20,
                         "conversion": [1] * 6 + [0] * 14 + [1] * 3 + [0] * 17})
    mask = np.ones(len(data), dtype=bool)
    samples = bootstrap_policies(data, {"first": mask, "second": mask}, repeats=30)
    np.testing.assert_array_equal(samples["first"], samples["second"])
    assert np.std(samples["first"]) > 0
