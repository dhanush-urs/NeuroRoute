#!/usr/bin/env python3
"""
XGBoost model for traffic prediction.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import joblib
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


class XGBoostModel:
    """
    XGBoost regressor for traffic congestion prediction.
    """
    
    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 8,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        early_stopping_rounds: int = 20,
        eval_metric: str = 'mae',
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        self.params = {
            'n_estimators': n_estimators,
            'max_depth': max_depth,
            'learning_rate': learning_rate,
            'subsample': subsample,
            'colsample_bytree': colsample_bytree,
            'early_stopping_rounds': early_stopping_rounds,
            'eval_metric': eval_metric,
            'random_state': random_state,
            'n_jobs': n_jobs,
        }
        self.model = None
        self.feature_names = None
        self.best_iteration = 0
    
    def fit(
        self, 
        X: pd.DataFrame, 
        y: pd.Series,
        X_val: pd.DataFrame = None,
        y_val: pd.Series = None
    ) -> 'XGBoostModel':
        """Train the XGBoost model."""
        self.feature_names = X.columns.tolist()
        
        self.model = XGBRegressor(**self.params)
        
        if X_val is not None and y_val is not None:
            self.model.fit(
                X, y,
                eval_set=[(X_val, y_val)],
                verbose=False
            )
            self.best_iteration = self.model.best_iteration
        else:
            self.model.fit(X, y)
        
        return self
    
    def predict(self, X: pd.DataFrame, iteration: int = None) -> np.ndarray:
        """Predict congestion scores."""
        if self.model is None:
            raise ValueError("Model not fitted")
        
        X = X[self.feature_names]
        
        if iteration is not None:
            return self.model.predict(X, iteration_range=(0, iteration + 1))
        elif self.best_iteration > 0:
            return self.model.predict(X, iteration_range=(0, self.best_iteration + 1))
        else:
            return self.model.predict(X)
    
    def feature_importance(self, importance_type: str = 'gain') -> pd.DataFrame:
        """Get feature importance."""
        if self.model is None:
            raise ValueError("Model not fitted")
        
        importance_df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        return importance_df
    
    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
        """Evaluate model on test data."""
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        
        y_pred = self.predict(X)
        
        mae = mean_absolute_error(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        r2 = r2_score(y, y_pred)
        
        return {
            'mae': mae,
            'rmse': rmse,
            'r2': r2,
        }
    
    def save(self, path: str):
        """Save model to disk."""
        joblib.dump({
            'model': self.model,
            'params': self.params,
            'feature_names': self.feature_names,
            'best_iteration': self.best_iteration,
        }, path)
    
    @classmethod
    def load(cls, path: str) -> 'XGBoostModel':
        data = joblib.load(path)
        model = cls(**data['params'])
        model.model = data['model']
        model.feature_names = data['feature_names']
        model.best_iteration = data.get('best_iteration', 0)
        return model


def train_xgboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    **kwargs
) -> 'XGBoostModel':
    """Train XGBoost with validation."""
    model = XGBoostModel(**kwargs)
    model.fit(X_train, y_train, X_val, y_val)
    
    # Evaluate on validation
    metrics = model.evaluate(X_val, y_val)
    print(f"Validation - MAE: {metrics['mae']:.4f}, RMSE: {metrics['rmse']:.4f}, R2: {metrics['r2']:.4f}")
    
    return model


if __name__ == "__main__":
    print("XGBoost model ready")