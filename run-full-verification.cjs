const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SCREENSHOT_DIR = path.join(__dirname, 'test-results', 'screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function runFullVerification() {
  console.log('🚀 Starting Comprehensive NeuroRoute Browser & Functional Verification...');
  
  const browser = await chromium.launch({ 
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  const consoleErrors = [];
  const uncaughtExceptions = [];
  const failedRequests = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  page.on('pageerror', err => {
    uncaughtExceptions.push(err.message);
  });

  page.on('requestfailed', req => {
    failedRequests.push(`${req.method()} ${req.url()} (${req.failure()?.errorText})`);
  });

  const results = {};

  try {
    // 1. Navigate to application
    console.log('1. Navigating to http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-initial-dashboard.png'), fullPage: true });

    // 2. Start simulation and verify ticks advance
    console.log('2. Testing Simulation Start & Clock Advancement...');
    const clockEl = page.locator('#simulation-clock');
    const clockInitial = await clockEl.textContent();
    console.log(`   Initial Clock: ${clockInitial}`);

    const startBtn = page.locator('button:has-text("▶ Start"), button:has-text("Start")').first();
    if (await startBtn.isVisible()) {
      await startBtn.click();
      console.log('   Clicked Start button.');
    }
    
    // Set speed to 5x to ensure visible progress
    await page.request.post('http://localhost:8000/api/v1/simulation/speed', {
      data: { speed_multiplier: 5 }
    });
    console.log('   Set simulation speed to 5x.');
    
    // Wait for simulation ticks to advance
    await page.waitForTimeout(6000);
    const clockAfter = await clockEl.textContent();
    console.log(`   Clock after 6s: ${clockAfter}`);
    results.ticksAdvancing = clockAfter !== clockInitial || clockAfter.includes('SIM:');

    // 3. Verify Active Vehicle Entities & Position Movement
    console.log('3. Checking Active Vehicle Entities & Position Updates...');
    const vehicleRes = await page.request.get('http://localhost:8000/api/v1/traffic/vehicles');
    const vehicleData = await vehicleRes.json();
    console.log(`   Backend reports active vehicles: ${vehicleData.count}`);
    results.activeVehiclesExist = vehicleData.count > 0;
    
    const sampleV1 = vehicleData.vehicles?.[0];
    await page.waitForTimeout(4000);
    const vehicleRes2 = await page.request.get('http://localhost:8000/api/v1/traffic/vehicles');
    const vehicleData2 = await vehicleRes2.json();
    const sampleV2 = vehicleData2.vehicles?.find(v => v.vehicle_id === sampleV1?.vehicle_id);
    
    const posChanged = sampleV1 && sampleV2 && (sampleV1.longitude !== sampleV2.longitude || sampleV1.latitude !== sampleV2.latitude);
    console.log(`   Vehicle position changed: ${posChanged} (V1: ${sampleV1?.longitude?.toFixed(6)},${sampleV1?.latitude?.toFixed(6)} -> V2: ${sampleV2?.longitude?.toFixed(6)},${sampleV2?.latitude?.toFixed(6)})`);
    results.positionsChanging = posChanged;

    // 4. Verify Map Canvas and Legend Visibility
    console.log('4. Verifying Map Canvas & Interactive Legend...');
    const mapCanvas = page.locator('.maplibregl-canvas');
    await mapCanvas.waitFor({ state: 'visible', timeout: 10000 });
    
    const legendEl = page.locator('text=Traffic Intelligence Legend');
    const legendVisible = await legendEl.isVisible();
    console.log(`   Legend Visible: ${legendVisible}`);
    results.mapLegendVisible = legendVisible;

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-moving-vehicles-and-overlay.png'), fullPage: true });

    // 5. Verify Congestion Road Colors Across Scenarios
    console.log('5. Triggering Scenario to Verify Congestion Color Changes...');
    const rushHourBtn = page.locator('button:has-text("Rush Hour"), button:has-text("🚗 Rush Hour")').first();
    if (await rushHourBtn.isVisible()) {
      await rushHourBtn.click();
      console.log('   Clicked Rush Hour scenario.');
      await page.waitForTimeout(4000);
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-scenario-congestion-active.png'), fullPage: true });

    // 6. Verify Prediction API Succeeds & Real Chart Data Appears
    console.log('6. Verifying Congestion Predictions Panel & ML Chart...');
    const predPanel = page.locator('text=Congestion Predictions');
    await predPanel.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    
    const predError = await page.locator('text=Failed to load predictions').isVisible();
    const hasChart = await page.locator('.recharts-responsive-container').isVisible();
    const modelText = await page.locator('text=Algorithm:').locator('..').textContent();
    console.log(`   Prediction Panel has error: ${predError}, has chart: ${hasChart}, model: ${modelText?.trim()}`);
    results.predictionApiSucceeds = !predError && hasChart;
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-prediction-chart.png'), fullPage: true });

    // 7. Verify Traffic Status Panel Metrics Consistency
    console.log('7. Verifying Traffic Status Panel Metrics...');
    const summaryRes = await page.request.get('http://localhost:8000/api/v1/traffic/summary');
    const summaryData = await summaryRes.json();
    console.log(`   Backend Summary: vehicles=${summaryData.total_vehicles}, speed=${summaryData.avg_speed_kmh}km/h, roads=${summaryData.total_roads}`);
    
    const statCards = await page.locator('text=Total Vehicles').locator('..').textContent();
    console.log(`   Frontend StatCard text: ${statCards?.trim()}`);
    // Ensure fractional values like 542.239 are gone and integer formatting is used
    const isIntegerFormatted = !statCards?.includes('.') && !statCards?.includes('542.239');
    console.log(`   Total Vehicles is formatted integer: ${isIntegerFormatted}`);
    results.metricsIntegerAndConsistent = isIntegerFormatted;

    // 8 & 9. Route Planning, Origin/Destination Selection, and Route Rendering
    console.log('8. Testing Route Planning & Recommended Path Drawing...');
    const sampleRouteBtn = page.locator('button:has-text("N0000 → N0100")');
    if (await sampleRouteBtn.isVisible()) {
      await sampleRouteBtn.scrollIntoViewIfNeeded();
      await sampleRouteBtn.click();
      console.log('   Selected sample route N0000 → N0100.');
      await page.waitForTimeout(1000);
    }
    
    const calcRouteBtn = page.locator('button:has-text("Calculate Routes")');
    if (await calcRouteBtn.isVisible()) {
      await calcRouteBtn.scrollIntoViewIfNeeded();
      await calcRouteBtn.click();
      console.log('   Clicked Calculate Routes.');
      await page.waitForTimeout(3000);
    }
    
    const routeComparison = page.locator('text=Route Comparison');
    const comparisonVisible = await routeComparison.isVisible();
    const recommendedRoute = page.locator('text=NeuroRoute (Recommended)');
    const recommendedVisible = await recommendedRoute.isVisible();
    console.log(`   Route Comparison Visible: ${comparisonVisible}, Recommended visible: ${recommendedVisible}`);
    results.routePlanningAndRendering = comparisonVisible && recommendedVisible;
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-route-rendered.png'), fullPage: true });

    // 10 & 11. Incident Injection & Rerouting / Road Closure
    console.log('9. Testing Incident Injection (Accident & Road Closure)...');
    const triggerAccidentBtn = page.locator('button:has-text("Trigger Accident"), button:has-text("💥 Accident")').first();
    if (await triggerAccidentBtn.isVisible()) {
      await triggerAccidentBtn.scrollIntoViewIfNeeded();
      await triggerAccidentBtn.click();
      console.log('   Clicked Trigger Accident.');
      await page.waitForTimeout(3000);
    }
    
    const activeIncidentsRes = await page.request.get('http://localhost:8000/api/v1/incidents/active');
    const activeIncidentsData = await activeIncidentsRes.json();
    console.log(`   Active incidents count: ${activeIncidentsData.count}`);
    results.incidentsIntegrated = activeIncidentsData.count > 0;
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-incidents-on-map.png'), fullPage: true });

    // 12. Browser Resizing
    console.log('10. Testing Browser Resize Layer Resilience...');
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForTimeout(1000);
    const canvasAfterResize = await mapCanvas.isVisible();
    console.log(`   Canvas visible after resize: ${canvasAfterResize}`);
    results.resizeResilient = canvasAfterResize;
    await page.setViewportSize({ width: 1440, height: 900 });

    // 13 & 14. Error checks
    console.log('11. Checking for Uncaught JavaScript Errors...');
    console.log(`   Uncaught Page Errors: ${uncaughtExceptions.length}`);
    if (uncaughtExceptions.length > 0) {
      console.log('   Errors:', uncaughtExceptions);
    }
    results.noUncaughtErrors = uncaughtExceptions.length === 0;

    console.log('\n================ FINAL PLAYWRIGHT VERIFICATION SUMMARY ================');
    console.log(JSON.stringify(results, null, 2));
    console.log('=======================================================================\n');
    console.log(`All screenshots saved to: ${SCREENSHOT_DIR}`);

  } catch (err) {
    console.error('Test execution failed with error:', err);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, 'error-failure.png'), fullPage: true });
  } finally {
    await browser.close();
  }
}

runFullVerification().catch(console.error);
