#!/usr/bin/env python3
"""
Random Forest model for traffic prediction.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


class RandomForestModel:
    """
    Random Forest regressor for traffic congestion prediction.
    """
    
    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 15,
        min_samples_split: int = 10,
        min_samples_leaf: int = 5,
        max_features: str = 'sqrt',
        random_state: int = 42,
        n_jobs: int = -1,
    ):
        self.params = {
            'n_estimators': n_estimators,
            'max_depth': max_depth,
            'min_samples_split': min_samples_split,
            'min_samples_leaf': min_samples_leaf,
            'max_features': max_features,
            'random_state': random_state,
            'n_jobs': n_jobs,
        }
        self.model = None
        self.feature_names = None
    
    def fit(self, X: pd.DataFrame, y: pd.Series) -> 'RandomForestModel':
        """Train the Random Forest model."""
        self.feature_names = X.columns.tolist()
        
        self.model = RandomForestRegressor(**self.params)
        self.model.fit(X, y)
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict congestion scores."""
        if self.model is None:
            raise ValueError("Model not fitted")
        
        # Ensure same feature order
        X = X[self.feature_names]
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict with uncertainty (using tree variance)."""
        if self.model is None:
            raise ValueError("Model not fitted")
        
        X = X[self.feature_names]
        predictions = np.array([tree.predict(X) for tree in self.model.estimators_])
        mean_pred = predictions.mean(axis=0)
        std_pred = predictions.std(axis=0)
        return np.column_stack([mean_pred, std_pred])
    
    def feature_importance(self) -> pd.DataFrame:
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
        }, path)
    
    @classmethod
    def load(cls, path: str) -> 'RandomForestModel':
        data = joblib.load(path)
        model = cls(**data['params'])
        model.model = data['model']
        model.feature_names = data['feature_names']
        return model


def train_random_forest(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    **kwargs
) -> 'RandomForestModel':
    """Train Random Forest with validation."""
    model = RandomForestModel(**kwargs)
    model.fit(X_train, y_train)
    
    # Evaluate on validation
    metrics = model.evaluate(X_val, y_val)
    print(f"Validation - MAE: {metrics['mae']:.4f}, RMSE: {metrics['rmse']:.4f}, R2: {metrics['r2']:.4f}")
    
    return model


if __name__ == "__main__":
    print("Random Forest model ready")