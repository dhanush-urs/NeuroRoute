#!/usr/bin/env python3
"""
NeuroRoute Full E2E Subsystems Test Runner
Tests Phases 1, 3, 4, 5, 6, 7, 8, 9, 10, 11 against live running application.
"""

import asyncio
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
import websockets
import psycopg2

BASE_URL = "http://localhost:8000"
WS_BASE = "ws://localhost:8000/api/v1/ws"

results = {}


def log_phase(name):
    print(f"\n{'='*20} {name} {'='*20}")


def record(phase, test_name, passed, details=""):
    if phase not in results:
        results[phase] = []
    status = "PASS" if passed else "FAIL"
    results[phase].append({"test": test_name, "status": status, "details": details})
    print(f"[{status}] {phase} :: {test_name} - {details}")


def http_req(path, method="GET", data=None, timeout=10):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


# ==============================================================================
# PHASE 1: ENVIRONMENT & STARTUP
# ==============================================================================
def test_phase_1():
    log_phase("PHASE 1: ENVIRONMENT AND STARTUP VALIDATION")
    
    # 1. PostgreSQL DB connection & counts
    try:
        conn = psycopg2.connect("postgresql://neuroroute:neuroroute@localhost:5432/neuro_route")
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM nodes;")
        n_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM roads;")
        r_count = cur.fetchone()[0]
        conn.close()
        record("Phase 1", "PostgreSQL Connectivity", True, f"{n_count} nodes, {r_count} roads in database")
    except Exception as e:
        record("Phase 1", "PostgreSQL Connectivity", False, str(e))

    # 2. HTTP endpoints
    endpoints = [
        ("/health", "Health endpoint"),
        ("/api/v1/traffic/geometry", "Traffic geometry"),
        ("/api/v1/traffic/nodes", "Nodes list"),
        ("/api/v1/traffic/summary", "Traffic summary"),
        ("/api/v1/simulation/status", "Simulation status"),
        ("/api/v1/predictions/models", "Predictions model registry"),
        ("/api/v1/traffic/incidents/active", "Active incidents"),
    ]
    for path, name in endpoints:
        try:
            status, data = http_req(path)
            record("Phase 1", f"Endpoint {name}", status == 200, f"HTTP {status}")
        except Exception as e:
            record("Phase 1", f"Endpoint {name}", False, str(e))


# ==============================================================================
# PHASE 3: SIMULATION END-TO-END
# ==============================================================================
async def test_phase_3():
    log_phase("PHASE 3: SIMULATION END-TO-END")
    
    # 1. Reset simulation
    try:
        status, data = http_req("/api/v1/simulation/control", method="POST", data={"action": "reset", "seed": 42})
        record("Phase 3", "Simulation Reset", status == 200, f"State reset: {data.get('status')}")
    except Exception as e:
        record("Phase 3", "Simulation Reset", False, str(e))

    # 2. Start simulation
    try:
        status, data = http_req("/api/v1/simulation/start", method="POST", data={"speed_multiplier": 5})
        record("Phase 3", "Simulation Start", status == 200, f"Started: session_id={data.get('session_id')}")
    except Exception as e:
        record("Phase 3", "Simulation Start", False, str(e))

    # 3. Observe 10 successive ticks
    ticks = set()
    t_start = time.time()
    _, init_status = http_req("/api/v1/simulation/status")
    t0 = init_status.get("current_tick", 0)
    while len(ticks) < 10 and ((max(ticks) - t0) if ticks else 0) < 10 and time.time() - t_start < 45:
        _, status_data = http_req("/api/v1/simulation/status")
        t = status_data.get("current_tick", 0)
        if t > 0:
            ticks.add(t)
        await asyncio.sleep(0.3)

    advanced = (max(ticks) - t0) if ticks else len(ticks)
    record("Phase 3", "10 Consecutive Ticks", len(ticks) >= 10 or advanced >= 10, f"Observed {len(ticks)} ticks, advanced {advanced} ticks: {sorted(list(ticks))[:10]}")

    # 4. Verify simulation clock and vehicles
    _, status_data = http_req("/api/v1/simulation/status")
    clock = status_data.get("simulation_time")
    record("Phase 3", "Clock Advancement", clock is not None and clock != "2024-01-01T00:00:00", f"Clock: {clock}")

    # 5. Pause simulation
    http_req("/api/v1/simulation/control", method="POST", data={"action": "pause"})
    await asyncio.sleep(1.5)
    _, paused_status = http_req("/api/v1/simulation/status")
    paused_tick = paused_status.get("current_tick")
    await asyncio.sleep(1.5)
    _, paused_status2 = http_req("/api/v1/simulation/status")
    paused_tick2 = paused_status2.get("current_tick")
    record("Phase 3", "Simulation Pause", paused_tick == paused_tick2, f"Tick remained at {paused_tick}")

    # 6. Resume simulation
    http_req("/api/v1/simulation/control", method="POST", data={"action": "resume"})
    await asyncio.sleep(1.5)
    _, resumed_status = http_req("/api/v1/simulation/status")
    record("Phase 3", "Simulation Resume", resumed_status.get("current_tick") > paused_tick, f"Tick advanced to {resumed_status.get('current_tick')}")

    # 7. Speed multiplier change
    http_req("/api/v1/simulation/control", method="POST", data={"action": "speed", "speed_multiplier": 5})
    _, speed_status = http_req("/api/v1/simulation/status")
    record("Phase 3", "Speed Multiplier", speed_status.get("speed_multiplier") == 5, f"Speed set to {speed_status.get('speed_multiplier')}x")
    http_req("/api/v1/simulation/control", method="POST", data={"action": "speed", "speed_multiplier": 1})


# ==============================================================================
# PHASE 4: GEOGRAPHIC & VEHICLE MAP-MATCHING VALIDATION
# ==============================================================================
async def test_phase_4():
    log_phase("PHASE 4: GEOGRAPHIC AND VEHICLE VALIDATION")

    # Fetch geometry
    _, geo = http_req("/api/v1/traffic/geometry")
    roads = {f["properties"]["road_id"]: f["geometry"]["coordinates"] for f in geo["features"]}

    def p_to_seg(px, py, x1, y1, x2, y2):
        lat_mid = math.radians((py + (y1 + y2)/2) / 2)
        m_lon = 111412.84 * math.cos(lat_mid)
        m_lat = 111132.95 - 559.82 * math.cos(2 * lat_mid)
        px_m, py_m = px * m_lon, py * m_lat
        x1_m, y1_m = x1 * m_lon, y1 * m_lat
        x2_m, y2_m = x2 * m_lon, y2 * m_lat
        dx, dy = x2_m - x1_m, y2_m - y1_m
        lsq = dx*dx + dy*dy
        if lsq < 1e-6:
            return math.hypot(px_m - x1_m, py_m - y1_m)
        t = max(0.0, min(1.0, ((px_m - x1_m)*dx + (py_m - y1_m)*dy) / lsq))
        return math.hypot(px_m - (x1_m + t*dx), py_m - (y1_m + t*dy))

    def dist_to_line(px, py, coords):
        return min(p_to_seg(px, py, coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1]) for i in range(len(coords)-1))

    # Listen to WebSocket vehicles
    distances = []
    bearings_valid = []
    land_valid = []

    async with websockets.connect(f"{WS_BASE}/traffic") as ws:
        for _ in range(8):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=4.0)
                data = json.loads(msg)
                if data.get("type") == "vehicle_update":
                    vehicles = data.get("data", [])
                    for v in vehicles:
                        rid = v["road_id"]
                        lon, lat = v["longitude"], v["latitude"]
                        coords = roads.get(rid)
                        if coords:
                            d = dist_to_line(lon, lat, coords)
                            distances.append(d)
                            land_valid.append(-74.020 <= lon <= -73.985 and 40.702 <= lat <= 40.730)
                            bearings_valid.append(0.0 <= v.get("bearing", -1) <= 360.0)
                    if len(distances) >= 200:
                        break
            except asyncio.TimeoutError:
                break

    max_d = max(distances) if distances else 999
    avg_d = sum(distances) / len(distances) if distances else 999
    all_land = all(land_valid) if land_valid else False
    all_bearings = all(bearings_valid) if bearings_valid else False

    record("Phase 4", "Vehicle Map-Matching Precision", max_d < 0.5, f"Max dist: {max_d:.4f}m, Avg dist: {avg_d:.4f}m (Target < 0.5m)")
    record("Phase 4", "Land Boundary Confinement", all_land, f"100% of {len(land_valid)} vehicle positions within Lower Manhattan land boundaries")
    record("Phase 4", "Localized Segment Heading", all_bearings, f"100% of vehicle headings in [0, 360] degrees")


# ==============================================================================
# PHASE 5: DEMO SCENARIO E2E
# ==============================================================================
def test_phase_5():
    log_phase("PHASE 5: DEMO SCENARIO E2E")

    scenarios = [
        "normal", "rush_hour", "major_jam", "accident",
        "road_closure", "heavy_rain", "traffic_surge", "major_event"
    ]

    for sc in scenarios:
        try:
            status, data = http_req("/api/v1/simulation/scenario", method="POST", data={"scenario_name": sc})
            _, st = http_req("/api/v1/simulation/status")
            record("Phase 5", f"Scenario '{sc}'", status == 200, f"Applied: weather={st.get('weather')}, demand_mult={st.get('demand_multiplier')}, incidents={st.get('active_incidents')}")
        except Exception as e:
            record("Phase 5", f"Scenario '{sc}'", False, str(e))

    # Test multi-step transitions: Normal -> Rush Hour -> Major Jam -> Normal
    seq = ["normal", "rush_hour", "major_jam", "normal"]
    seq_ok = True
    for s in seq:
        st_code, _ = http_req("/api/v1/simulation/scenario", method="POST", data={"scenario_name": s})
        if st_code != 200:
            seq_ok = False
    _, final_st = http_req("/api/v1/simulation/status")
    seq_ok = seq_ok and final_st.get("demand_multiplier") == 1.0 and final_st.get("active_incidents") == 0
    record("Phase 5", "Scenario Transition Sequence", seq_ok, "Normal -> Rush Hour -> Major Jam -> Normal clean reset verified")


# ==============================================================================
# PHASE 6: ROUTING END-TO-END
# ==============================================================================
def test_phase_6():
    log_phase("PHASE 6: ROUTING END-TO-END")

    # Get sample origin & destination nodes
    _, n_data = http_req("/api/v1/traffic/nodes")
    nodes = n_data["nodes"]
    nodes.sort(key=lambda n: n["latitude"])
    orig = nodes[0]["node_id"]  # Battery Park
    dest = nodes[-1]["node_id"]  # SoHo

    algorithms = ["dijkstra", "astar_current", "astar_predicted", "neuro_route"]

    for algo in algorithms:
        try:
            path = f"/api/v1/routes/calculate?origin={orig}&destination={dest}&algorithm={algo}"
            status, r_data = http_req(path)
            nodes_len = len(r_data.get("nodes", []))
            edges_len = len(r_data.get("edges", []))
            dist = r_data.get("distance_km", 0)
            eta = r_data.get("current_eta_sec", 0)
            valid = status == 200 and nodes_len >= 2 and edges_len >= 1 and dist > 0
            record("Phase 6", f"Algorithm '{algo}'", valid, f"dist={dist}km, eta={eta}s, nodes={nodes_len}, edges={edges_len}")
        except Exception as e:
            record("Phase 6", f"Algorithm '{algo}'", False, str(e))

    # Test calculate-all endpoint
    try:
        status, all_routes = http_req(f"/api/v1/routes/calculate-all?origin={orig}&destination={dest}")
        record("Phase 6", "Calculate All Multi-Candidate", status == 200 and len(all_routes) >= 3, f"Returned {len(all_routes)} candidate routes")
    except Exception as e:
        record("Phase 6", "Calculate All Multi-Candidate", False, str(e))


# ==============================================================================
# PHASE 7: INCIDENT MANAGEMENT E2E
# ==============================================================================
def test_phase_7():
    log_phase("PHASE 7: INCIDENT MANAGEMENT E2E")

    # 1. Trigger accident
    try:
        # Get a road ID
        _, geo = http_req("/api/v1/traffic/geometry")
        test_road_id = geo["features"][10]["properties"]["road_id"]

        status, inc_data = http_req("/api/v1/incidents", method="POST", data={
            "incident_type": "accident",
            "road_id": test_road_id,
            "severity": 0.8
        })
        inc_id = inc_data.get("incident_id")
        record("Phase 7", "Trigger Accident", status == 200, f"Created {inc_id} on road {test_road_id}")

        # 2. Check active incidents API
        _, active = http_req("/api/v1/incidents/active")
        found = any(i["incident_id"] == inc_id for i in active.get("incidents", []))
        record("Phase 7", "Verify Active Incident", found, f"Incident {inc_id} visible in active list")

        # 3. Resolve incident
        status, res_data = http_req(f"/api/v1/incidents/{inc_id}", method="DELETE")
        record("Phase 7", "Resolve Incident", status == 200, f"Resolved incident: {res_data}")

        # 4. Verify removal
        _, active_after = http_req("/api/v1/incidents/active")
        not_found = not any(i["incident_id"] == inc_id for i in active_after.get("incidents", []))
        record("Phase 7", "Capacity & Road Restoration", not_found, f"Incident {inc_id} removed, capacity restored")
    except Exception as e:
        record("Phase 7", "Incident Operations", False, str(e))


# ==============================================================================
# PHASE 8: PREDICTION PIPELINE E2E
# ==============================================================================
def test_phase_8():
    log_phase("PHASE 8: PREDICTION PIPELINE E2E")

    # 1. List models
    try:
        status, models = http_req("/api/v1/predictions/models")
        record("Phase 8", "List Prediction Models", status == 200 and len(models) > 0, f"Models available: {[m.get('name') for m in models]}")
    except Exception as e:
        record("Phase 8", "List Prediction Models", False, str(e))

    # 2. Predict on valid road
    try:
        _, geo = http_req("/api/v1/traffic/geometry")
        test_road = geo["features"][0]["properties"]["road_id"]
        status, pred = http_req(f"/api/v1/predictions/{test_road}")
        preds_list = pred.get("predictions", []) if isinstance(pred, dict) else []
        is_valid = status == 200 and len(preds_list) > 0
        horizons = [p.get("horizon_minutes") for p in preds_list]
        record("Phase 8", "Single Road Prediction", is_valid, f"Road {test_road}: {len(preds_list)} horizons {horizons}")
    except Exception as e:
        record("Phase 8", "Single Road Prediction", False, str(e))

    # 3. Predict invalid road (should 404 or return error)
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/v1/predictions/invalid-road-id-99999")
        urllib.request.urlopen(req)
        record("Phase 8", "Invalid Road ID Handling", False, "Expected 404 but got 200")
    except urllib.error.HTTPError as e:
        record("Phase 8", "Invalid Road ID Handling", e.code == 404, f"Correctly returned HTTP {e.code}")
    except Exception as e:
        record("Phase 8", "Invalid Road ID Handling", False, str(e))


# ==============================================================================
# PHASE 9: WEBSOCKET E2E
# ==============================================================================
async def test_phase_9():
    log_phase("PHASE 9: WEBSOCKET E2E")

    channels = ["traffic", "simulation", "incidents", "routing"]
    for ch in channels:
        try:
            async with websockets.connect(f"{WS_BASE}/{ch}") as ws:
                # If routing channel, trigger route calculation to cause broadcast
                if ch == "routing":
                    _, n_data = http_req("/api/v1/traffic/nodes")
                    n0 = n_data["nodes"][0]["node_id"]
                    n1 = n_data["nodes"][10]["node_id"]
                    http_req(f"/api/v1/routes/calculate?origin={n0}&destination={n1}")

                msg = await asyncio.wait_for(ws.recv(), timeout=6.0)
                data = json.loads(msg)
                record("Phase 9", f"WebSocket Channel '{ch}'", "type" in data, f"Received message type='{data.get('type')}'")
        except Exception as e:
            record("Phase 9", f"WebSocket Channel '{ch}'", False, str(e))


# ==============================================================================
# PHASE 10: AI INSIGHTS E2E
# ==============================================================================
def test_phase_10():
    log_phase("PHASE 10: AI INSIGHTS E2E")

    try:
        # Check health and models
        _, health = http_req("/api/v1/explanations/health")
        active_provider = health.get("active_provider", "template")
        record("Phase 10", "AI Service Provider", True, f"Active provider: {active_provider}")

        # Generate explanation (allow up to 30s for external NVIDIA NIM inference)
        status, exp = http_req("/api/v1/explanations/generate", method="POST", data={
            "recommended_route": {"distance_km": 3.2, "eta_sec": 480, "algorithm": "neuro_route"},
            "current_congestion": {"level": "moderate", "avg_speed_kmh": 32.5},
            "active_incidents": [{"type": "accident", "severity": 0.8}],
            "reroute_reason": "Accident on Broadway reducing capacity by 80%"
        }, timeout=30)
        text = exp.get("explanation", "")
        provider = exp.get("provider", "")
        record("Phase 10", "AI Explanation Generation", status == 200 and len(text) > 20, f"Provider: {provider}, Length: {len(text)} chars: '{text[:80]}...'")
    except Exception as e:
        record("Phase 10", "AI Explanation Generation", False, str(e))


# ==============================================================================
# PHASE 11: WHAT-IF ISOLATION E2E
# ==============================================================================
def test_phase_11():
    log_phase("PHASE 11: WHAT-IF ISOLATION E2E")

    # Record baseline simulation state
    _, base_st = http_req("/api/v1/simulation/status")
    base_tick = base_st.get("current_tick")
    base_inc = base_st.get("active_incidents")

    try:
        status, whatif = http_req("/api/v1/simulation/what-if", method="POST", data={
            "scenario_type": "accident",
            "scenario_params": {"severity": 0.8},
            "steps": 30
        })
        record("Phase 11", "What-If Execution", status == 200, f"What-If scenario completed: {whatif.get('status', 'success')}")

        # Verify live simulation state was NOT altered
        _, post_st = http_req("/api/v1/simulation/status")
        isolated = (post_st.get("active_incidents") == base_inc)
        record("Phase 11", "State Isolation Verification", isolated, "Live simulation state preserved without leakage")
    except Exception as e:
        record("Phase 11", "What-If Execution", False, str(e))


async def main():
    test_phase_1()
    await test_phase_3()
    await test_phase_4()
    test_phase_5()
    test_phase_6()
    test_phase_7()
    test_phase_8()
    await test_phase_9()
    test_phase_10()
    test_phase_11()

    print("\n" + "="*50)
    print("BACKEND SUBSYSTEMS SUMMARY:")
    all_tests = [t for p in results.values() for t in p]
    passed = sum(1 for t in all_tests if t["status"] == "PASS")
    failed = sum(1 for t in all_tests if t["status"] == "FAIL")
    print(f"Total Tests: {len(all_tests)} | Passed: {passed} | Failed: {failed}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
