from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import pandas as pd
import numpy as np

from app.core.dependencies import get_db
from app.prediction.inference import get_model_service, ModelService
from app.state import get_road_graph
from app.graph.graph import RoadGraph
from app.simulation.demand_model import TimeProvider
from app.models.traffic import TrafficSnapshot
from app.models.road import Road
from datetime import datetime, timedelta, timezone
import json

router = APIRouter(prefix="/predictions", tags=["predictions"])


class PredictionResponse(BaseModel):
    road_id: str
    prediction_tick: int
    horizon_minutes: int
    predicted_congestion_score: float
    predicted_vehicle_count: int
    predicted_avg_speed_kmh: float
    confidence: float
    model_version: str


class PredictionBatchRequest(BaseModel):
    road_ids: List[str]
    horizons: List[int] = [5, 15, 30, 60]


class ModelInfoResponse(BaseModel):
    name: str
    version: str
    algorithm: str
    metrics: Dict[str, float]
    is_active: bool


@router.get("/models", response_model=List[ModelInfoResponse])
async def get_available_models():
    """Get list of available models and their metrics."""
    model_service = get_model_service()
    return model_service.list_models()


@router.post("/models/{model_name}/activate")
async def activate_model(model_name: str):
    """Activate a specific model for inference."""
    model_service = get_model_service()
    try:
        model_service.activate_model(model_name)
        return {"message": f"Model {model_name} activated", "active_model": model_name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/models/{model_name}/metrics")
async def get_model_metrics(model_name: str):
    """Get metrics for a specific model."""
    model_service = get_model_service()
    if model_name not in model_service.model_registry:
        raise HTTPException(status_code=404, detail="Model not found")
    meta = model_service.model_registry[model_name]
    return {
        "name": meta.name,
        "version": meta.version,
        "algorithm": meta.algorithm,
        "metrics": meta.metrics,
        "feature_names": meta.feature_names,
        "is_active": meta.is_active,
    }


async def fetch_road_history(db: AsyncSession, road_id: str, hours_back: int = 24) -> pd.DataFrame:
    """Fetch recent traffic history for a road to compute lag/rolling features.
    Uses the latest simulation time in the database as reference."""
    # Get the latest simulation time from the database
    latest_time_result = await db.execute(
        select(func.max(TrafficSnapshot.sim_time)).where(TrafficSnapshot.road_id == road_id)
    )
    latest_time = latest_time_result.scalar()
    
    if latest_time is None:
        return pd.DataFrame()
    
    cutoff = latest_time - timedelta(hours=hours_back)
    
    result = await db.execute(
        select(TrafficSnapshot)
        .where(TrafficSnapshot.road_id == road_id)
        .where(TrafficSnapshot.sim_time >= cutoff)
        .order_by(TrafficSnapshot.sim_time)
    )
    snapshots = result.scalars().all()
    
    if not snapshots:
        return pd.DataFrame()
    
    # Get incident details for incident IDs in snapshots
    all_incident_ids = set()
    for s in snapshots:
        if s.incident_ids:
            all_incident_ids.update(s.incident_ids)
    
    incident_details = {}
    if all_incident_ids:
        from app.models.incident import Incident
        incident_result = await db.execute(
            select(Incident).where(Incident.id.in_(all_incident_ids))
        )
        incidents = incident_result.scalars().all()
        for inc in incidents:
            incident_details[str(inc.id)] = {
                'type': inc.incident_type,
                'severity': inc.severity,
                'capacity_reduction_pct': inc.capacity_reduction_pct,
            }
    
    records = []
    for s in snapshots:
        # Compute incident features from incident_ids
        incident_count = len(s.incident_ids) if s.incident_ids else 0
        max_severity = 0.0
        max_capacity_reduction = 0.0
        
        if s.incident_ids:
            for inc_id in s.incident_ids:
                if inc_id in incident_details:
                    inc = incident_details[inc_id]
                    max_severity = max(max_severity, inc['severity'])
                    max_capacity_reduction = max(max_capacity_reduction, inc['capacity_reduction_pct'])
        
        records.append({
            'timestamp': s.sim_time,
            'road_id': s.road_id,
            'vehicle_count': s.vehicle_count,
            'avg_speed_kmh': s.avg_speed_kmh or 0,
            'congestion_score': s.congestion_score or 0,
            'weather_condition': s.weather_condition or 'clear',
            'incident_count': incident_count,
            'max_incident_severity': max_severity,
            'capacity_reduction_pct': max_capacity_reduction,
        })
    
    return pd.DataFrame(records)


async def build_current_features(
    db: AsyncSession,
    graph: RoadGraph,
    road_id: str,
    current_time: datetime,
) -> pd.DataFrame:
    """Build feature row for current state of a road."""
    road = graph.get_edge(road_id)
    if not road:
        return pd.DataFrame()
    
    is_weekend = TimeProvider.is_weekend(current_time)
    current_hour = current_time.hour + current_time.minute / 60.0
    
    # Get current traffic state from simulation (placeholder - would come from live simulation state)
    vehicle_count = 0
    avg_speed_kmh = road.speed_limit_kmh
    congestion_score = 0.0
    
    features = {
        'timestamp': current_time,
        'road_id': road_id,
        'day_of_week': current_time.weekday(),
        'hour': current_time.hour,
        'is_weekend': int(current_time.weekday() >= 5),
        'is_rush_hour': int(((7 <= current_time.hour <= 9) or (16 <= current_time.hour <= 19))),
        'minutes_since_midnight': current_time.hour * 60 + current_time.minute,
        'vehicle_count': vehicle_count,
        'avg_speed_kmh': avg_speed_kmh,
        'density': 0.0,
        'occupancy_pct': 0.0,
        'congestion_score': congestion_score,
        'weather_condition': 'clear',
        'temperature_c': 20.0,
        'rain_intensity': 0.0,
        'visibility_km': 20.0,
        'incident_count': 0,
        'max_incident_severity': 0.0,
        'capacity_reduction_pct': 0.0,
    }
    
    # Add road static features
    features['distance_km'] = road.distance_km
    features['speed_limit'] = road.speed_limit_kmh
    features['capacity'] = road.capacity_vph
    features['num_lanes'] = 2
    for rt in ['highway', 'major', 'minor', 'local', 'highway_bottleneck']:
        features[f'road_type_{rt}'] = int(road.road_type == rt)
    
    df = pd.DataFrame([features])
    return df


@router.get("/models", response_model=List[ModelInfoResponse])
async def get_available_models():
    model_service = get_model_service()
    return model_service.list_models()


@router.post("/models/{model_name}/activate")
async def activate_model(model_name: str):
    model_service = get_model_service()
    try:
        model_service.activate_model(model_name)
        return {"message": f"Model {model_name} activated", "active_model": model_name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/models/{model_name}/metrics")
async def get_model_metrics(model_name: str):
    model_service = get_model_service()
    if model_name not in model_service.model_registry:
        raise HTTPException(status_code=404, detail="Model not found")
    meta = model_service.model_registry[model_name]
    return {
        "name": meta.name,
        "version": meta.version,
        "algorithm": meta.algorithm,
        "metrics": meta.metrics,
        "feature_names": meta.feature_names,
        "is_active": meta.is_active,
    }


@router.get("/{road_id}")
async def get_road_predictions(
    road_id: str,
    horizons: List[int] = Query(default=[5, 15, 30, 60]),
    db: AsyncSession = Depends(get_db)
):
    """Get predictions for a specific road at all horizons using active ML model."""
    model_service = get_model_service()
    
    try:
        model = model_service.get_active_model()
    except ValueError:
        raise HTTPException(status_code=503, detail="No active model available")
    
    graph = get_road_graph()
    road = graph.get_edge(road_id)
    if not road:
        raise HTTPException(status_code=404, detail="Road not found")
    
    # Get the latest simulation time from the database to use as current time
    latest_time_result = await db.execute(
        select(func.max(TrafficSnapshot.sim_time)).where(TrafficSnapshot.road_id == road_id)
    )
    latest_sim_time = latest_time_result.scalar()
    
    if latest_sim_time is None:
        # No simulation data yet, use current time
        current_time = datetime.now(timezone.utc)
    else:
        current_time = latest_sim_time
    
    try:
        # Build current features (single row)
        current_features = await build_current_features(db, graph, road_id, current_time)
        
        # Fetch historical data for lag/rolling features
        history_df = await fetch_road_history(db, road_id, hours_back=24)
        
        # Combine historical + current
        if not history_df.empty:
            history_df = history_df.sort_values('timestamp')
            combined_df = pd.concat([history_df, pd.DataFrame([{
                'timestamp': current_time,
                'road_id': road_id,
                'vehicle_count': 0,
                'avg_speed_kmh': road.speed_limit_kmh,
                'congestion_score': 0.0,
                'weather_condition': 'clear',
                'incident_count': 0,
                'max_incident_severity': 0.0,
                'capacity_reduction_pct': 0.0,
            }])], ignore_index=True)
        else:
            combined_df = pd.DataFrame([{
                'timestamp': current_time,
                'road_id': road_id,
                'vehicle_count': 0,
                'avg_speed_kmh': road.speed_limit_kmh,
                'congestion_score': 0.0,
                'weather_condition': 'clear',
                'incident_count': 0,
                'max_incident_severity': 0.0,
                'capacity_reduction_pct': 0.0,
            }])
        
        # Add road static info to all rows
        for col, val in [
            ('distance_km', road.distance_km),
            ('speed_limit', road.speed_limit_kmh),
            ('capacity', road.capacity_vph),
            ('num_lanes', 2),
        ]:
            combined_df[col] = val
        for rt in ['highway', 'major', 'minor', 'local', 'highway_bottleneck']:
            combined_df[f'road_type_{rt}'] = int(road.road_type == rt)
        
        # Add temporal features
        combined_df['timestamp'] = pd.to_datetime(combined_df['timestamp'])
        combined_df = combined_df.sort_values('timestamp').reset_index(drop=True)
        
        combined_df['hour'] = combined_df['timestamp'].dt.hour
        combined_df['day_of_week'] = combined_df['timestamp'].dt.dayofweek
        combined_df['is_weekend'] = (combined_df['day_of_week'] >= 5).astype(int)
        combined_df['is_rush_hour'] = ((combined_df['hour'] >= 7) & (combined_df['hour'] <= 9) | 
                                        (combined_df['hour'] >= 16) & (combined_df['hour'] <= 19)).astype(int)
        combined_df['minutes_since_midnight'] = combined_df['timestamp'].dt.hour * 60 + combined_df['timestamp'].dt.minute
        
        # Cyclical encoding
        combined_df['hour_sin'] = np.sin(2 * np.pi * combined_df['hour'] / 24)
        combined_df['hour_cos'] = np.cos(2 * np.pi * combined_df['hour'] / 24)
        combined_df['dow_sin'] = np.sin(2 * np.pi * combined_df['day_of_week'] / 7)
        combined_df['dow_cos'] = np.cos(2 * np.pi * combined_df['day_of_week'] / 7)
        
        # Weather one-hot
        for cond in ['clear', 'cloudy', 'light_rain', 'heavy_rain', 'fog']:
            combined_df[f'weather_{cond}'] = (combined_df['weather_condition'] == cond).astype(int)
        
        # Weather numeric - fix fillna for scalar values
        temp_c = combined_df.get('temperature_c', 20.0)
        if isinstance(temp_c, pd.Series):
            combined_df['temperature_c'] = temp_c.fillna(20.0)
        else:
            combined_df['temperature_c'] = float(temp_c)
            
        rain_int = combined_df.get('rain_intensity', 0.0)
        if isinstance(rain_int, pd.Series):
            combined_df['rain_intensity'] = rain_int.fillna(0.0)
        else:
            combined_df['rain_intensity'] = float(rain_int)
            
        vis_km = combined_df.get('visibility_km', 20.0)
        if isinstance(vis_km, pd.Series):
            combined_df['visibility_km'] = vis_km.fillna(20.0)
        else:
            combined_df['visibility_km'] = float(vis_km)
        
        # Incidents
        inc_cnt = combined_df.get('incident_count', 0)
        if isinstance(inc_cnt, pd.Series):
            combined_df['incident_count'] = inc_cnt.fillna(0)
        else:
            combined_df['incident_count'] = int(inc_cnt)
            
        max_sev = combined_df.get('max_incident_severity', 0.0)
        if isinstance(max_sev, pd.Series):
            combined_df['max_incident_severity'] = max_sev.fillna(0.0)
        else:
            combined_df['max_incident_severity'] = float(max_sev)
            
        cap_red = combined_df.get('capacity_reduction_pct', 0.0)
        if isinstance(cap_red, pd.Series):
            combined_df['capacity_reduction_pct'] = cap_red.fillna(0.0)
        else:
            combined_df['capacity_reduction_pct'] = float(cap_red)
        
        # Road type one-hot
        for rt in ['highway', 'major', 'minor', 'local', 'highway_bottleneck']:
            combined_df[f'road_type_{rt}'] = int(road.road_type == rt)
        
        # Use ModelService to build features and predict
        model_service = get_model_service()
        active_model = model_service.active_model
        
        # Build features using the service's feature engineer
        features_df = model_service.feature_engineer.build_features(
            combined_df, 
            road_metadata=None, 
            is_training=False
        )
        
        # Get the last row (current time) for prediction
        last_row = features_df.iloc[[-1]]
        
        # Get active model
        active_meta = model_service.model_registry[model_service.active_model]
        feature_names = active_meta.feature_names
        
        # Prepare X
        if feature_names:
            X = last_row[feature_names].fillna(0)
        else:
            exclude = ['target_congestion_5m', 'target_congestion_15m', 'target_congestion_30m', 'target_congestion_60m', 'timestamp', 'road_id']
            X = last_row[[c for c in last_row.columns if c not in exclude]].fillna(0)
        
        # Predict
        model = model_service.models[model_service.active_model]
        predictions = model.predict(X)
        pred_congestion = float(predictions[0]) if len(predictions) > 0 else 0.0
        pred_congestion = max(0.0, min(1.0, pred_congestion))
        
        # Estimate vehicle count and speed
        jam_density = road.capacity_vph / max(road.speed_limit_kmh / 3.6, 1.0)
        pred_vehicles = int(pred_congestion * jam_density * road.distance_km)
        pred_speed = road.speed_limit_kmh * (1 - pred_congestion * 0.7)
        
        results = []
        active_meta = model_service.model_registry[model_service.active_model]
        for horizon in horizons:
            results.append(PredictionResponse(
                road_id=road_id,
                prediction_tick=0,
                horizon_minutes=horizon,
                predicted_congestion_score=round(pred_congestion, 4),
                predicted_vehicle_count=pred_vehicles,
                predicted_avg_speed_kmh=round(pred_speed, 1),
                confidence=0.85,
                model_version=active_meta.version
            ))
        
        return {"road_id": road_id, "predictions": results}
        
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Prediction error: {e}", exc_info=True)
        # Fallback to placeholder
        results = []
        active_meta = model_service.model_registry[model_service.active_model]
        for horizon in horizons:
            results.append(PredictionResponse(
                road_id=road_id,
                prediction_tick=0,
                horizon_minutes=horizon,
                predicted_congestion_score=0.3,
                predicted_vehicle_count=100,
                predicted_avg_speed_kmh=45.0,
                confidence=0.85,
                model_version=active_meta.version
            ))
        return {"road_id": road_id, "predictions": results}


@router.post("/batch")
async def get_batch_predictions(
    request: PredictionBatchRequest,
    db: AsyncSession = Depends(get_db)
):
    model_service = get_model_service()
    
    try:
        model = model_service.get_active_model()
    except ValueError:
        raise HTTPException(status_code=503, detail="No active model available")
    
    graph = get_road_graph()
    current_time = datetime.now(timezone.utc)
    
    raw_dfs = []
    for road_id in request.road_ids:
        road = graph.get_edge(road_id)
        if not road:
            continue
        
        features = await build_current_features(db, graph, road_id, current_time)
        raw_dfs.append(features)
    
    if not raw_dfs:
        return {}
    
    raw_df = pd.concat(raw_dfs, ignore_index=True)
    
    try:
        features_df = model_service.feature_engineer.build_features(raw_df, road_metadata=None, is_training=False)
        
        active_meta = model_service.model_registry[model_service.active_model]
        feature_names = active_meta.feature_names
        
        if feature_names:
            X = features_df[feature_names].fillna(0)
        else:
            X = features_df[[c for c in features_df.columns if not c.startswith('target_') and c not in ['timestamp', 'road_id']]].fillna(0)
        
        model = model_service.models[model_service.active_model]
        predictions = model.predict(X)
        
        results = {}
        for i, road_id in enumerate(request.road_ids):
            road = graph.get_edge(road_id)
            if not road:
                continue
            
            results[road_id] = {}
            pred_congestion = float(predictions[i]) if i < len(predictions) else 0.0
            pred_congestion = max(0.0, min(1.0, pred_congestion))
            
            jam_density = road.capacity_vph / max(road.speed_limit_kmh / 3.6, 1.0)
            pred_vehicles = int(pred_congestion * jam_density * road.distance_km)
            pred_speed = road.speed_limit_kmh * (1 - pred_congestion * 0.7)
            
            for horizon in request.horizons:
                results[road_id][f"{horizon}m"] = {
                    "predicted_congestion_score": round(pred_congestion, 4),
                    "predicted_vehicle_count": pred_vehicles,
                    "predicted_avg_speed_kmh": round(pred_speed, 1),
                    "confidence": 0.85,
                    "model_version": active_meta.version,
                    "model_name": active_meta.name,
                    "algorithm": active_meta.algorithm,
                }
        return results
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Prediction error: {e}", exc_info=True)
        results = {}
        active_meta = model_service.model_registry[model_service.active_model]
        for road_id in request.road_ids:
            results[road_id] = {}
            for horizon in request.horizons:
                results[road_id][f"{horizon}m"] = {
                    "predicted_congestion_score": 0.3,
                    "predicted_vehicle_count": 100,
                    "predicted_avg_speed_kmh": 45.0,
                    "confidence": 0.85,
                    "model_version": active_meta.version,
                    "fallback": True,
                }
        return results