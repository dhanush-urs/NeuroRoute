# Machine Learning Pipeline

## Overview

NeuroRoute uses a **time-series forecasting** approach to predict road congestion 5, 15, 30, and 60 minutes into the future. The pipeline is designed for **offline training** with **online inference**.

## Dataset Generation

### Synthetic Data Design

The dataset is generated deterministically from the traffic simulation engine, ensuring:
- **Reproducibility**: Same seed → same data
- **Realistic patterns**: Rush hours, weekends, weather, incidents
- **No leakage**: Chronological splits only

### Features (per road per tick)

| Category | Features | Count |
|----------|----------|-------|
| **Temporal** | hour, day_of_week, is_weekend, is_rush_hour, minutes_since_midnight | 5 |
| **Road Static** | distance_km, speed_limit, capacity, road_type (one-hot), num_lanes | 8 |
| **Traffic State** | vehicle_count, avg_speed_kmh, density, occupancy_pct, congestion_score | 5 |
| **Historical** | congestion_1h_ago, congestion_3h_ago, congestion_24h_ago, rolling_avg_1h, rolling_avg_3h | 5 |
| **Spatial** | upstream_congestion_avg, downstream_congestion_avg, parallel_road_congestion_avg | 3 |
| **Weather** | temperature_c, rain_intensity, visibility_km, weather_condition (one-hot) | 8 |
| **Incidents** | active_incident_count, max_incident_severity, capacity_reduction_pct | 3 |
| **TOTAL** | | **37** |

### Targets

| Target | Description | Primary |
|--------|-------------|---------|
| `congestion_5m` | Congestion in 5 minutes | No |
| `congestion_15m` | Congestion in 15 minutes | **Yes** |
| `congestion_30m` | Congestion in 30 minutes | No |
| `congestion_60m` | Congestion in 60 minutes | No |

### Generation Parameters

```python
DatasetGenerator(
    seed=42,
    num_roads=200,           # Configurable
    num_days=7,              # 7 days = 10,080 minutes
    tick_interval_min=1      # 1-minute resolution
)
# Records: 200 roads × 10,080 ticks = 2,016,000 rows
```

**Development mode**: 50 roads × 1 day = 72,000 rows (fast iteration)

### Output Format

Parquet file with columns:
```
timestamp, road_id, day_of_week, hour, is_weekend, is_rush_hour,
minutes_since_midnight, vehicle_count, avg_speed_kmh, density,
occupancy_pct, congestion_score, weather_condition, temperature_c,
rain_intensity, visibility_km, incident_count, max_incident_severity,
capacity_reduction_pct, target_congestion_5m, target_congestion_15m,
target_congestion_30m, target_congestion_60m
```

## Models

### 1. Historical Baseline

**Method**: Per-road, per-hour-of-week moving average

```python
class BaselineModel:
    def fit(self, df):
        # Group by road_id, hour_of_week (0-167)
        self.baseline = df.groupby(['road_id', 'hour_of_week'])['congestion_score'].mean()
    
    def predict(self, features):
        hour_of_week = features['day_of_week'] * 24 + features['hour']
        return self.baseline.get((features['road_id'], hour_of_week), 0.3)
```

**Pros**: Fast, interpretable, no training
**Cons**: Cannot capture incidents, weather, spatial effects

---

### 2. Random Forest

**Library**: scikit-learn

**Configuration**:
```python
RandomForestRegressor(
    n_estimators=200,
    max_depth=15,
    min_samples_split=10,
    min_samples_leaf=5,
    max_features='sqrt',
    random_state=42,
    n_jobs=-1
)
```

**Training**: ~30 seconds on full dataset

**Expected Metrics** (on test set):
- MAE: ~0.08
- RMSE: ~0.11
- R²: ~0.75
- Inference: ~5ms per 1000 predictions

---

### 3. XGBoost

**Library**: xgboost

**Configuration**:
```python
XGBRegressor(
    n_estimators=300,
    max_depth=8,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    early_stopping_rounds=20,
    eval_metric='mae',
    random_state=42,
    n_jobs=-1
)
```

**Training**: ~60 seconds on full dataset

**Expected Metrics** (on test set):
- MAE: ~0.07
- RMSE: ~0.10
- R²: ~0.78
- Inference: ~8ms per 1000 predictions

---

### 4. LSTM (Optional)

**Library**: PyTorch

**Architecture**:
```
Input (37 features) → Linear(64) → LSTM(64, 2 layers) → Linear(32) → Linear(4 targets)
```

**Configuration**:
```python
LSTMModel(
    input_dim=37,
    hidden_dim=64,
    num_layers=2,
    output_dim=4,  # 4 horizons
    dropout=0.2,
    sequence_length=12  # 12 time steps = 12 minutes history
)
```

**Training**: ~10 minutes on GPU

**Expected Metrics**:
- MAE: ~0.065
- RMSE: ~0.09
- R²: ~0.80
- Inference: ~15ms per 1000 predictions

---

## Training Pipeline

### Data Splits (Chronological!)

```
┌─────────────────────────────────────────────────────────────┐
│  Days 1-21 (Train)    Days 22-25 (Val)    Days 26-30 (Test) │
│  60%                    13%                   27%            │
└─────────────────────────────────────────────────────────────┘
```

**Critical**: No random shuffle! Time-series leakage would inflate metrics.

### Training Script

```bash
# Train all models
python scripts/train_model.py --data data/processed/traffic_dataset.parquet

# Train specific model
python scripts/train_model.py --model random_forest

# Compare models
python scripts/train_model.py --compare
```

### Model Registry

Each trained model is registered in `model_registry` table:

```sql
INSERT INTO model_registry (
    model_name, version, algorithm, metrics, hyperparameters,
    feature_list, model_path, is_active
) VALUES (
    'congestion_forecaster', 'v1.2', 'xgboost',
    '{"mae": 0.072, "rmse": 0.098, "r2": 0.78, "inference_ms": 8}',
    '{"n_estimators": 300, "max_depth": 8, ...}',
    '["road_id", "hour", "congestion_score", ...]',
    '/app/models/xgboost_v1.2.joblib', true
);
```

---

## Inference Service

### Singleton Pattern

```python
class ModelService:
    _instance = None
    _model = None
    _model_version = None
    
    @classmethod
    def get_instance(cls) -> 'ModelService':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def load_model(self, version: str = "latest"):
        # Load from model_registry
        self._model = joblib.load(model_path)
        self._model_version = version
    
    def predict(self, features: pd.DataFrame) -> np.ndarray:
        # Returns shape (n_samples, 4) for 4 horizons
        return self._model.predict(features)
```

### Inference Pipeline

```
Traffic Snapshot (per road)
    │
    ▼
FeatureEngineer.build_features(snapshot, history, weather, incidents)
    │
    ▼
ModelService.predict(features_df) → predictions (n_roads × 4 horizons)
    │
    ▼
PredictionWriter.persist(predictions, session_id, tick)
    │
    ▼
GraphWeightUpdater.update_edges(predictions)
```

### Batch Inference

For performance, predictions are batched:

```python
def predict_batch(self, road_features: List[Dict]) -> List[Prediction]:
    df = pd.DataFrame(road_features)
    preds = self._model.predict(df)  # Vectorized
    return [Prediction(...) for pred in preds]
```

**Batch size**: 100 roads per call (configurable)

---

## Evaluation

### Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **MAE** | mean(\|y - ŷ\|) | < 0.08 |
| **RMSE** | sqrt(mean((y - ŷ)²)) | < 0.11 |
| **R²** | 1 - SS_res/SS_tot | > 0.75 |
| **Inference Time** | p95 latency | < 50ms |

### Model Comparison (Example)

| Model | MAE | RMSE | R² | Inference (ms/1k) | Train Time |
|-------|-----|------|-----|-------------------|------------|
| Baseline | 0.142 | 0.185 | 0.42 | 0.5 | - |
| Random Forest | 0.081 | 0.112 | 0.75 | 5 | 30s |
| XGBoost | 0.072 | 0.098 | 0.78 | 8 | 60s |
| LSTM | 0.065 | 0.091 | 0.80 | 15 | 10m |

### Evaluation Script

```bash
python scripts/train_model.py --evaluate --data traffic_dataset.parquet
```

Outputs comparison table and saves plots to `data/models/evaluation/`.

---

## Feature Importance

### Random Forest Top Features

1. `congestion_score` (current) — 0.35
2. `hour` — 0.18
3. `upstream_congestion_avg` — 0.12
4. `vehicle_count` — 0.09
5. `is_rush_hour` — 0.08
6. `downstream_congestion_avg` — 0.06
7. `weather_condition` — 0.04
8. `incident_count` — 0.03
9. `rolling_avg_1h` — 0.03
10. `temperature_c` — 0.02

### Interpretation

- **Current congestion** is the strongest predictor (temporal persistence)
- **Time of day** captures daily patterns
- **Spatial features** (upstream/downstream) capture propagation
- **Incidents/weather** have lower importance but critical for edge cases

---

## Limitations & Future Work

### Current Limitations

1. **No real-time data** — purely synthetic training
2. **Single-city** — not tested on multiple topologies
3. **Fixed horizons** — 5/15/30/60 min only
4. **No uncertainty quantification** — point predictions only
5. **Feature engineering manual** — could use automated feature discovery

### Future Improvements

1. **Spatiotemporal GNN** — Graph Neural Network on road graph
2. **Probabilistic forecasting** — Prediction intervals
3. **Online learning** — Model updates from live data
4. **Multi-city transfer learning** — Pre-train on synthetic, fine-tune on real
5. **Explainable AI** — SHAP values per prediction
6. **Ensemble stacking** — Combine RF + XGBoost + LSTM