"""Model wrapper that predicts the change in delay rather than the delay itself.

Kept in its own module so saved models always point at
src.modeling.change.PredictChange. If it lived in train.py, running
`python -m src.modeling.train` would save it as __main__.PredictChange,
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
