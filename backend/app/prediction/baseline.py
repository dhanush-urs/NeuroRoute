#!/usr/bin/env python3
"""
Baseline models for traffic prediction.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import joblib


@dataclass
class BaselineModel:
    """
    Historical moving average baseline.
    Predicts congestion based on per-road, per-hour-of-week average.
    """
    baseline: Dict[tuple, float] = None
    global_mean: float = 0.0
    
    def fit(self, X: pd.DataFrame, y: pd.Series) -> 'BaselineModel':
        """
        Fit baseline model.
        
        Args:
            X: Feature matrix with road_id, hour, day_of_week columns
            y: Target congestion scores
        """
        # Need road_id, hour, day_of_week in X
        required_cols = ['road_id', 'hour', 'day_of_week']
        for col in required_cols:
            if col not in X.columns:
                raise ValueError(f"Required column {col} not found in X")
        
        # Create hour_of_week (0-167)
        X = X.copy()
        X['hour_of_week'] = X['day_of_week'] * 24 + X['hour']
        
        # Group by road_id and hour_of_week
        df = pd.DataFrame({
            'road_id': X['road_id'],
            'hour_of_week': X['hour_of_week'],
            'congestion': y
        })
        
        self.baseline = df.groupby(['road_id', 'hour_of_week'])['congestion'].mean().to_dict()
        
        # Global fallback
        self.global_mean = y.mean()
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict congestion scores."""
        if self.baseline is None:
            raise ValueError("Model not fitted")
        
        X = X.copy()
        X['hour_of_week'] = X['day_of_week'] * 24 + X['hour']
        
        predictions = []
        for _, row in X.iterrows():
            key = (row['road_id'], row['hour_of_week'])
            pred = self.baseline.get(key, self.global_mean)
            predictions.append(pred)
        
        return np.array(predictions)
    
    def save(self, path: str):
        """Save model to disk."""
        joblib.dump({
            'baseline': self.baseline,
            'global_mean': self.global_mean,
        }, path)
    
    @classmethod
    def load(cls, path: str) -> 'BaselineModel':
        """Load model from disk."""
        data = joblib.load(path)
        model = cls()
        model.baseline = data['baseline']
        model.global_mean = data['global_mean']
        return model


@dataclass
class SeasonalBaseline:
    """
    Seasonal baseline using multiple time granularities.
    """
    # hour_of_week -> mean
    hourly_baseline: Dict[tuple, float] = None
    # day_of_week, hour -> mean
    daily_baseline: Dict[tuple, float] = None
    # hour -> mean (global)
    hourly_global: Dict[int, float] = None
    global_mean: float = 0.0
    
    def fit(self, X: pd.DataFrame, y: pd.Series) -> 'SeasonalBaseline':
        X = X.copy()
        X['hour_of_week'] = X['day_of_week'] * 24 + X['hour']
        
        df = pd.DataFrame({
            'road_id': X['road_id'],
            'hour_of_week': X['hour_of_week'],
            'day_of_week': X['day_of_week'],
            'hour': X['hour'],
            'congestion': y
        })
        
        # Per-road, per-hour-of-week
        self.hourly_baseline = df.groupby(['road_id', 'hour_of_week'])['congestion'].mean().to_dict()
        
        # Per-road, per-day-of-week, per-hour
        self.daily_baseline = df.groupby(['road_id', 'day_of_week', 'hour'])['congestion'].mean().to_dict()
        
        # Global per-hour
        self.hourly_global = df.groupby('hour')['congestion'].mean().to_dict()
        
        self.global_mean = y.mean()
        
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        X = X.copy()
        X['hour_of_week'] = X['day_of_week'] * 24 + X['hour']
        
        predictions = []
        for _, row in X.iterrows():
            # Try per-road, per-hour-of-week
            key1 = (row['road_id'], row['hour_of_week'])
            if key1 in self.hourly_baseline:
                predictions.append(self.hourly_baseline[key1])
                continue
            
            # Try per-road, per-day, per-hour
            key2 = (row['road_id'], row['day_of_week'], row['hour'])
            if key2 in self.daily_baseline:
                predictions.append(self.daily_baseline[key2])
                continue
            
            # Try global per-hour
            if row['hour'] in self.hourly_global:
                predictions.append(self.hourly_global[row['hour']])
                continue
            
            # Global fallback
            predictions.append(self.global_mean)
        
        return np.array(predictions)
    
    def save(self, path: str):
        joblib.dump({
            'hourly_baseline': self.hourly_baseline,
            'daily_baseline': self.daily_baseline,
            'hourly_global': self.hourly_global,
            'global_mean': self.global_mean,
        }, path)
    
    @classmethod
    def load(cls, path: str) -> 'SeasonalBaseline':
        data = joblib.load(path)
        model = cls()
        model.hourly_baseline = data['hourly_baseline']
        model.daily_baseline = data['daily_baseline']
        model.hourly_global = data['hourly_global']
        model.global_mean = data['global_mean']
        return model


def evaluate_baseline(model, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, float]:
    """Evaluate baseline model."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    
    y_pred = model.predict(X_test)
    
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    
    return {
        'mae': mae,
        'rmse': rmse,
        'r2': r2,
    }


if __name__ == "__main__":
    print("Baseline models ready")