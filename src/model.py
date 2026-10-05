import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklift.models import TwoModels

from src.data import CATEGORICAL, NUMERIC, SEED, make_features


def make_classifier(kind="logistic"):
    preprocess = ColumnTransformer([
        ("numeric", StandardScaler(), NUMERIC),
        ("category", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL),
    ])
    if kind == "logistic":
        estimator = LogisticRegression(C=1.0, max_iter=1000, random_state=SEED)
    elif kind == "forest":
        estimator = RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=200,
            max_features=1.0, random_state=SEED, n_jobs=2,
        )
    else:
        raise ValueError("Unknown model")
    return Pipeline([("preprocess", preprocess), ("classifier", estimator)])


def fit_uplift(train, kind="logistic"):
    model = TwoModels(make_classifier(kind), make_classifier(kind), method="vanilla")
    model.fit(make_features(train), train.conversion, train.treatment)
    return model


def fit_response(train):
    treated = train.loc[train.treatment == 1]
    model = make_classifier()
    model.fit(make_features(treated), treated.conversion)
    return model


def top_mask(scores, share):
    scores = np.asarray(scores, dtype=float)
    if not 0 <= share <= 1 or not np.isfinite(scores).all():
        raise ValueError("Check audience share and model scores")
    mask = np.zeros(len(scores), dtype=bool)
    count = int(np.floor(len(scores) * share))
    order = np.argsort(-scores, kind="stable")
    mask[order[:count]] = True
    return mask
