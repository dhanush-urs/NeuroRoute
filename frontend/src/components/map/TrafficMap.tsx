import { useEffect, useRef, useMemo, useState } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { VehicleItem } from '../../hooks'

interface TrafficMapProps {
  onNodeClick: (nodeId: string) => void
  selectedOrigin: string | null
  selectedDestination: string | null
  traffic: Map<string, any>
  vehicles?: VehicleItem[]
  incidents?: any[]
  activeRoute?: any | null
}

interface RoadGeometryFeature {
  type: 'Feature'
  properties: {
    road_id: string
    road_type: string
    source_node: string
    target_node: string
  }
  geometry: {
    type: 'LineString'
    coordinates: [number, number][]
  }
}

interface RoadGeometryResponse {
  type: 'FeatureCollection'
  features: RoadGeometryFeature[]
}

interface NodeData {
  node_id: string
  latitude: number
  longitude: number
  node_type: string
}

// Minimal MapLibre style using OSM tiles - no external style dependency
const MINIMAL_STYLE = {
  version: 8,
  sources: {
    'osm': {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: {
        'background-color': '#f5f5f0',
      },
    },
    {
      id: 'osm-tiles',
      type: 'raster',
      source: 'osm',
      minzoom: 0,
      maxzoom: 19,
    },
  ],
} as const

export function TrafficMap({ 
  onNodeClick, 
  selectedOrigin, 
  selectedDestination, 
  traffic,
  vehicles = [],
  incidents = [],
  activeRoute = null,
}: TrafficMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [roadGeometry, setRoadGeometry] = useState<RoadGeometryFeature[]>([])
  const [nodes, setNodes] = useState<NodeData[]>([])
  const [geometryLoaded, setGeometryLoaded] = useState(false)
  const [geometryError, setGeometryError] = useState<string | null>(null)
  const [bounds, setBounds] = useState<maplibregl.LngLatBoundsLike | null>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  const onNodeClickRef = useRef(onNodeClick)
  useEffect(() => {
    onNodeClickRef.current = onNodeClick
  }, [onNodeClick])

  // Track animated vehicle positions
  const vehicleAnimPositions = useRef<Map<string, {
    currentLng: number
    currentLat: number
    targetLng: number
    targetLat: number
    bearing: number
    speed: number
    state: string
  }>>(new Map())
  const animFrameRef = useRef<number | null>(null)

  // Fetch road geometry and nodes on mount
  useEffect(() => {
    let cancelled = false

    const fetchRoadData = async () => {
      try {
        const [geometryRes, nodesRes] = await Promise.all([
          fetch('/api/v1/traffic/geometry'),
          fetch('/api/v1/traffic/nodes')
        ])

        if (!geometryRes.ok) {
          throw new Error(`Geometry fetch failed: ${geometryRes.status}`)
        }
        if (!nodesRes.ok) {
          throw new Error(`Nodes fetch failed: ${nodesRes.status}`)
        }

        const geometryData: RoadGeometryResponse = await geometryRes.json()
        const nodesData = await nodesRes.json()

        if (cancelled) return

        setRoadGeometry(geometryData.features || [])
        setNodes(nodesData.nodes || [])
        setGeometryLoaded(true)

        // Calculate bounds from road geometry
        if (geometryData.features && geometryData.features.length > 0) {
          const allCoords = geometryData.features.flatMap(f => f.geometry.coordinates)
          const lngs = allCoords.map(c => c[0])
          const lats = allCoords.map(c => c[1])
          const minLng = Math.min(...lngs)
          const maxLng = Math.max(...lngs)
          const minLat = Math.min(...lats)
          const maxLat = Math.max(...lats)
          setBounds([[minLng, minLat], [maxLng, maxLat]] as maplibregl.LngLatBoundsLike)
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to fetch road data:', error)
          setGeometryError(error instanceof Error ? error.message : 'Unknown error')
          setGeometryLoaded(true)
        }
      }
    }

    fetchRoadData()

    return () => {
      cancelled = true
    }
  }, [])

  // Map of road geometries by road_id for quick lookups
  const geometryMap = useMemo(() => {
    return new Map(roadGeometry.map(g => [g.properties.road_id, g]))
  }, [roadGeometry])

  // Map of node coordinates by node_id for quick lookups
  const nodeCoordsMap = useMemo(() => {
    return new Map(nodes.map(n => [n.node_id, [n.longitude, n.latitude] as [number, number]]))
  }, [nodes])

  // Convert ALL road geometries to GeoJSON features with real-time congestion levels
  const roadFeatures = useMemo(() => {
    const features: any[] = []

    roadGeometry.forEach((road) => {
      const roadId = road.properties.road_id
      const data = traffic.get(roadId)

      features.push({
        type: 'Feature',
        properties: {
          road_id: roadId,
          congestion_level: data?.congestion_level || 'free',
          vehicle_count: data?.vehicle_count || 0,
          avg_speed_kmh: data?.avg_speed_kmh || 0,
          congestion_score: data?.congestion_score || 0,
        },
        geometry: road.geometry,
      })
    })

    return { type: 'FeatureCollection', features }
  }, [traffic, roadGeometry])

  // Convert nodes to GeoJSON
  const nodeFeatures = useMemo(() => {
    const features: any[] = []
    nodes.forEach(node => {
      features.push({
        type: 'Feature',
        properties: {
          node_id: node.node_id,
          node_type: node.node_type,
        },
        geometry: {
          type: 'Point',
          coordinates: [node.longitude, node.latitude],
        },
      })
    })
    return { type: 'FeatureCollection', features }
  }, [nodes])

  // Convert incidents to GeoJSON features placed at the midpoint of affected roads
  const incidentFeatures = useMemo(() => {
    const features: any[] = []
    const incList = Array.isArray(incidents) ? incidents : []

    incList.forEach((inc) => {
      const roadGeom = geometryMap.get(inc.road_id)
      if (roadGeom && roadGeom.geometry.coordinates.length > 0) {
        const coords = roadGeom.geometry.coordinates
        const midIdx = Math.floor(coords.length / 2)
        const point = coords[midIdx]

        features.push({
          type: 'Feature',
          properties: {
            incident_id: inc.incident_id,
            incident_type: inc.incident_type || inc.type,
            road_id: inc.road_id,
            severity: inc.severity,
            description: inc.description || 'Traffic Incident',
            capacity_reduction_pct: inc.capacity_reduction_pct,
          },
          geometry: {
            type: 'Point',
            coordinates: point,
          },
        })
      }
    })

    return { type: 'FeatureCollection', features }
  }, [incidents, geometryMap])

  // Convert active route to GeoJSON line feature
  const routeFeatures = useMemo(() => {
    const features: any[] = []

    if (activeRoute && Array.isArray(activeRoute.nodes) && activeRoute.nodes.length >= 2) {
      let coordinates: [number, number][] = []

      // If activeRoute has edges, stitch their geometry coordinates to follow curved roads
      if (Array.isArray(activeRoute.edges) && activeRoute.edges.length > 0) {
        activeRoute.edges.forEach((edgeId: string, idx: number) => {
          const edgeGeom = geometryMap.get(edgeId)
          if (edgeGeom && Array.isArray(edgeGeom.geometry?.coordinates)) {
            const edgeCoords = edgeGeom.geometry.coordinates as [number, number][]
            if (idx === 0) {
              coordinates.push(...edgeCoords)
            } else if (edgeCoords.length > 0) {
              // Avoid duplicate junction coordinate
              coordinates.push(...edgeCoords.slice(1))
            }
          }
        })
      }

      // Fallback to nodes if edges didn't yield enough coordinates
      if (coordinates.length < 2) {
        coordinates = []
        activeRoute.nodes.forEach((nodeId: string) => {
          const coords = nodeCoordsMap.get(nodeId)
          if (coords) {
            coordinates.push(coords)
          }
        })
      }

      if (coordinates.length >= 2) {
        features.push({
          type: 'Feature',
          properties: {
            algorithm: activeRoute.algorithm || 'route',
            distance_km: activeRoute.distance_km,
            current_eta_sec: activeRoute.current_eta_sec,
          },
          geometry: {
            type: 'LineString',
            coordinates,
          },
        })
      }
    }

    return { type: 'FeatureCollection', features }
  }, [activeRoute, nodeCoordsMap, geometryMap])

  // Keep references to latest features so map load handler can use them immediately
  const roadFeaturesRef = useRef(roadFeatures)
  roadFeaturesRef.current = roadFeatures

  const nodeFeaturesRef = useRef(nodeFeatures)
  nodeFeaturesRef.current = nodeFeatures

  const incidentFeaturesRef = useRef(incidentFeatures)
  incidentFeaturesRef.current = incidentFeatures

  const routeFeaturesRef = useRef(routeFeatures)
  routeFeaturesRef.current = routeFeatures

  // Initialize Map
  useEffect(() => {
    if (!mapContainer.current || map.current) return

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: MINIMAL_STYLE as unknown as maplibregl.StyleSpecification,
      center: [-74.01, 40.71], // New York / synthetic city center
      zoom: 13,
      pitch: 0,
      bearing: 0,
    })

    map.current.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right')

    // Handle window resizing safely
    const handleResize = () => {
      map.current?.resize()
    }
    window.addEventListener('resize', handleResize)

    map.current.on('load', () => {
      if (!map.current) return

      // 1. Road network source and layers
      map.current.addSource('roads', {
        type: 'geojson',
        data: roadFeaturesRef.current as any,
      })

      // Roads casing for contrast
      map.current.addLayer({
        id: 'roads-casing',
        type: 'line',
        source: 'roads',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': '#ffffff',
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            10, 3,
            13, 5.5,
            15, 7.5,
            18, 11,
          ],
          'line-opacity': 0.7,
        },
      })

      // Colored congestion overlay
      map.current.addLayer({
        id: 'roads-layer',
        type: 'line',
        source: 'roads',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': [
            'match',
            ['get', 'congestion_level'],
            'free', '#22c55e',       // green
            'moderate', '#eab308',   // yellow
            'heavy', '#f97316',      // orange
            'congested', '#ef4444',  // red
            'severe', '#991b1b',     // dark red
            'closed', '#374151',     // dark grey
            '#22c55e',
          ],
          'line-width': [
            'interpolate',
            ['linear'],
            ['zoom'],
            10, 2,
            13, 3.5,
            15, 5,
            18, 8,
          ],
          'line-opacity': 0.9,
        },
      })

      // 2. Active Route layers (rendered above roads)
      map.current.addSource('routes', {
        type: 'geojson',
        data: routeFeaturesRef.current as any,
      })

      map.current.addLayer({
        id: 'route-casing',
        type: 'line',
        source: 'routes',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': '#0f172a',
          'line-width': 8,
          'line-opacity': 0.5,
        },
      })

      map.current.addLayer({
        id: 'route-layer',
        type: 'line',
        source: 'routes',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': '#0284c7',
          'line-width': 5,
          'line-opacity': 0.95,
        },
      })

      // 3. Vehicles source and layers
      map.current.addSource('vehicles', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      map.current.addLayer({
        id: 'vehicles-glow',
        type: 'circle',
        source: 'vehicles',
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            10, 4,
            13, 7,
            16, 11,
          ],
          'circle-color': '#38bdf8',
          'circle-opacity': 0.4,
          'circle-blur': 0.4,
        },
      })

      map.current.addLayer({
        id: 'vehicles-layer',
        type: 'circle',
        source: 'vehicles',
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            10, 2.5,
            13, 4.5,
            16, 7,
          ],
          'circle-color': [
            'match',
            ['get', 'state'],
            'slowing', '#f59e0b',
            'stopped', '#ef4444',
            '#0284c7',
          ],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': 1.0,
        },
      })

      // 4. Incidents source and layers
      map.current.addSource('incidents', {
        type: 'geojson',
        data: incidentFeaturesRef.current as any,
      })

      map.current.addLayer({
        id: 'incidents-glow',
        type: 'circle',
        source: 'incidents',
        paint: {
          'circle-radius': 14,
          'circle-color': '#ef4444',
          'circle-opacity': 0.35,
          'circle-blur': 0.3,
        },
      })

      map.current.addLayer({
        id: 'incidents-layer',
        type: 'circle',
        source: 'incidents',
        paint: {
          'circle-radius': 7,
          'circle-color': '#b91c1c',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
        },
      })

      // 5. Nodes source and layers
      map.current.addSource('nodes', {
        type: 'geojson',
        data: nodeFeaturesRef.current as any,
      })

      map.current.addLayer({
        id: 'nodes-layer',
        type: 'circle',
        source: 'nodes',
        minzoom: 13.5,
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            13.5, 2.5,
            15, 4.5,
            17, 7,
          ],
          'circle-color': '#0284c7',
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': 0.7,
        },
      })

      // 6. Selected Origin & Destination layers
      map.current.addSource('selected-origin', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      map.current.addLayer({
        id: 'selected-origin-pulse',
        type: 'circle',
        source: 'selected-origin',
        paint: {
          'circle-radius': 18,
          'circle-color': '#22c55e',
          'circle-opacity': 0.35,
          'circle-blur': 0.3,
        },
      })

      map.current.addLayer({
        id: 'selected-origin-layer',
        type: 'circle',
        source: 'selected-origin',
        paint: {
          'circle-radius': 9,
          'circle-color': '#16a34a',
          'circle-stroke-width': 3,
          'circle-stroke-color': '#ffffff',
        },
      })

      map.current.addSource('selected-destination', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      map.current.addLayer({
        id: 'selected-destination-pulse',
        type: 'circle',
        source: 'selected-destination',
        paint: {
          'circle-radius': 18,
          'circle-color': '#ef4444',
          'circle-opacity': 0.35,
          'circle-blur': 0.3,
        },
      })

      map.current.addLayer({
        id: 'selected-destination-layer',
        type: 'circle',
        source: 'selected-destination',
        paint: {
          'circle-radius': 9,
          'circle-color': '#dc2626',
          'circle-stroke-width': 3,
          'circle-stroke-color': '#ffffff',
        },
      })

      // Fit map to bounds if available
      if (bounds) {
        try {
          map.current.fitBounds(bounds, { padding: 40, maxZoom: 15 })
        } catch (e) {
          console.warn('Failed to fit bounds:', e)
        }
      }
    })

    // Click handler for nodes
    map.current.on('click', 'nodes-layer', (e) => {
      if (e.features && e.features.length > 0) {
        const nodeId = e.features[0].properties?.node_id
        if (nodeId) {
          onNodeClickRef.current?.(nodeId)
        }
      }
    })

    // Pointer hover states for nodes
    map.current.on('mouseenter', 'nodes-layer', (e) => {
      if (!map.current) return
      map.current.getCanvas().style.cursor = 'pointer'
      const nodeId = e.features?.[0]?.properties?.node_id
      if (nodeId) setHoveredNode(nodeId)
    })

    map.current.on('mouseleave', 'nodes-layer', () => {
      if (!map.current) return
      map.current.getCanvas().style.cursor = ''
      setHoveredNode(null)
    })

    // Hover tooltip for incidents
    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 10,
    })

    map.current.on('mouseenter', 'incidents-layer', (e) => {
      if (!map.current || !e.features || !e.features[0]) return
      map.current.getCanvas().style.cursor = 'pointer'
      const props = e.features[0].properties
      const coordinates = (e.features[0].geometry as any).coordinates.slice()

      popup
        .setLngLat(coordinates)
        .setHTML(`
          <div style="font-family: sans-serif; font-size: 12px; padding: 4px;">
            <div style="font-weight: bold; color: #b91c1c; text-transform: uppercase;">⚠️ ${props?.incident_type}</div>
            <div>${props?.description || 'Active incident'}</div>
            <div style="color: #64748b; font-size: 10px; margin-top: 2px;">
              Road: ${props?.road_id?.slice(0, 8)}... | Capacity: -${props?.capacity_reduction_pct}%
            </div>
          </div>
        `)
        .addTo(map.current)
    })

    map.current.on('mouseleave', 'incidents-layer', () => {
      if (!map.current) return
      map.current.getCanvas().style.cursor = ''
      popup.remove()
    })

    // Hover tooltip for roads (Phase 4 road inspection)
    map.current.on('mouseenter', 'roads-layer', (e) => {
      if (!map.current || !e.features || !e.features[0]) return
      map.current.getCanvas().style.cursor = 'pointer'
      const props = e.features[0].properties
      popup
        .setLngLat(e.lngLat)
        .setHTML(`
          <div style="font-family: sans-serif; font-size: 12px; padding: 4px;">
            <div style="font-weight: bold; color: #0f172a;">🛣️ Road Segment</div>
            <div style="font-family: monospace; font-size: 11px; color: #475569;">ID: ${props?.road_id?.slice(0, 12)}...</div>
            <div style="margin-top: 4px;">Congestion: <strong style="text-transform: uppercase;">${props?.congestion_level}</strong></div>
            <div>Speed: ${props?.avg_speed_kmh} km/h</div>
            <div>Vehicles: ${props?.vehicle_count}</div>
          </div>
        `)
        .addTo(map.current)
    })

    map.current.on('mouseleave', 'roads-layer', () => {
      if (!map.current) return
      map.current.getCanvas().style.cursor = ''
      popup.remove()
    })

    // Hover tooltip for vehicles (Phase 4 vehicle inspection)
    map.current.on('mouseenter', 'vehicles-layer', (e) => {
      if (!map.current || !e.features || !e.features[0]) return
      map.current.getCanvas().style.cursor = 'pointer'
      const props = e.features[0].properties
      const coordinates = (e.features[0].geometry as any).coordinates.slice()
      popup
        .setLngLat(coordinates)
        .setHTML(`
          <div style="font-family: sans-serif; font-size: 12px; padding: 4px;">
            <div style="font-weight: bold; color: #0284c7;">🚗 Vehicle ${props?.vehicle_id}</div>
            <div>Speed: ${props?.speed} km/h</div>
            <div>Status: ${props?.state}</div>
            <div>Bearing: ${props?.bearing}°</div>
          </div>
        `)
        .addTo(map.current)
    })

    map.current.on('mouseleave', 'vehicles-layer', () => {
      if (!map.current) return
      map.current.getCanvas().style.cursor = ''
      popup.remove()
    })

    return () => {
      window.removeEventListener('resize', handleResize)
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current)
      }
      map.current?.remove()
      map.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Initialize map only once on mount!

  // Fit bounds when bounds change without re-initializing the map
  useEffect(() => {
    if (!map.current || !bounds) return
    try {
      map.current.fitBounds(bounds, { padding: 40, maxZoom: 15, duration: 1000 })
    } catch (e) {
      console.warn('Failed to fit bounds:', e)
    }
  }, [bounds])

  // Update roads layer
  useEffect(() => {
    if (!map.current || !map.current.getSource('roads')) return
    const source = map.current.getSource('roads') as maplibregl.GeoJSONSource
    if (source && source.setData) {
      source.setData(roadFeatures as GeoJSON.FeatureCollection)
    }
  }, [roadFeatures])

  // Update nodes layer
  useEffect(() => {
    if (!map.current || !map.current.getSource('nodes')) return
    const source = map.current.getSource('nodes') as maplibregl.GeoJSONSource
    if (source && source.setData) {
      source.setData(nodeFeatures as GeoJSON.FeatureCollection)
    }
  }, [nodeFeatures])

  // Update incidents layer
  useEffect(() => {
    if (!map.current || !map.current.getSource('incidents')) return
    const source = map.current.getSource('incidents') as maplibregl.GeoJSONSource
    if (source && source.setData) {
      source.setData(incidentFeatures as GeoJSON.FeatureCollection)
    }
  }, [incidentFeatures])

  // Update active route layer
  useEffect(() => {
    if (!map.current || !map.current.getSource('routes')) return
    const source = map.current.getSource('routes') as maplibregl.GeoJSONSource
    if (source && source.setData) {
      source.setData(routeFeatures as GeoJSON.FeatureCollection)
    }
  }, [routeFeatures])

  // Smooth vehicle animation loop
  useEffect(() => {
    if (!vehicles || vehicles.length === 0) {
      if (map.current && map.current.getSource('vehicles')) {
        const source = map.current.getSource('vehicles') as maplibregl.GeoJSONSource
        source.setData({ type: 'FeatureCollection', features: [] })
      }
      vehicleAnimPositions.current.clear()
      return
    }

    const currentMap = vehicleAnimPositions.current
    const activeIds = new Set<string>()

    // Update targets
    vehicles.forEach((v) => {
      activeIds.add(v.vehicle_id)
      const existing = currentMap.get(v.vehicle_id)

      if (existing) {
        existing.targetLng = v.longitude
        existing.targetLat = v.latitude
        existing.bearing = v.bearing
        existing.speed = v.speed
        existing.state = v.state
      } else {
        currentMap.set(v.vehicle_id, {
          currentLng: v.longitude,
          currentLat: v.latitude,
          targetLng: v.longitude,
          targetLat: v.latitude,
          bearing: v.bearing,
          speed: v.speed,
          state: v.state,
        })
      }
    })

    // Remove exited vehicles
    for (const id of Array.from(currentMap.keys())) {
      if (!activeIds.has(id)) {
        currentMap.delete(id)
      }
    }

    // Smooth animation step throttled to ~30 FPS
    let isCancelled = false
    let lastRenderTime = 0

    const step = (timestamp: number) => {
      if (isCancelled || !map.current) return

      if (timestamp - lastRenderTime >= 33) {
        lastRenderTime = timestamp

        const features: any[] = []

        currentMap.forEach((v, id) => {
          // Interpolate smoothly: 25% of remaining distance per 30fps frame
          const deltaLng = v.targetLng - v.currentLng
          const deltaLat = v.targetLat - v.currentLat

          if (Math.abs(deltaLng) > 0.000001 || Math.abs(deltaLat) > 0.000001) {
            v.currentLng += deltaLng * 0.25
            v.currentLat += deltaLat * 0.25
          } else {
            v.currentLng = v.targetLng
            v.currentLat = v.targetLat
          }

          features.push({
            type: 'Feature',
            properties: {
              vehicle_id: id,
              speed: v.speed,
              state: v.state,
              bearing: v.bearing,
            },
            geometry: {
              type: 'Point',
              coordinates: [v.currentLng, v.currentLat],
            },
          })
        })

        const source = map.current.getSource('vehicles') as maplibregl.GeoJSONSource
        if (source && source.setData) {
          source.setData({
            type: 'FeatureCollection',
            features,
          })
        }
      }

      animFrameRef.current = requestAnimationFrame(step)
    }

    animFrameRef.current = requestAnimationFrame(step)

    return () => {
      isCancelled = true
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current)
      }
    }
  }, [vehicles])

  // Update selected origin/destination
  useEffect(() => {
    if (!map.current) return

    const originSource = map.current.getSource('selected-origin') as maplibregl.GeoJSONSource
    if (originSource) {
      if (selectedOrigin) {
        const coords = nodeCoordsMap.get(selectedOrigin)
        if (coords) {
          originSource.setData({
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              properties: { node_id: selectedOrigin },
              geometry: {
                type: 'Point',
                coordinates: coords,
              },
            }]
          })
        }
      } else {
        originSource.setData({ type: 'FeatureCollection', features: [] })
      }
    }

    const destSource = map.current.getSource('selected-destination') as maplibregl.GeoJSONSource
    if (destSource) {
      if (selectedDestination) {
        const coords = nodeCoordsMap.get(selectedDestination)
        if (coords) {
          destSource.setData({
            type: 'FeatureCollection',
            features: [{
              type: 'Feature',
              properties: { node_id: selectedDestination },
              geometry: {
                type: 'Point',
                coordinates: coords,
              },
            }]
          })
        }
      } else {
        destSource.setData({ type: 'FeatureCollection', features: [] })
      }
    }
  }, [selectedOrigin, selectedDestination, nodeCoordsMap])

  return (
    <div className="relative w-full h-full" style={{ width: '100%', height: '100%' }}>
      <div
        ref={mapContainer}
        className="w-full h-full"
        style={{ width: '100%', height: '100%' }}
      />

      {/* Loading Overlay */}
      {!geometryLoaded && !geometryError && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-100/90 backdrop-blur-xs z-20 pointer-events-none">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500 mx-auto"></div>
            <p className="mt-2 text-slate-600 font-medium">Loading road network...</p>
          </div>
        </div>
      )}

      {/* Error Overlay */}
      {geometryError && (
        <div className="absolute inset-0 flex items-center justify-center bg-red-50/95 z-20 p-4">
          <div className="text-center p-4">
            <p className="text-red-600 font-medium">Failed to load road network</p>
            <p className="text-sm text-slate-500 mt-1">{geometryError}</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 px-4 py-2 bg-primary-500 text-white rounded hover:bg-primary-600 font-medium pointer-events-auto"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Floating Interactive Map Legend */}
      <div className="absolute bottom-6 left-6 z-10 bg-white/95 backdrop-blur-sm p-3 rounded-xl shadow-lg border border-slate-200 text-xs flex flex-col gap-2 max-w-xs pointer-events-auto">
        <div className="font-semibold text-slate-800 flex items-center justify-between gap-4">
          <span>Traffic Intelligence Legend</span>
          {vehicles.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-sky-100 text-sky-700 font-mono text-[10px]">
              {vehicles.length} active
            </span>
          )}
        </div>

        {/* Congestion Levels */}
        <div className="grid grid-cols-3 gap-x-2 gap-y-1 text-[11px] text-slate-600">
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-[#22c55e]" /> Free
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-[#eab308]" /> Moderate
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-[#f97316]" /> Heavy
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-[#ef4444]" /> Congested
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-[#991b1b]" /> Severe
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-3 h-1.5 rounded-full bg-[#374151]" /> Closed
          </div>
        </div>

        <div className="border-t border-slate-200/60 pt-2 flex items-center justify-between text-[11px] text-slate-600">
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-[#0284c7] border border-white shadow-sm inline-block" />
            <span>Vehicles</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-[#b91c1c] border border-white shadow-sm inline-block" />
            <span>Incident</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-[#16a34a] border border-white shadow-sm inline-block" />
            <span>Origin</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-full bg-[#dc2626] border border-white shadow-sm inline-block" />
            <span>Dest</span>
          </div>
        </div>

        {hoveredNode && (
          <div className="text-[11px] bg-sky-50 text-sky-800 p-1.5 rounded border border-sky-200 text-center font-mono">
            Node: {hoveredNode} (Click to set)
          </div>
        )}
      </div>
    </div>
  )
}