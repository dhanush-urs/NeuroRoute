import { test, expect } from '@playwright/test';

test.describe('NeuroRoute Traffic Visualization Diagnosis', () => {
  test.setTimeout(120000);

  test('should load and show traffic data', async ({ page }) => {
    // Capture console messages
    const consoleMessages: string[] = [];
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Capture failed network requests
    const failedRequests: string[] = [];
    page.on('response', response => {
      if (response.status() >= 400) {
        failedRequests.push(`${response.request().method()} ${response.url()} - ${response.status()}`);
      }
    });

    // Navigate to the app
    await page.goto('http://localhost:3001', { waitUntil: 'domcontentloaded', timeout: 60000 });
    
    // Take initial screenshot
    await page.screenshot({ path: 'test-results/debug-initial.png', fullPage: true });
    console.log('Initial screenshot taken');
    
    // Wait for map to load and WebSocket to connect
    await page.waitForTimeout(8000);
    
    // Check if Demo menu is open and close it
    const demoButton = page.locator('button:has-text("🎬 Demo")');
    if (await demoButton.isVisible()) {
      await demoButton.click();
      await page.waitForTimeout(500);
    }
    
    // Start simulation
    const startButton = page.locator('button:has-text("▶ Start")');
    if (await startButton.isVisible()) {
      await startButton.click();
      console.log('Clicked Start');
    }
    
    // Wait for traffic data to arrive - increased wait time
    await page.waitForTimeout(15000);
    
    // Wait for vehicle count to be > 0 (traffic data should arrive via WebSocket)
    await page.waitForFunction(() => {
      const elements = document.querySelectorAll('p, span, div');
      for (const el of elements) {
        if (el.textContent?.includes('Total Vehicles')) {
          const parent = el.parentElement;
          if (parent) {
            const valueText = parent.textContent || '';
            const match = valueText.match(/\d+/);
            if (match) {
              const val = parseInt(match[0].replace(/,/g, ''), 10);
              return val > 0;
            }
          }
        }
      }
      return false;
    }, { timeout: 30000 });
    
    // Print console errors and failed requests for debugging
    console.log('Console errors so far:', consoleErrors.length);
    consoleErrors.forEach(e => console.log('  -', e));
    console.log('Failed requests so far:', failedRequests.length);
    failedRequests.forEach(r => console.log('  -', r));
    
    // Take screenshot to debug
    await page.screenshot({ path: 'test-results/debug-before-check.png', fullPage: true });
    console.log('Screenshot taken');
    
    // Check dashboard values
    const trafficStatusHeader = page.locator('text=📊 Traffic Status');
    await expect(trafficStatusHeader).toBeVisible({ timeout: 15000 });
    
    // Check for StatCard values
    const totalVehiclesStat = page.locator('text=Total Vehicles').locator('..').locator('text=/\\d+/');
    const vehiclesText = await totalVehiclesStat.textContent().catch(() => 'Not found');
    console.log('Vehicle count display:', vehiclesText);
    
    const congestedStat = page.locator('text=Congested Roads').locator('..').locator('text=/\\d+/');
    const congestedText = await congestedStat.textContent().catch(() => 'Not found');
    console.log('Congested roads display:', congestedText);
    
    // Check simulation clock
    const simClock = page.locator('text=/SIM: \\d+/');
    const clockText = await simClock.textContent().catch(() => 'Not found');
    console.log('Simulation clock:', clockText);
    
    // Check WebSocket channel connections
    const connectedChannels = await page.evaluate(() => {
      // @ts-ignore
      return window.__WS_DEBUG__?.connectedChannels || {};
    });
    console.log('Connected channels:', JSON.stringify(connectedChannels));
    
    // Check System Metrics
    const systemMetricsHeader = page.locator('text=📈 System Metrics');
    await expect(systemMetricsHeader).toBeVisible({ timeout: 10000 });
    
    const tickStat = page.locator('text=Simulation Tick').locator('..').locator('text=/\\d+/');
    const tickText = await tickStat.textContent().catch(() => 'Not found');
    console.log('Simulation tick:', tickText);
    
    const wsStat = page.locator('text=WebSocket Connected').locator('..').locator('text=/Yes|No/');
    const wsText = await wsStat.textContent().catch(() => 'Not found');
    console.log('WebSocket connected:', wsText);
    
    // Take screenshot
    await page.screenshot({ path: 'test-results/traffic-data-check.png', fullPage: true });
    
    // Print WebSocketService debug messages
    const wsMessages = consoleMessages.filter(m => m.includes('[WebSocketService]'));
    console.log('WebSocketService messages:', wsMessages.length);
    wsMessages.forEach(m => console.log('  ', m));
    
    // Print useTrafficData debug messages
    const trafficMessages = consoleMessages.filter(m => m.includes('[useTrafficData]'));
    console.log('useTrafficData messages:', trafficMessages.length);
    trafficMessages.forEach(m => console.log('  ', m));
    
    // Print summary
    console.log('\n=== DIAGNOSIS SUMMARY ===');
    console.log('Console errors:', consoleErrors.length);
    consoleErrors.forEach(e => console.log('  -', e));
    console.log('Failed requests:', failedRequests.length);
    failedRequests.forEach(r => console.log('  -', r));
    
    // Assert no critical errors (filter out expected WebSocket reconnection errors)
    const criticalErrors = consoleErrors.filter(e => 
      !e.includes('favicon') && 
      !e.includes('manifest') && 
      !e.includes('source map') &&
      !e.includes('WebSocket error on traffic') &&  // Expected during reconnection
      !e.includes('WebSocket error on routing') &&  // Expected during reconnection
      !e.includes('WebSocket error on incidents') &&  // Expected during reconnection
      !e.includes('WebSocket error on simulation')   // Expected during reconnection
    );
    expect(criticalErrors.length).toBe(0);
    
    // The key assertion - traffic data should be > 0
    // Using a softer assertion to see what we get
    console.log('Vehicle count:', vehiclesText);
    console.log('Congested roads:', congestedText);
    
    // Assert that traffic data is being received (vehicle count should be > 0 after simulation runs)
    const vehicleCount = parseInt(vehiclesText?.replace(/,/g, '') || '0', 10);
    expect(vehicleCount).toBeGreaterThan(0);
  });
});