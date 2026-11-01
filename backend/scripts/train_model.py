#!/usr/bin/env python3
"""
Training pipeline for traffic prediction models.
"""

import os
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.prediction.baseline import BaselineModel, SeasonalBaseline, evaluate_baseline
from app.prediction.random_forest import RandomForestModel, train_random_forest
from app.prediction.xgboost_model import XGBoostModel, train_xgboost
from app.prediction.features import FeatureEngineer, FeatureConfig, prepare_training_data
from app.prediction.inference import ModelService, get_model_service
from scripts.generate_dataset import DatasetGenerator


def load_dataset(data_path: str) -> pd.DataFrame:
    """Load dataset from parquet file."""
    return pd.read_parquet(data_path)


def load_road_metadata(session_factory) -> pd.DataFrame:
    """Load road metadata from database."""
    import asyncio
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.core.config import get_settings
    from app.models.road import Road
    
    async def _load():
        settings = get_settings()
        engine = create_async_engine(settings.database_url)
        async with engine.begin() as conn:
            from app.models import Base
            await conn.run_sync(Base.metadata.create_all)
        
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy.orm import sessionmaker
        
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(select(Road))
            roads = result.scalars().all()
            return pd.DataFrame([{
                'id': str(r.id),
                'distance_km': r.distance_km,
                'speed_limit': r.speed_limit_kmh,
                'capacity': r.capacity_vph,
                'road_type': r.road_type,
                'num_lanes': r.num_lanes,
            } for r in roads])
    
    return asyncio.run(_load())


def main():
    parser = argparse.ArgumentParser(description="Train traffic prediction models")
    parser.add_argument("--data", type=str, default="traffic_dataset.parquet", help="Dataset path")
    parser.add_argument("--models", nargs="+", default=["baseline", "rf", "xgb"], 
                       help="Models to train: baseline, rf, xgb")
    parser.add_argument("--output-dir", type=str, default="/app/models", help="Output directory")
    parser.add_argument("--target", type=str, default="target_congestion_15m", 
                       help="Target horizon: target_congestion_5m, 15m, 30m, 60m")
    parser.add_argument("--register", action="store_true", help="Register trained models in ModelService")
    parser.add_argument("--dev", action="store_true", help="Use dev mode (smaller dataset)")
    
    args = parser.parse_args()
    
    # Load dataset
    print(f"Loading dataset from {args.data}...")
    df = load_dataset(args.data)
    print(f"Dataset shape: {df.shape}")
    
    # Load road metadata
    print("Loading road metadata...")
    road_metadata = load_road_metadata(None)
    print(f"Loaded {len(road_metadata)} roads")
    
    # Prepare features
    print("Building features...")
    feature_config = FeatureConfig(
        historical_lags=[60, 180, 1440],
        rolling_windows=[60, 180]
    )
    
    X, y, feature_cols = prepare_training_data(
        df, 
        road_metadata=None,  # Skip for now, use placeholder
        target_horizon=args.target,
        feature_config=FeatureConfig()
    )
    
    print(f"Feature matrix: {X.shape}")
    print(f"Target: {args.target}")
    
    # Split chronologically (no random shuffle!)
    n = len(X)
    train_end = int(n * 0.6)
    val_end = int(n * 0.8)
    
    X_train, y_train = X.iloc[:train_end], y.iloc[:train_end]
    X_val, y_val = X.iloc[train_end:val_end], y.iloc[train_end:val_end]
    X_test, y_test = X.iloc[val_end:], y.iloc[val_end:]
    
    print(f"Train: {len(X_train)}, Val: {len(X_val)}, Test: {len(X_test)}")
    
    # Initialize model service
    model_service = ModelService()
    
    results = {}
    
    # Train baseline
    if "baseline" in args.models:
        print("\n=== Training Baseline ===")
        baseline = SeasonalBaseline()
        baseline.fit(X_train, y_train)
        metrics = evaluate_baseline(baseline, X_test, y_test)
        print(f"Test - MAE: {metrics['mae']:.4f}, RMSE: {metrics['rmse']:.4f}, R2: {metrics['r2']:.4f}")
        results['baseline'] = metrics
        
        if args.register:
            model_service.register_model(
                name="seasonal_baseline",
                model=baseline,
                version="1.0",
                algorithm="baseline",
                metrics=metrics,
                feature_names=[],
                model_path="/app/models/baseline.joblib"
            )
            baseline.save("/app/models/baseline.joblib")
    
    # Train Random Forest
    if "rf" in args.models:
        print("\n=== Training Random Forest ===")
        rf_model = train_random_forest(
            X_train, y_train, X_val, y_val,
            n_estimators=200,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
        )
        metrics = rf_model.evaluate(X_test, y_test)
        print(f"Test - MAE: {metrics['mae']:.4f}, RMSE: {metrics['rmse']:.4f}, R2: {metrics['r2']:.4f}")
        results['random_forest'] = metrics
        
        if args.register:
            model_service.register_model(
                name="random_forest",
                model=rf_model,
                version="1.0",
                algorithm="random_forest",
                metrics=metrics,
                feature_names=rf_model.feature_names,
                model_path="/app/models/random_forest.joblib"
            )
            rf_model.save("/app/models/random_forest.joblib")
    
    # Train XGBoost
    if "xgb" in args.models:
        print("\n=== Training XGBoost ===")
        xgb_model = train_xgboost(
            X_train, y_train, X_val, y_val,
            n_estimators=300,
            max_depth=8,
            learning_rate=0.05,
        )
        metrics = xgb_model.evaluate(X_test, y_test)
        print(f"Test - MAE: {metrics['mae']:.4f}, RMSE: {metrics['rmse']:.4f}, R2: {metrics['r2']:.4f}")
        results['xgboost'] = metrics
        
        if args.register:
            model_service.register_model(
                name="xgboost",
                model=xgb_model,
                version="1.0",
                algorithm="xgboost",
                metrics=metrics,
                feature_names=xgb_model.feature_names,
                model_path="/app/models/xgboost.joblib"
            )
            xgb_model.save("/app/models/xgboost.joblib")
    
    # Print summary
    print("\n=== Training Summary ===")
    for name, metrics in results.items():
        print(f"{name}: MAE={metrics['mae']:.4f}, RMSE={metrics['rmse']:.4f}, R2={metrics['r2']:.4f}")
    
    # Activate best model
    if args.register and results:
        best_model = max(results.items(), key=lambda x: x[1]['r2'])[0]
        model_service.activate_model(best_model)
        print(f"\nActivated best model: {best_model}")


if __name__ == "__main__":
    main()