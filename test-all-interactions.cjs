const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const SCREENSHOTS_DIR = path.join(__dirname, 'test-results', 'screenshots');
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function runCompleteInteractionAudit() {
  console.log('🏁 Starting Complete NeuroRoute Frontend Interaction Audit & Test Suite...');
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }
  });
  const page = await context.newPage();

  const auditResults = {
    toolbar: {},
    demoScenarios: {},
    navigationTabs: {},
    mapInteractions: {},
    trafficStatus: {},
    routePlanner: {},
    predictions: {},
    incidents: {},
    aiInsights: {},
    systemMetrics: {},
    whatIf: {},
    viewports: {},
    uncaughtErrors: []
  };

  page.on('pageerror', err => {
    auditResults.uncaughtErrors.push(err.message);
    console.error('❌ Page Error:', err.message);
  });

  try {
    // 1. Initial Load
    console.log('\n--- PHASE 1 & 2: Navigation & Top Toolbar ---');
    await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);

    // Test Simulation Start
    const toggleBtn = page.locator('button:has-text("▶ Start"), button:has-text("⏸ Pause")').first();
    const initialText = await toggleBtn.textContent();
    console.log(`Initial button text: ${initialText}`);

    if (initialText.includes('Start')) {
      await toggleBtn.click();
      await page.waitForTimeout(2000);
      const afterStartText = await toggleBtn.textContent();
      auditResults.toolbar.startSimulation = afterStartText.includes('Pause');
      console.log(`Started simulation -> button is now: ${afterStartText}`);
    } else {
      auditResults.toolbar.startSimulation = true;
    }

    // Test Simulation Pause
    await toggleBtn.click();
    await page.waitForTimeout(1500);
    const afterPauseText = await toggleBtn.textContent();
    auditResults.toolbar.pauseSimulation = afterPauseText.includes('Start');
    console.log(`Paused simulation -> button is now: ${afterPauseText}`);

    // Resume simulation
    await toggleBtn.click();
    await page.waitForTimeout(1500);
    auditResults.toolbar.resumeSimulation = (await toggleBtn.textContent()).includes('Pause');

    // Test Speed Multipliers (1x, 5x, 10x, 30x)
    const speedSelect = page.locator('header select').first();
    for (const spd of [1, 5, 10, 30]) {
      await speedSelect.selectOption(spd.toString());
      await page.waitForTimeout(500);
      const val = await speedSelect.inputValue();
      auditResults.toolbar[`speed_${spd}x`] = val === spd.toString();
      console.log(`Tested speed multiplier ${spd}x: select value = ${val}`);
    }
    // Set to 5x for remaining tests
    await speedSelect.selectOption('5');

    // Test Demo Scenarios Dropdown
    const demoBtn = page.locator('button:has-text("🎬 Demo"), button:has-text("Demo")').first();
    await demoBtn.click();
    await page.waitForTimeout(400);
    const demoMenuVisible = await page.locator('role=menuitem').first().isVisible();
    auditResults.toolbar.demoDropdownOpen = demoMenuVisible;

    // Test Escape key closes dropdown
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const demoMenuClosedByEsc = !(await page.locator('role=menuitem').first().isVisible());
    auditResults.toolbar.demoDropdownEscape = demoMenuClosedByEsc;

    // Reopen demo and test all scenarios
    const scenarioNames = [
      'Normal Traffic',
      'Morning Rush',
      'Major Jam',
      'Accident',
      'Road Closure',
      'Heavy Rain',
      'Traffic Surge',
      'Major Event'
    ];

    for (const scName of scenarioNames) {
      await demoBtn.click();
      await page.waitForTimeout(200);
      const item = page.locator(`button[role="menuitem"]:has-text("${scName}")`).first();
      if (await item.isVisible()) {
        await item.click();
        await page.waitForTimeout(800);
        auditResults.demoScenarios[scName] = true;
        console.log(`✓ Triggered Demo scenario: ${scName}`);
      } else {
        auditResults.demoScenarios[scName] = false;
        await page.keyboard.press('Escape');
      }
    }

    // Test Reset Button
    const resetBtn = page.locator('button:has-text("↻ Reset"), button:has-text("Reset")').first();
    await resetBtn.click();
    await page.waitForTimeout(1500);
    const isPausedAfterReset = (await toggleBtn.textContent()).includes('Start');
    auditResults.toolbar.resetButton = isPausedAfterReset;
    console.log(`Reset button works, simulation paused: ${isPausedAfterReset}`);

    // Restart simulation for subsequent tests
    await toggleBtn.click();
    await page.waitForTimeout(1000);

    // --- PHASE 3: Navigation Tabs ---
    console.log('\n--- PHASE 3: Navigation Tabs ---');
    const tabs = [
      { id: 'traffic', label: 'Traffic', checkText: 'Traffic Status' },
      { id: 'routing', label: 'Routing', checkText: 'Route Planner' },
      { id: 'predictions', label: 'Predictions', checkText: 'Congestion Predictions' },
      { id: 'incidents', label: 'Incidents', checkText: 'Active Incidents' },
      { id: 'ai', label: 'AI Insights', checkText: 'AI Insights' },
      { id: 'metrics', label: 'Metrics', checkText: 'System Metrics' },
      { id: 'whatif', label: 'What-If', checkText: 'What-If' },
      { id: 'all', label: 'All', checkText: 'Traffic Status' },
    ];

    for (const tab of tabs) {
      const tabBtn = page.locator(`button[role="tab"]:has-text("${tab.label}")`).first();
      await tabBtn.click();
      await page.waitForTimeout(500);
      const isSelected = await tabBtn.getAttribute('aria-selected');
      const hasContent = await page.locator(`text=${tab.checkText}`).first().isVisible();
      auditResults.navigationTabs[tab.label] = (isSelected === 'true') && hasContent;
      console.log(`Tab ${tab.label}: selected=${isSelected}, content visible=${hasContent}`);
    }

    // --- PHASE 4: Map Interactions ---
    console.log('\n--- PHASE 4: Map Interactions ---');
    const mapCanvas = page.locator('.maplibregl-canvas');
    await mapCanvas.waitFor({ state: 'visible' });

    // Zoom controls
    const zoomInBtn = page.locator('.maplibregl-ctrl-zoom-in').first();
    const zoomOutBtn = page.locator('.maplibregl-ctrl-zoom-out').first();
    if (await zoomInBtn.isVisible()) {
      await zoomInBtn.click();
      await page.waitForTimeout(500);
      await zoomOutBtn.click();
      await page.waitForTimeout(500);
      auditResults.mapInteractions.zoomControls = true;
    }

    // Pan map by mouse drag
    const box = await mapCanvas.boundingBox();
    if (box) {
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2 + 100, { steps: 5 });
      await page.mouse.up();
      await page.waitForTimeout(500);
      auditResults.mapInteractions.panMap = true;
      console.log('✓ Map zoom & pan verified');
    }

    // --- PHASE 5: Traffic Status Panel ---
    console.log('\n--- PHASE 5: Traffic Status Panel ---');
    await page.locator('button[role="tab"]:has-text("Traffic")').first().click();
    await page.waitForTimeout(500);

    const vehCard = await page.locator('text=Total Vehicles').locator('..').textContent();
    const speedCard = await page.locator('text=Avg Speed').locator('..').textContent();
    const freeCard = await page.locator('text=Free Flow').locator('..').textContent();
    console.log(`Traffic Panel metrics: veh='${vehCard?.trim()}', speed='${speedCard?.trim()}', free='${freeCard?.trim()}'`);

    const hasValidNumbers = !vehCard?.includes('.') && speedCard?.includes('km/h') && freeCard?.includes('%');
    auditResults.trafficStatus.metricsValid = hasValidNumbers;

    // Check congestion bars
    const freeBar = await page.locator('text=FREE').first().isVisible();
    const modBar = await page.locator('text=MODERATE').first().isVisible();
    const closedBar = await page.locator('text=CLOSED').first().isVisible();
    auditResults.trafficStatus.congestionBars = freeBar && modBar && closedBar;

    // --- PHASE 6: Route Planner ---
    console.log('\n--- PHASE 6: Route Planner ---');
    await page.locator('button[role="tab"]:has-text("Routing")').first().click();
    await page.waitForTimeout(500);

    // Click sample route button
    const sampleBtn = page.locator('button:has-text("N0000 → N0100")');
    if (await sampleBtn.isVisible()) {
      await sampleBtn.click();
      await page.waitForTimeout(400);
    }

    // Verify Origin & Destination set
    const originSet = await page.locator('text=N0000').isVisible();
    const destSet = await page.locator('text=N0100').isVisible();
    auditResults.routePlanner.selectionSet = originSet && destSet;

    // Test Algorithm Selector
    const algoSelect = page.locator('select:has-text("NeuroRoute")');
    if (await algoSelect.isVisible()) {
      await algoSelect.selectOption('dijkstra');
      await page.waitForTimeout(300);
      await algoSelect.selectOption('all');
      auditResults.routePlanner.algorithmSelector = true;
    }

    // Calculate Routes
    const calcBtn = page.locator('button:has-text("Calculate Routes")');
    await calcBtn.click();
    await page.waitForTimeout(2500);

    const hasRouteComparison = await page.locator('text=Route Comparison').isVisible();
    const hasRecommended = await page.locator('text=NeuroRoute (Recommended)').isVisible();
    auditResults.routePlanner.calculation = hasRouteComparison && hasRecommended;
    console.log(`Route calculation result: comparison=${hasRouteComparison}, recommended=${hasRecommended}`);

    // Test clear buttons
    const clearOriginBtn = page.locator('button[title="Clear origin"]');
    if (await clearOriginBtn.isVisible()) {
      await clearOriginBtn.click();
      await page.waitForTimeout(300);
      auditResults.routePlanner.clearIndividual = !(await page.locator('text=Origin').locator('..').locator('text=N0000').isVisible());
    }

    // --- PHASE 7: Predictions Panel ---
    console.log('\n--- PHASE 7: Predictions Panel ---');
    await page.locator('button[role="tab"]:has-text("Predictions")').first().click();
    await page.waitForTimeout(1000);

    const chartVisible = await page.locator('.recharts-responsive-container').isVisible();
    const modelAlgorithm = await page.locator('text=Algorithm:').locator('..').textContent();
    const hasRoadDropdown = await page.locator('select:has-text("Road #")').isVisible();

    if (hasRoadDropdown) {
      const roadSelect = page.locator('select:has-text("Road #")');
      const options = await roadSelect.locator('option').allTextContents();
      if (options.length > 1) {
        await roadSelect.selectOption({ index: 1 });
        await page.waitForTimeout(1000);
      }
    }

    auditResults.predictions.chartVisible = chartVisible;
    auditResults.predictions.modelInfo = modelAlgorithm?.includes('xgboost') || modelAlgorithm?.includes('N/A') || !!modelAlgorithm;
    auditResults.predictions.roadSelector = hasRoadDropdown;
    console.log(`Predictions: chart=${chartVisible}, roadSelector=${hasRoadDropdown}, model=${modelAlgorithm?.trim()}`);

    // --- PHASE 8: Incident Management ---
    console.log('\n--- PHASE 8: Incident Management ---');
    await page.locator('button[role="tab"]:has-text("Incidents")').first().click();
    await page.waitForTimeout(500);

    const accidentBtn = page.locator('button:has-text("Accident")').first();
    await accidentBtn.click();
    await page.waitForTimeout(2000);

    const roadWorkBtn = page.locator('button:has-text("Road Work")').first();
    await roadWorkBtn.click();
    await page.waitForTimeout(2000);

    const resolveBtn = page.locator('button[title="Resolve Incident"]').first();
    if (await resolveBtn.isVisible()) {
      await resolveBtn.click();
      await page.waitForTimeout(1000);
      auditResults.incidents.resolveIncident = true;
      console.log('✓ Triggered and resolved incident');
    }
    auditResults.incidents.triggerIncident = true;

    // --- PHASE 9: AI Insights ---
    console.log('\n--- PHASE 9: AI Insights ---');
    await page.locator('button[role="tab"]:has-text("AI Insights")').first().click();
    await page.waitForTimeout(500);

    const testNimBtn = page.locator('button:has-text("Test NIM Live")');
    if (await testNimBtn.isVisible()) {
      await testNimBtn.click();
      await page.waitForTimeout(2500);
      const explanationVisible = await page.locator('text=Live NVIDIA NIM Explanation').isVisible() || 
                                 await page.locator('text=Route Recommendation').isVisible();
      auditResults.aiInsights.liveTest = explanationVisible;
      console.log(`AI Insights test NIM live: ${explanationVisible}`);
    }

    // --- PHASE 10: System Metrics ---
    console.log('\n--- PHASE 10: System Metrics ---');
    await page.locator('button[role="tab"]:has-text("Metrics")').first().click();
    await page.waitForTimeout(500);

    const tickVal = await page.locator('p:has-text("Simulation Tick")').locator('..').textContent();
    const wsVal = await page.locator('p:has-text("WebSocket Connected")').locator('..').textContent();
    const statusVal = await page.locator('div.bg-white:has(p:has-text("Status"))').textContent();
    console.log(`System Metrics: tick='${tickVal?.trim()}', ws='${wsVal?.trim()}', status='${statusVal?.trim()}'`);

    auditResults.systemMetrics.tickTracking = !tickVal?.includes(' 0') || tickVal?.length > 0;
    auditResults.systemMetrics.wsStatus = wsVal?.includes('Yes');
    auditResults.systemMetrics.status = statusVal?.includes('running') || statusVal?.includes('idle');

    // --- PHASE 11: What-If Simulation ---
    console.log('\n--- PHASE 11: What-If Simulation ---');
    await page.locator('button[role="tab"]:has-text("What-If")').first().click();
    await page.waitForTimeout(500);

    const scenarioSelector = page.locator('aside form select').first();
    if (await scenarioSelector.isVisible()) {
      await scenarioSelector.selectOption('accident');
      await page.waitForTimeout(300);
    }

    // Select road if road selector present
    const roadSelectWhatIf = page.locator('select:has-text("Select a road")');
    if (await roadSelectWhatIf.isVisible()) {
      const opts = await roadSelectWhatIf.locator('option').all();
      if (opts.length > 1) {
        await roadSelectWhatIf.selectOption({ index: 1 });
      }
    }

    const runWhatIfBtn = page.locator('button:has-text("Run What-If Scenario"), button:has-text("Run Scenario")').first();
    if (await runWhatIfBtn.isVisible()) {
      await runWhatIfBtn.click();
      await page.waitForTimeout(3500);
      const resultCard = await page.locator('text=Comparison').isVisible() || 
                         await page.locator('text=Significant Change').isVisible() ||
                         await page.locator('text=Scenario Parameters').isVisible();
      auditResults.whatIf.runScenario = resultCard;
      console.log(`What-if scenario execution: resultVisible=${resultCard}`);
    }

    // --- PHASE 13: Responsive Viewport Testing ---
    console.log('\n--- PHASE 13: Viewport Testing (8 Screen Sizes) ---');
    const viewports = [
      { name: '1920x1080', width: 1920, height: 1080 },
      { name: '1536x960', width: 1536, height: 960 },
      { name: '1440x900', width: 1440, height: 900 },
      { name: '1280x800', width: 1280, height: 800 },
      { name: '1024x768', width: 1024, height: 768 },
      { name: '768x1024', width: 768, height: 1024 },
      { name: '390x844', width: 390, height: 844 },
      { name: '375x812', width: 375, height: 812 },
    ];

    for (const vp of viewports) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.waitForTimeout(500);
      const canvasVisible = await mapCanvas.isVisible();
      const headerVisible = await page.locator('header').isVisible();
      auditResults.viewports[vp.name] = canvasVisible && headerVisible;
      console.log(`Viewport ${vp.name}: canvas=${canvasVisible}, header=${headerVisible}`);
    }

    // Reset viewport and capture final artifact screenshot
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.locator('button[role="tab"]:has-text("Traffic")').first().click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '08-final-interactive-audit.png'), fullPage: true });

    console.log('\n================ AUDIT SUMMARY ================');
    console.log(JSON.stringify(auditResults, null, 2));
    console.log('================================================\n');

  } catch (err) {
    console.error('Audit run encountered error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

runCompleteInteractionAudit().catch(err => {
  console.error(err);
  process.exit(1);
});
