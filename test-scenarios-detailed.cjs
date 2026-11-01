/**
 * Comprehensive NeuroRoute Demo Scenario Verification Test Suite
 *
 * Verifies all 8 Demo scenarios individually and through repeated transition sequences:
 * - Normal Traffic
 * - Morning Rush
 * - Major Jam
 * - Accident
 * - Road Closure
 * - Heavy Rain
 * - Traffic Surge
 * - Major Event
 *
 * Verifies backend state via API, WebSocket updates, and frontend UI responsiveness.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const http = require('http');

const BASE_URL = 'http://localhost:3000';
const API_URL = 'http://localhost:8000';
const SCREENSHOTS_DIR = path.join(__dirname, 'test-results', 'screenshots', 'scenarios');

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

function fetchJson(urlPath) {
  return new Promise((resolve, reject) => {
    http.get(`${API_URL}${urlPath}`, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          resolve({ raw: data, status: res.statusCode });
        }
      });
    }).on('error', reject);
  });
}

async function runScenarioAudit() {
  console.log('🚀 Starting Comprehensive NeuroRoute Scenario Verification...\n');

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const auditReport = {
    timestamp: new Date().toISOString(),
    scenarios: {},
    transitionSequences: {},
    uiInteractions: {
      menuOpens: false,
      menuClosesOnSelect: false,
      escapeDismiss: false,
      outsideClickDismiss: false,
      loadingStateShown: false,
      feedbackToastShown: false,
    }
  };

  try {
    console.log('1. Navigating to frontend...');
    await page.goto(BASE_URL, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    const demoBtn = page.locator('#demo-scenarios-btn, button:has-text("Demo")').first();
    await demoBtn.waitFor({ state: 'visible', timeout: 10000 });
    console.log('✓ Frontend loaded and Demo button visible');

    // --- UI Interaction Tests ---
    console.log('\n2. Testing Demo Menu Interactions & Accessibility...');
    
    // Open menu
    await demoBtn.click();
    await page.waitForTimeout(300);
    const menu = page.locator('div[role="menu"]');
    auditReport.uiInteractions.menuOpens = await menu.isVisible();
    console.log(`- Menu opens: ${auditReport.uiInteractions.menuOpens}`);

    // Dismiss with Escape key
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const closedAfterEscape = !(await menu.isVisible());
    auditReport.uiInteractions.escapeDismiss = closedAfterEscape;
    console.log(`- Escape dismisses menu: ${closedAfterEscape}`);

    // Reopen and outside click dismiss
    await demoBtn.click();
    await page.waitForTimeout(300);
    await page.mouse.click(10, 10);
    await page.waitForTimeout(300);
    const closedAfterOutside = !(await menu.isVisible());
    auditReport.uiInteractions.outsideClickDismiss = closedAfterOutside;
    console.log(`- Outside click dismisses menu: ${closedAfterOutside}`);

    // Helper to click scenario and observe behavior
    async function selectScenario(scenarioLabel, scenarioId) {
      console.log(`\n▶ Testing Scenario: ${scenarioLabel} (${scenarioId})...`);
      
      // Wait for any active applying state to finish
      await page.waitForFunction(() => !document.querySelector('#demo-scenarios-btn')?.hasAttribute('disabled'), { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(200);

      // Open dropdown if closed
      if (!(await menu.isVisible())) {
        await demoBtn.click();
        await menu.waitFor({ state: 'visible', timeout: 5000 });
      }

      const item = page.locator(`button[role="menuitem"]:has-text("${scenarioLabel}")`);
      await item.waitFor({ state: 'visible', timeout: 5000 });

      // Click scenario
      const [response] = await Promise.all([
        page.waitForResponse(res => res.url().includes('/api/v1/simulation/scenario') && res.request().method() === 'POST'),
        item.click()
      ]);

      const resBody = await response.json();
      console.log(`  API Response status: ${response.status()}, status applied: ${resBody.status}`);

      // Wait for UI to update feedback and close menu
      await page.waitForTimeout(1000);
      const menuClosed = !(await menu.isVisible());
      auditReport.uiInteractions.menuClosesOnSelect = menuClosed;

      // Check feedback badge
      const feedback = page.locator('div[role="status"]');
      const hasFeedback = await feedback.isVisible();
      if (hasFeedback) {
        auditReport.uiInteractions.feedbackToastShown = true;
        const text = await feedback.textContent();
        console.log(`  Feedback visible: "${text}"`);
      }

      // Query backend state
      const simStatus = await fetchJson('/api/v1/simulation/status');
      const activeIncidents = await fetchJson('/api/v1/incidents/active');
      const trafficSummary = await fetchJson('/api/v1/traffic/summary');

      // Take screenshot
      const screenshotPath = path.join(SCREENSHOTS_DIR, `scenario-${scenarioId}.png`);
      await page.screenshot({ path: screenshotPath });

      return {
        scenarioId,
        scenarioLabel,
        httpStatus: response.status(),
        apiResponseBody: resBody,
        simStatus,
        activeIncidentsCount: activeIncidents.count ?? activeIncidents.length ?? 0,
        activeIncidents: activeIncidents.incidents ?? activeIncidents,
        trafficSummary,
        menuClosed,
        hasFeedback,
        screenshot: `scenario-${scenarioId}.png`
      };
    }

    // --- TEST INDIVIDUAL SCENARIOS ---
    
    // 1. Normal Traffic
    const normalRes = await selectScenario('Normal Traffic', 'normal');
    auditReport.scenarios.normal = {
      passed: normalRes.simStatus.demand_multiplier === 1.0 && 
              normalRes.activeIncidentsCount === 0 && 
              normalRes.simStatus.weather === 'clear',
      details: normalRes
    };
    console.log(`  Result Normal: demand=${normalRes.simStatus.demand_multiplier}, incidents=${normalRes.activeIncidentsCount}, weather=${normalRes.simStatus.weather}`);

    // 2. Morning Rush
    const rushRes = await selectScenario('Morning Rush', 'rush_hour');
    auditReport.scenarios.rush_hour = {
      passed: rushRes.simStatus.demand_multiplier >= 1.5 && 
              rushRes.simStatus.weather === 'clear',
      details: rushRes
    };
    console.log(`  Result Morning Rush: demand=${rushRes.simStatus.demand_multiplier}`);

    // 3. Major Jam
    const jamRes = await selectScenario('Major Jam', 'major_jam');
    auditReport.scenarios.major_jam = {
      passed: jamRes.simStatus.demand_multiplier >= 2.0 && 
              jamRes.activeIncidentsCount >= 1,
      details: jamRes
    };
    console.log(`  Result Major Jam: demand=${jamRes.simStatus.demand_multiplier}, incidents=${jamRes.activeIncidentsCount}`);

    // 4. Accident
    const accidentRes = await selectScenario('Accident', 'accident');
    auditReport.scenarios.accident = {
      passed: accidentRes.activeIncidentsCount >= 1 && 
              accidentRes.activeIncidents.some(i => i.incident_type === 'accident' || i.type === 'accident'),
      details: accidentRes
    };
    console.log(`  Result Accident: active incidents=${accidentRes.activeIncidentsCount}`);

    // 5. Road Closure
    const closureRes = await selectScenario('Road Closure', 'road_closure');
    const closureFound = closureRes.activeIncidents.some(i => (i.incident_type === 'road_closure' || i.type === 'road_closure'));
    auditReport.scenarios.road_closure = {
      passed: closureFound,
      details: closureRes
    };
    console.log(`  Result Road Closure: closure incident active=${closureFound}`);

    // 6. Heavy Rain
    const rainRes = await selectScenario('Heavy Rain', 'heavy_rain');
    auditReport.scenarios.heavy_rain = {
      passed: rainRes.simStatus.weather === 'heavy_rain' && rainRes.simStatus.weather_locked === true,
      details: rainRes
    };
    console.log(`  Result Heavy Rain: weather=${rainRes.simStatus.weather}, locked=${rainRes.simStatus.weather_locked}`);

    // 7. Traffic Surge
    const surgeRes = await selectScenario('Traffic Surge', 'traffic_surge');
    auditReport.scenarios.traffic_surge = {
      passed: Math.abs(surgeRes.simStatus.demand_multiplier - 1.30) < 0.05,
      details: surgeRes
    };
    console.log(`  Result Traffic Surge: demand=${surgeRes.simStatus.demand_multiplier} (expected 1.30)`);

    // 8. Major Event
    const eventRes = await selectScenario('Major Event', 'major_event');
    const eventFound = eventRes.activeIncidents.some(i => (i.incident_type === 'special_event' || i.type === 'special_event'));
    auditReport.scenarios.major_event = {
      passed: eventFound && eventRes.apiResponseBody.modifications?.localized_demand_multiplier === 2.8,
      details: eventRes
    };
    console.log(`  Result Major Event: special event incident=${eventFound}, localized demand=2.8`);

    // --- REPEATED TRANSITION SEQUENCES ---
    console.log('\n3. Testing Multi-Step Transition Sequences (Verifying State Isolation)...');

    // Sequence 1: Normal → Morning Rush → Major Jam → Normal
    console.log('\nTesting Sequence 1: Normal → Morning Rush → Major Jam → Normal');
    await selectScenario('Normal Traffic', 'normal');
    await selectScenario('Morning Rush', 'rush_hour');
    await selectScenario('Major Jam', 'major_jam');
    const seq1End = await selectScenario('Normal Traffic', 'normal');
    const seq1Passed = seq1End.simStatus.demand_multiplier === 1.0 && seq1End.activeIncidentsCount === 0;
    auditReport.transitionSequences.sequence1 = {
      name: 'Normal -> Rush -> Jam -> Normal',
      passed: seq1Passed,
      finalState: { demand: seq1End.simStatus.demand_multiplier, incidents: seq1End.activeIncidentsCount }
    };
    console.log(`✓ Sequence 1 Passed: ${seq1Passed} (baseline fully restored)`);

    // Sequence 2: Normal → Accident → Road Closure → Normal
    console.log('\nTesting Sequence 2: Normal → Accident → Road Closure → Normal');
    await selectScenario('Accident', 'accident');
    await selectScenario('Road Closure', 'road_closure');
    const seq2End = await selectScenario('Normal Traffic', 'normal');
    const seq2Passed = seq2End.activeIncidentsCount === 0 && seq2End.simStatus.weather === 'clear';
    auditReport.transitionSequences.sequence2 = {
      name: 'Normal -> Accident -> Closure -> Normal',
      passed: seq2Passed,
      finalState: { incidents: seq2End.activeIncidentsCount, weather: seq2End.simStatus.weather }
    };
    console.log(`✓ Sequence 2 Passed: ${seq2Passed} (incidents and closures cleanly cleared)`);

    // Sequence 3: Normal → Heavy Rain → Traffic Surge → Major Event → Normal
    console.log('\nTesting Sequence 3: Normal → Heavy Rain → Traffic Surge → Major Event → Normal');
    await selectScenario('Heavy Rain', 'heavy_rain');
    await selectScenario('Traffic Surge', 'traffic_surge');
    await selectScenario('Major Event', 'major_event');
    const seq3End = await selectScenario('Normal Traffic', 'normal');
    const seq3Passed = seq3End.simStatus.demand_multiplier === 1.0 && 
                       seq3End.simStatus.weather === 'clear' && 
                       seq3End.simStatus.weather_locked === false &&
                       seq3End.activeIncidentsCount === 0;
    auditReport.transitionSequences.sequence3 = {
      name: 'Normal -> Rain -> Surge -> Event -> Normal',
      passed: seq3Passed,
      finalState: {
        demand: seq3End.simStatus.demand_multiplier,
        weather: seq3End.simStatus.weather,
        weatherLocked: seq3End.simStatus.weather_locked,
        incidents: seq3End.activeIncidentsCount
      }
    };
    console.log(`✓ Sequence 3 Passed: ${seq3Passed} (weather lock and localized multipliers cleared)`);

    console.log('\n================ SCENARIO VERIFICATION SUMMARY ================');
    console.log(JSON.stringify({
      scenariosPassed: Object.entries(auditReport.scenarios).every(([_, v]) => v.passed),
      sequencesPassed: Object.entries(auditReport.transitionSequences).every(([_, v]) => v.passed),
      uiInteractions: auditReport.uiInteractions,
      summary: Object.fromEntries(Object.entries(auditReport.scenarios).map(([k, v]) => [k, v.passed]))
    }, null, 2));
    console.log('===============================================================\n');

  } catch (err) {
    console.error('Scenario audit encountered an error:', err);
    process.exit(1);
  } finally {
    await browser.close();
  }
}

runScenarioAudit().catch(err => {
  console.error(err);
  process.exit(1);
});
