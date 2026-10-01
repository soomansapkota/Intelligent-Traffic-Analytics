import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error

def evaluate_rolling_origin(model, X: pd.DataFrame, y: pd.Series, n_splits: int = 5):
    """Evaluates model using rolling origin time-series split."""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    
    scores = {"mae": [], "rmse": [], "mape": []}
    
    for train_index, test_index in tscv.split(X):
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]
        
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        
        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        # Protect against division by zero in MAPE
        mape = np.mean(np.abs((y_test - preds) / np.clip(np.abs(y_test), 1, None))) * 100
        
        scores["mae"].append(mae)
        scores["rmse"].append(rmse)
        scores["mape"].append(mape)
        
    return {k: np.mean(v) for k, v in scores.items()}