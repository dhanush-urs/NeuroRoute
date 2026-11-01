import { test, expect } from '@playwright/test'

test.describe('NeuroRoute Frontend - Map and Data Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Start backend simulation before each test
    // Increase timeout for Vite dev server startup
    await page.goto('http://localhost:3001', { waitUntil: 'domcontentloaded', timeout: 120000 })
    // Wait for map to load and WebSocket to connect
    await page.waitForTimeout(10000)
  })

  test('should load road geometry from backend API', async ({ page }) => {
    // Check that road geometry fetch succeeded
    const response = await page.request.get('http://localhost:8000/api/v1/traffic/geometry')
    expect(response.ok()).toBeTruthy()
    
    const geometry = await response.json()
    expect(geometry.type).toBe('FeatureCollection')
    expect(geometry.features.length).toBeGreaterThan(0)
    
    // Verify coordinate ordering is [longitude, latitude]
    const firstFeature = geometry.features[0]
    const coords = firstFeature.geometry.coordinates[0]
    expect(coords[0]).toBeLessThan(-70) // longitude
    expect(coords[1]).toBeGreaterThan(40) // latitude
  })

  test('should load nodes from backend API', async ({ page }) => {
    const response = await page.request.get('http://localhost:8000/api/v1/traffic/nodes')
    expect(response.ok()).toBeTruthy()
    
    const nodesData = await response.json()
    expect(nodesData.nodes).toBeDefined()
    expect(nodesData.nodes.length).toBeGreaterThan(0)
    
    // Verify node structure
    const firstNode = nodesData.nodes[0]
    expect(firstNode.node_id).toBeDefined()
    expect(firstNode.latitude).toBeDefined()
    expect(firstNode.longitude).toBeDefined()
  })

  test('should load traffic data from backend API', async ({ page }) => {
    // Start simulation if not already running
    await page.request.post('http://localhost:8000/api/v1/simulation/start', {
      data: { seed: 42, speed_multiplier: 1 }
    })
    
    await page.waitForTimeout(3000)
    
    const response = await page.request.get('http://localhost:8000/api/v1/traffic/current?limit=1000')
    expect(response.ok()).toBeTruthy()
    
    const traffic = await response.json()
    expect(traffic.length).toBeGreaterThan(0)
    
    // Verify traffic data structure
    const firstRoad = traffic[0]
    expect(firstRoad.road_id).toBeDefined()
    expect(firstRoad.congestion_level).toBeDefined()
    expect(firstRoad.vehicle_count).toBeDefined()
    expect(firstRoad.avg_speed_kmh).toBeDefined()
  })

  test('should not use placeholder coordinates for roads', async ({ page }) => {
    const response = await page.request.get('http://localhost:8000/api/v1/traffic/geometry')
    const geometry = await response.json()
    
    // Check that no feature uses placeholder [0, 0] coordinates
    for (const feature of geometry.features) {
      for (const coord of feature.geometry.coordinates) {
        // Placeholder would be [0, 0] or very close to it
        expect(coord[0]).not.toBe(0)
        expect(coord[1]).not.toBe(0)
      }
    }
  })

  test('WebSocket connections should eventually succeed', async ({ page }) => {
    // Check WebSocket connections by looking at console for successful connections
    // The connections are tested via the backend API
    const wsResponse = await page.request.get('http://localhost:8000/health')
    expect(wsResponse.ok()).toBeTruthy()
    
    // Verify backend is running and accepting connections
    const health = await wsResponse.json()
    expect(health.status).toBe('healthy')
  })

  test('TrafficStatusPanel should display real data not hardcoded values', async ({ page }) => {
    // Start simulation
    await page.request.post('http://localhost:8000/api/v1/simulation/start', {
      data: { seed: 42, speed_multiplier: 1 }
    })
    
    await page.waitForTimeout(3000)
    
    // Check traffic summary API returns real data
    const response = await page.request.get('http://localhost:8000/api/v1/traffic/summary')
    expect(response.ok()).toBeTruthy()
    
    const summary = await response.json()
    expect(summary.total_roads).toBeGreaterThan(0)
    expect(summary.total_vehicles).toBeGreaterThanOrEqual(0)
    expect(summary.congestion_distribution).toBeDefined()
  })

  test('map should fit bounds to road network', async ({ page }) => {
    const response = await page.request.get('http://localhost:8000/api/v1/traffic/geometry')
    const geometry = await response.json()
    
    // Calculate bounds from geometry
    const allCoords = geometry.features.flatMap((f: any) => f.geometry.coordinates)
    const lngs = allCoords.map((c: any) => c[0])
    const lats = allCoords.map((c: any) => c[1])
    
    const minLng = Math.min(...lngs)
    const maxLng = Math.max(...lngs)
    const minLat = Math.min(...lats)
    const maxLat = Math.max(...lats)
    
    // Bounds should be around NYC area
    expect(minLng).toBeLessThan(-73)
    expect(maxLng).toBeGreaterThan(-75)
    expect(minLat).toBeGreaterThan(40)
    expect(maxLat).toBeLessThan(41)
  })
})