import hashlib
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parents[1]
DATA_URL = "https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz"
DATA_MD5 = "a68a81291f53a14f4e29002629803ba3"
NUMERIC = ["recency", "log_history", "mens", "womens", "newbie"]
CATEGORICAL = ["zip_code", "channel"]
FEATURES = NUMERIC + CATEGORICAL
SEED = 42


def load_data(path=None):
    path = Path(path) if path else ROOT / "data/raw/hillstrom.csv.gz"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(DATA_URL, timeout=60) as response:
            content = response.read()
        if hashlib.md5(content).hexdigest() != DATA_MD5:
            raise ValueError("Downloaded data checksum does not match")
        path.write_bytes(content)
    if hashlib.md5(path.read_bytes()).hexdigest() != DATA_MD5:
        raise ValueError("Data file changed. Check its checksum")
    data = pd.read_csv(path)
    validate_data(data)
    data.index.name = "row_id"
    return data


def validate_data(data):
    required = set(FEATURES) - {"log_history"}
    required |= {"history", "history_segment", "segment", "visit", "conversion", "spend"}
    if not required.issubset(data.columns):
        raise ValueError("Required columns are missing")
    if data.isna().any().any():
        raise ValueError("Source data contains missing values")
    if set(data.segment.unique()) != {"Mens E-Mail", "Womens E-Mail", "No E-Mail"}:
        raise ValueError("Unexpected experiment groups")
    for column in ["mens", "womens", "newbie", "visit", "conversion"]:
        if not data[column].isin([0, 1]).all():
            raise ValueError(f"{column} must contain only 0 and 1")
    if (data[["history", "spend"]] < 0).any().any():
        raise ValueError("Negative purchase amounts")
    if not data.recency.between(1, 12).all():
        raise ValueError("recency must be between 1 and 12")
    if (data.conversion > data.visit).any():
        raise ValueError("Conversion without a website visit")
    if ((data.spend > 0) != (data.conversion == 1)).any():
        raise ValueError("spend and conversion are inconsistent")


def binary_experiment(data):
    data = data.loc[data.segment != "Womens E-Mail"].copy()
    data["treatment"] = (data.segment == "Mens E-Mail").astype(int)
    return data


def make_features(data):
    features = data.copy()
    features["log_history"] = np.log1p(features.history)
    return features[FEATURES]


def split_data(data):
    strata = data.treatment.astype(str) + "_" + data.conversion.astype(str)
    train, other = train_test_split(data, test_size=0.4, stratify=strata, random_state=SEED)
    other_strata = other.treatment.astype(str) + "_" + other.conversion.astype(str)
    validation, test = train_test_split(
        other, test_size=0.5, stratify=other_strata, random_state=SEED
    )
    return train, validation, test
