#!/usr/bin/env python3
"""
Model inference service - singleton for online predictions.
"""

import os
import json
import joblib
import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path

from app.prediction.baseline import BaselineModel, SeasonalBaseline
from app.prediction.random_forest import RandomForestModel
from app.prediction.xgboost_model import XGBoostModel
from app.prediction.features import FeatureEngineer, FeatureConfig


@dataclass
class ModelMetadata:
    """Metadata about a loaded model."""
    name: str
    version: str
    algorithm: str
    metrics: Dict[str, float]
    feature_names: List[str]
    model_path: str
    is_active: bool = False


class ModelService:
    """
    Singleton service for managing ML models and inference.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.models: Dict[str, Any] = {}
        self.active_model: Optional[str] = None
        self.model_registry: Dict[str, ModelMetadata] = {}
        self.feature_engineer = FeatureEngineer()
        # Use local directory for development, /app/models for Docker
        model_dir = os.getenv("MODEL_DIR", "./models")
        self.model_dir = Path(model_dir)
        if not self.model_dir.exists() or not (self.model_dir / "model_registry.json").exists():
            candidate = Path(__file__).resolve().parent.parent.parent / "models"
            if candidate.exists() and (candidate / "model_registry.json").exists():
                self.model_dir = candidate
        self.model_dir.mkdir(parents=True, exist_ok=True)
    
    def register_model(
        self,
        name: str,
        model: Any,
        version: str,
        algorithm: str,
        metrics: Dict[str, float],
        feature_names: List[str],
        model_path: str
    ):
        """Register a trained model."""
        metadata = ModelMetadata(
            name=name,
            version=version,
            algorithm=algorithm,
            metrics=metrics,
            feature_names=feature_names,
            model_path=model_path,
            is_active=False
        )
        self.models[name] = model
        self.model_registry[name] = metadata
        
        # Save metadata
        self._save_registry()
    
    def activate_model(self, name: str):
        """Set a model as active for inference."""
        if name not in self.models:
            raise ValueError(f"Model {name} not registered")
        
        # Deactivate all
        for meta in self.model_registry.values():
            meta.is_active = False
        
        # Activate selected
        self.active_model = name
        self.model_registry[name].is_active = True
        self._save_registry()
    
    def get_active_model(self):
        """Get the currently active model."""
        if self.active_model is None:
            # Auto-activate best model if available
            if self.model_registry:
                best = max(self.model_registry.values(), key=lambda m: m.metrics.get('r2', 0))
                self.activate_model(best.name)
            else:
                raise ValueError("No models registered")
        
        return self.models[self.active_model]
    
    def predict(
        self,
        features_df: pd.DataFrame,
        model_name: str = None,
        horizon: str = 'target_congestion_15m'
    ) -> np.ndarray:
        """
        Make predictions using active or specified model.
        
        Args:
            features_df: Raw traffic data (will be processed by feature engineer)
            model_name: Specific model to use (None = active)
            horizon: Prediction horizon
            
        Returns:
            Predictions array
        """
        model_name = model_name or self.active_model
        if model_name not in self.models:
            raise ValueError(f"Model {model_name} not found")
        
        model = self.models[model_name]
        
        # Build features
        features_df = self.feature_engineer.build_features(
            features_df, 
            is_training=False
        )
        
        # Select features
        meta = self.model_registry[model_name]
        X = features_df[meta.feature_names].fillna(0)
        
        # Predict
        if hasattr(self.models[model_name], 'predict'):
            return self.models[model_name].predict(X)
        else:
            raise ValueError(f"Model {model_name} has no predict method")

    async def predict_batch(self, roads: Dict[str, Any], current_tick: int) -> None:
        """
        Generate predictions for all roads and update road objects.
        
        Args:
            roads: Dictionary of road objects
            current_tick: Current simulation tick
        """
        if not self.models:
            return
            
        # Run CPU-intensive prediction in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._predict_batch_sync, roads, current_tick)
    
    def _predict_batch_sync(self, roads: Dict[str, Any], current_tick: int) -> None:
        """Synchronous batch prediction (runs in thread pool)."""
        if not self.models:
            return
            
        # Prepare features DataFrame from roads
        features_list = []
        for road_id, road in roads.items():
            feat = {
                'road_id': road_id,
                'tick': current_tick,
                'timestamp': datetime.now(timezone.utc),  # Add timestamp for feature engineering
                'vehicle_count': getattr(road, 'vehicle_count', 0),
                'avg_speed_kmh': getattr(road, 'avg_speed', road.speed_limit_kmh),
                'congestion_score': getattr(road, 'current_congestion', 0.0),
                'congestion_level': getattr(road, 'congestion_level', 'free'),
                'capacity': getattr(road, 'capacity_vph', 900),
                'speed_limit': getattr(road, 'speed_limit_kmh', 50),
                'distance_km': getattr(road, 'distance_km', 1.0),
                'road_type': getattr(road, 'road_type', 'major'),
                'weather_condition': getattr(road, 'weather_condition', 'clear'),
                'temperature_c': getattr(road, 'temperature_c', 20.0),
                # Weather features needed for feature engineering
                'rain_intensity': getattr(road, 'rain_intensity', 0.0),
                'visibility_km': getattr(road, 'visibility_km', 20.0),
                'incident_count': 1 if getattr(road, 'incident_penalty', 0) > 0 else 0,
                'max_incident_severity': getattr(road, 'incident_penalty', 0),
                'capacity_reduction_pct': getattr(road, 'incident_penalty', 0) * 100,
            }
            features_list.append(feat)
        
        if not features_list:
            return
            
        features_df = pd.DataFrame(features_list)
        
        try:
            predictions = self.predict(features_df, horizon='target_congestion_15m')
            
            # Update road objects with predictions
            for i, (road_id, road) in enumerate(roads.items()):
                if i < len(predictions):
                    pred = max(0.0, min(1.0, float(predictions[i])))
                    road.predicted_congestion_15m = pred
                    road.predicted_congestion_5m = pred * 0.9
                    road.predicted_congestion_30m = pred * 1.1
                    road.predicted_congestion_60m = pred * 1.2
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Batch prediction failed: {e}")
    
    def load_model(
        self,
        name: str,
        path: str,
        algorithm: str = None
    ):
        """Load a model from disk."""
        if algorithm == 'baseline':
            model = BaselineModel.load(path)
        elif algorithm == 'random_forest':
            model = RandomForestModel.load(path)
        elif algorithm == 'xgboost':
            model = XGBoostModel.load(path)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        
        # Register without metrics (assume already evaluated)
        self.register_model(
            name=name,
            model=model,
            version="1.0",
            algorithm=algorithm,
            metrics={},
            feature_names=model.feature_names if hasattr(model, 'feature_names') else [],
            model_path=path
        )
        return model
    
    def _save_registry(self):
        """Save model registry to disk."""
        registry_path = self.model_dir / "model_registry.json"
        data = {
            name: {
                'name': meta.name,
                'version': meta.version,
                'algorithm': meta.algorithm,
                'metrics': meta.metrics,
                'feature_names': meta.feature_names,
                'model_path': meta.model_path,
                'is_active': meta.is_active,
            }
            for name, meta in self.model_registry.items()
        }
        with open(registry_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_registry(self):
        """Load model registry from disk."""
        registry_path = self.model_dir / "model_registry.json"
        if registry_path.exists():
            with open(registry_path) as f:
                data = json.load(f)
            
            for name, meta in data.items():
                self.model_registry[name] = ModelMetadata(**meta)
                if meta['is_active']:
                    self.active_model = name
                
                # Load model from disk
                model_path = meta['model_path']
                p = Path(model_path)
                if not p.exists():
                    candidate = self.model_dir / p.name
                    if candidate.exists():
                        p = candidate
                if p.exists():
                    model_path = str(p)
                    algorithm = meta['algorithm']
                    try:
                        if algorithm == 'baseline':
                            # Could be BaselineModel or SeasonalBaseline - try both
                            model = SeasonalBaseline.load(model_path)
                        elif algorithm == 'random_forest':
                            model = RandomForestModel.load(model_path)
                        elif algorithm == 'xgboost':
                            model = XGBoostModel.load(model_path)
                        else:
                            continue
                        self.models[name] = model
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Failed to load model {name}: {e}")
    
    def list_models(self) -> List[Dict]:
        """List all registered models."""
        return [
            {
                'name': meta.name,
                'version': meta.version,
                'algorithm': meta.algorithm,
                'metrics': meta.metrics,
                'is_active': meta.is_active,
            }
            for meta in self.model_registry.values()
        ]


# Global instance
_model_service = None


def get_model_service() -> ModelService:
    """Get the global ModelService instance."""
    global _model_service
    if _model_service is None:
        _model_service = ModelService()
        _model_service.load_registry()
    return _model_service


def set_model_service(service: ModelService):
    """Set the global ModelService instance."""
    global _model_service
    _model_service = service