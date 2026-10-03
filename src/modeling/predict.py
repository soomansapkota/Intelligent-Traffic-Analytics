"""Load a trained delay model and score new rows with it.

Kept separate from train.py so the dashboard (or anything else that only
needs predictions) does not have to import scikit-learn's training pieces.
"""

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.base import RegressorMixin

DEFAULT_MODEL_DIR = Path("models")


def load_feature_columns(model_dir: Path = DEFAULT_MODEL_DIR) -> list[str]:
    """Load the feature column list saved alongside the trained models.

    Args:
        model_dir: Directory train.py saved into.

    Returns:
        Feature column names, in the order the models were trained on.
    """
    return json.loads((model_dir / "feature_columns.json").read_text())


def load_model(horizon: int, model_dir: Path = DEFAULT_MODEL_DIR) -> RegressorMixin:
    """Load one horizon's trained model.

    Args:
        horizon: Horizon in minutes, e.g. 5.
        model_dir: Directory train.py saved into (e.g. models/random_forest
            for a model trained with --model random_forest).

    Returns:
        The fitted regressor for that horizon.

    Raises:
        FileNotFoundError: If that horizon was never trained/saved.
    """
    path = model_dir / f"delay_model_{horizon}min.joblib"
    if not path.exists():
        raise FileNotFoundError(f"No trained model for horizon={horizon}min at {path}. Run `python -m src.modeling.train` first.")
    return joblib.load(path)


def predict_delay(
    model: RegressorMixin, rows: pd.DataFrame, feature_columns: list[str]
) -> pd.Series:
    """Predict delay (in seconds) for a batch of rows.

    Args:
        model: A model from load_model.
        rows: Rows with at least the columns in feature_columns; a missing
            feature is filled with NaN, which every model train.py builds handles natively.
        feature_columns: From load_feature_columns, so inference uses
            exactly the columns and order training used.

    Returns:
        Predicted delay in seconds, indexed like rows.
    """
    x = rows.reindex(columns=feature_columns)
    return pd.Series(model.predict(x), index=rows.index, name="predicted_delay")
