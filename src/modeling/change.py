"""Model wrappers saved inside the trained models.

PredictChange predicts the change in delay rather than the delay itself;
AsFloat feeds XGBoost the plain float input it requires.

Kept in their own module so saved models always point at
src.modeling.change. If they lived in train.py, running
`python -m src.modeling.train` would save them as __main__.PredictChange,
which predict.py and the API could not load back.
"""

import pandas as pd
from sklearn.base import RegressorMixin


class PredictChange:
    """Train a regressor on the change in delay, then add it back onto the current delay.

    Delay rarely moves over a few minutes, so a model that only learns the
    correction starts from the persistence guess instead of having to rebuild
    it out of tree steps. See notebooks/model_comparison.ipynb for the comparison.

    Args:
        model: Any regressor with fit/predict. X must include arrival_delay.
    """

    def __init__(self, model: RegressorMixin):
        self.model = model

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "PredictChange":
        self.model.fit(X, y - X["arrival_delay"])
        return self

    def predict(self, X: pd.DataFrame):
        return X["arrival_delay"].to_numpy() + self.model.predict(X)


class AsFloat:
    """Cast the feature frame to float before handing it to the wrapped model.

    XGBoost rejects the pandas nullable and object dtypes that scikit-learn
    accepts as they come out of model_dataset; NaN survives the cast, and
    XGBoost handles it natively.

    Args:
        model: Any regressor with fit/predict.
    """

    def __init__(self, model: RegressorMixin):
        self.model = model

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "AsFloat":
        self.model.fit(X.astype(float), y)
        return self

    def predict(self, X: pd.DataFrame):
        return self.model.predict(X.astype(float))
