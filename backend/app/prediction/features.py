#!/usr/bin/env python3
"""
Feature engineering for traffic prediction.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class FeatureConfig:
    """Configuration for feature engineering."""
    # Temporal features
    use_temporal: bool = True
    
    # Road static features
    use_road_static: bool = True
    
    # Traffic state features
    use_traffic_state: bool = True
    
    # Historical features
    use_historical: bool = True
    historical_lags: List[int] = None  # minutes
    rolling_windows: List[int] = None  # minutes
    
    # Spatial features
    use_spatial: bool = True
    
    # Weather features
    use_weather: bool = True
    
    # Incident features
    use_incidents: bool = True
    
    # Graph for spatial features
    graph: Optional[Any] = None
    
    def __post_init__(self):
        if self.historical_lags is None:
            self.historical_lags = [60, 180, 1440]  # 1h, 3h, 24h
        if self.rolling_windows is None:
            self.rolling_windows = [60, 180]  # 1h, 3h


class FeatureEngineer:
    """Builds features for traffic prediction from raw traffic data."""
    
    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
    
    def build_features(
        self,
        df: pd.DataFrame,
        road_metadata: Optional[pd.DataFrame] = None,
        is_training: bool = True
    ) -> pd.DataFrame:
        """
        Build feature matrix from raw traffic data.
        
        Args:
            df: Raw traffic data with columns like timestamp, road_id, vehicle_count, etc.
            road_metadata: Optional DataFrame with road static info (distance, speed_limit, capacity, road_type)
            is_training: Whether this is for training (includes targets) or inference
            
        Returns:
            DataFrame with features (and targets if is_training)
        """
        df = df.copy()
        df = df.sort_values(['road_id', 'timestamp']).reset_index(drop=True)
        
        # Ensure timestamp is datetime
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        features_list = []
        
        for road_id, group in df.groupby('road_id'):
            group = group.copy().sort_values('timestamp').reset_index(drop=True)
            
            feat = self._build_road_features(group, road_id, road_metadata)
            features_list.append(feat)
        
        result = pd.concat(features_list, ignore_index=True)
        
        if is_training:
            # Ensure targets are present
            target_cols = [c for c in result.columns if c.startswith('target_congestion_')]
            if not target_cols:
                raise ValueError("No target columns found for training")
        
        return result
    
    def _build_road_features(
        self,
        group: pd.DataFrame,
        road_id: str,
        road_metadata: Optional[pd.DataFrame]
    ) -> pd.DataFrame:
        """Build features for a single road."""
        group = group.copy()
        
        # 1. Temporal features
        if self.config.use_temporal:
            group = self._add_temporal_features(group)
        
        # 2. Road static features
        if self.config.use_road_static and road_metadata is not None:
            group = self._add_road_static_features(group, road_id, road_metadata)
        
        # 3. Traffic state features
        if self.config.use_traffic_state:
            group = self._add_traffic_state_features(group)
        
        # 4. Historical features
        if self.config.use_historical:
            group = self._add_historical_features(group)
        
        # 4. Spatial features
        if self.config.use_spatial:
            group = self._add_spatial_features(group, road_id)
        
        # 5. Weather features
        if self.config.use_weather:
            group = self._add_weather_features(group)
        
        # 6. Incident features
        if self.config.use_incidents:
            group = self._add_incident_features(group)
        
        # 7. Encode categorical features (factorize object/string columns)
        group = self._encode_categorical_features(group)
        
        # 8. Fill NaN for spatial features (missing neighbor data)
        group = self._fill_spatial_nan(group)
        
        return group
    
    def _fill_spatial_nan(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill NaN values for spatial features with 0 (no neighbor data available)."""
        df = df.copy()
        spatial_cols = ['upstream_congestion_avg', 'downstream_congestion_avg', 'parallel_road_congestion_avg']
        for col in spatial_cols:
            if col in df.columns:
                df[col] = df[col].fillna(0)
        return df
    
    def _encode_categorical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Encode categorical features to numeric (factorize object/string columns)."""
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == 'object' or df[col].dtype == 'string':
                df[col] = pd.factorize(df[col])[0]
        return df
    
    def _add_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add temporal features."""
        df = df.copy()
        
        if 'timestamp' in df.columns:
            df['hour'] = df['timestamp'].dt.hour
            df['day_of_week'] = df['timestamp'].dt.dayofweek
            df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
            df['is_rush_hour'] = ((df['hour'] >= 7) & (df['hour'] <= 9) | 
                                   (df['hour'] >= 16) & (df['hour'] <= 19)).astype(int)
            df['minutes_since_midnight'] = df['timestamp'].dt.hour * 60 + df['timestamp'].dt.minute
            
            # Cyclical encoding for hour and day of week
            df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
            df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
            df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
            df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        
        return df
    
    def _add_road_static_features(self, df: pd.DataFrame, road_id: str, road_metadata: pd.DataFrame) -> pd.DataFrame:
        """Add static road features."""
        df = df.copy()
        
        road_info = road_metadata[road_metadata['id'] == road_id]
        if len(road_info) > 0:
            road = road_info.iloc[0]
            df['distance_km'] = road.get('distance_km', 1.0)
            df['speed_limit'] = road.get('speed_limit', 50)
            df['capacity'] = road.get('capacity', 900)
            df['num_lanes'] = road.get('num_lanes', 2)
            
            # One-hot encode road type
            road_type = road.get('road_type', 'major')
            for rt in ['highway', 'major', 'minor', 'local', 'highway_bottleneck']:
                df[f'road_type_{rt}'] = (road_type == rt).astype(int)
        
        return df
    
    def _add_traffic_state_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add current traffic state features."""
        df = df.copy()
        
        # These should already be in the data
        # vehicle_count, avg_speed_kmh, density, occupancy_pct, congestion_score
        
        # Compute density (vehicles per km)
        if 'vehicle_count' in df.columns and 'distance_km' in df.columns:
            df['density'] = df['vehicle_count'] / df['distance_km'].replace(0, np.nan)
            df['density'] = df['density'].fillna(0)
        
        # Compute occupancy percentage
        if 'vehicle_count' in df.columns and 'capacity' in df.columns:
            df['occupancy_pct'] = (df['vehicle_count'] / df['capacity'].replace(0, np.nan)) * 100
            df['occupancy_pct'] = df['occupancy_pct'].fillna(0)
        
        return df
    
    def _add_historical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add lag and rolling features for congestion."""
        df = df.copy()
        
        if 'congestion_score' not in df.columns:
            return df
        
        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Lag features
        for lag in self.config.historical_lags:
            df[f'congestion_lag_{lag}m'] = df['congestion_score'].shift(lag)
        
        # Rolling statistics
        for window in self.config.rolling_windows:
            df[f'congestion_rolling_mean_{window}m'] = (
                df['congestion_score'].rolling(window=window, min_periods=1).mean()
            )
            df[f'congestion_rolling_std_{window}m'] = (
                df['congestion_score'].rolling(window=window, min_periods=1).std()
            )
            df[f'congestion_rolling_min_{window}m'] = (
                df['congestion_score'].rolling(window=window, min_periods=1).min()
            )
            df[f'congestion_rolling_max_{window}m'] = (
                df['congestion_score'].rolling(window=window, min_periods=1).max()
            )
        
        # Fill NaN values with 0 for lags, forward fill for rolling
        lag_cols = [c for c in df.columns if c.startswith('congestion_lag_')]
        df[lag_cols] = df[lag_cols].fillna(0)
        
        rolling_cols = [c for c in df.columns if c.startswith('congestion_rolling_')]
        df[rolling_cols] = df[rolling_cols].bfill().fillna(0)
        
        return df
    
    def _add_spatial_features(self, df: pd.DataFrame, road_id: str) -> pd.DataFrame:
        """Add spatial features (upstream/downstream congestion) using graph topology."""
        df = df.copy()
        
        # Get graph from config
        graph = getattr(self.config, 'graph', None)
        
        if graph is None:
            # No graph available - use NaN to indicate missing data (will be filled with 0 later)
            df['upstream_congestion_avg'] = np.nan
            df['downstream_congestion_avg'] = np.nan
            df['parallel_road_congestion_avg'] = np.nan
            return df
        
        # Get upstream roads (roads feeding into this road's source)
        upstream_roads = graph.get_upstream_roads(road_id)
        # Get downstream roads (roads fed by this road's target)
        downstream_roads = graph.get_downstream_roads(road_id)
        
        # We need congestion data for neighbor roads
        # This assumes the DataFrame has congestion data for all roads at this timestamp
        # For training data, we have historical data; for inference, we need current snapshot
        
        # Create a lookup for congestion scores by road_id at this timestamp
        # The df contains data for a single road over time, but we need cross-road data
        # This is a limitation - spatial features need panel data across roads
        # For now, we'll compute from the graph if we have access to current road states
        
        upstream_congestion = []
        downstream_congestion = []
        
        for up_road in upstream_roads:
            # Try to get congestion from road object if available
            if hasattr(up_road, 'current_congestion'):
                upstream_congestion.append(up_road.current_congestion)
        
        for down_road in downstream_roads:
            if hasattr(down_road, 'current_congestion'):
                downstream_congestion.append(down_road.current_congestion)
        
        # Also check for parallel roads (roads with same source or target)
        parallel_congestion = []
        edge = graph.get_road(road_id)
        if edge:
            # Roads with same source (parallel outgoing)
            same_source = graph.get_neighbors(edge.source)
            for p_road in same_source:
                if p_road.id != road_id and hasattr(p_road, 'current_congestion'):
                    parallel_congestion.append(p_road.current_congestion)
            
            # Roads with same target (parallel incoming)
            same_target = graph.get_predecessors(edge.target)
            for p_road in same_target:
                if p_road.id != road_id and hasattr(p_road, 'current_congestion'):
                    parallel_congestion.append(p_road.current_congestion)
        
        # Compute averages, use NaN for missing (will be filled later)
        df['upstream_congestion_avg'] = np.mean(upstream_congestion) if upstream_congestion else np.nan
        df['downstream_congestion_avg'] = np.mean(downstream_congestion) if downstream_congestion else np.nan
        df['parallel_road_congestion_avg'] = np.mean(parallel_congestion) if parallel_congestion else np.nan
        
        return df
    
    def _add_weather_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add weather features."""
        df = df.copy()
        
        if 'weather_condition' in df.columns:
            # One-hot encode weather
            for cond in ['clear', 'cloudy', 'light_rain', 'heavy_rain', 'fog']:
                df[f'weather_{cond}'] = (df['weather_condition'] == cond).astype(int)
            # Keep original weather_condition column for models that use factorized encoding
        
        # Numerical weather features
        if 'temperature_c' in df.columns:
            df['temperature_c'] = df['temperature_c'].fillna(20.0)
        if 'rain_intensity' in df.columns:
            df['rain_intensity'] = df['rain_intensity'].fillna(0.0)
        if 'visibility_km' in df.columns:
            df['visibility_km'] = df['visibility_km'].fillna(20.0)
        
        return df
    
    def _add_incident_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add incident features."""
        df = df.copy()
        
        if 'incident_count' in df.columns:
            df['incident_count'] = df['incident_count'].fillna(0)
        if 'max_incident_severity' in df.columns:
            df['max_incident_severity'] = df['max_incident_severity'].fillna(0.0)
        if 'capacity_reduction_pct' in df.columns:
            df['capacity_reduction_pct'] = df['capacity_reduction_pct'].fillna(0.0)
        
        return df
    
    def get_feature_names(self) -> List[str]:
        """Get list of feature column names (excluding targets)."""
        # This would be populated after building features on sample data
        exclude_patterns = ['target_', 'timestamp', 'road_id']
        # Would be populated dynamically
        return []


def load_road_metadata(session_factory) -> pd.DataFrame:
    """Load road metadata from database."""
    # Placeholder - would query database for road static info
    # Returns DataFrame with columns: id, distance_km, speed_limit, capacity, road_type, num_lanes
    pass


def prepare_training_data(
    df: pd.DataFrame,
    road_metadata: Optional[pd.DataFrame] = None,
    target_horizon: str = 'target_congestion_15m',
    feature_config: Optional[FeatureConfig] = None
) -> tuple:
    """
    Prepare X, y for training.
    
    Returns:
        (X, y, feature_names)
    """
    engineer = FeatureEngineer(feature_config)
    features_df = engineer.build_features(df, road_metadata, is_training=True)
    
    # Separate features and target
    target_col = target_horizon
    # Preserve road_id, hour, day_of_week for baseline model
    # But exclude non-numeric columns for ML models
    feature_cols = [c for c in features_df.columns 
                    if not c.startswith('target_') 
                    and c not in ['timestamp', 'target_congestion_5m', 
                                  'target_congestion_15m', 'target_congestion_30m', 'target_congestion_60m']]
    
    X = features_df[feature_cols].fillna(0)
    # Convert any object/string columns to numeric (encode categoricals)
    for col in X.columns:
        if X[col].dtype == 'object' or X[col].dtype == 'string':
            X[col] = pd.factorize(X[col])[0]
    y = features_df[target_col].fillna(0)
    
    return X, y, feature_cols


if __name__ == "__main__":
    # Test with sample data
    print("Feature engineering module ready")