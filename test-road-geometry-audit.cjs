const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function testRoadGeometryAudit() {
  console.log('Starting NeuroRoute Road Geometry & Vehicle Map-Matching Audit...');
  
  const artifactDir = '/Users/dhanushursmk/.gemini/antigravity/brain/8619c6ec-35a0-4100-aced-ad28b3fc4f39/screenshots/geometry';
  fs.mkdirSync(artifactDir, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  const pageErrors = [];
  page.on('pageerror', err => pageErrors.push(err.message));
  page.on('console', msg => {
    if (msg.type() === 'error') {
      pageErrors.push(msg.text());
    }
  });

  await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  // Wait for canvas
  const canvas = page.locator('.maplibregl-canvas');
  await canvas.waitFor({ state: 'visible', timeout: 15000 });
  console.log('✓ MapLibre Canvas visible');

  // Let simulation stream for 3 seconds
  await page.waitForTimeout(4000);

  // Query MapLibre state from browser context
  const mapData = await page.evaluate(() => {
    // Look for maplibregl map instance
    // Most apps attach it or have window._map, or we inspect sources from DOM/window
    // If not on window, we can test via DOM and network
    const layers = Array.from(document.querySelectorAll('.maplibregl-canvas'));
    return {
      canvasExists: layers.length > 0,
    };
  });
  console.log('Map status in browser:', mapData);

  // Take screenshot 1: Full road network overview
  const screenshot1Path = path.join(artifactDir, '01-manhattan-osm-network.png');
  await page.screenshot({ path: screenshot1Path, fullPage: true });
  console.log('✓ Captured 01-manhattan-osm-network.png');

  // Zoom into Lower Manhattan / Financial District / SoHo to view vehicles on actual streets
  // Scroll map wheel or drag
  await page.mouse.move(720, 450);
  for (let i = 0; i < 5; i++) {
    await page.mouse.wheel(0, -200); // zoom in
    await page.waitForTimeout(400);
  }
  await page.waitForTimeout(2000);

  const screenshot2Path = path.join(artifactDir, '02-zoomed-vehicles-on-osm-streets.png');
  await page.screenshot({ path: screenshot2Path, fullPage: true });
  console.log('✓ Captured 02-zoomed-vehicles-on-osm-streets.png');

  // Test Route Calculation in RoutePlanner panel
  console.log('Testing Route Planner with authentic OSM road geometry...');
  const routingTab = page.locator('button:has-text("Routing")').first();
  await routingTab.waitFor({ state: 'visible', timeout: 5000 });
  await routingTab.click();
  console.log('✓ Switched to Routing tab');
  await page.waitForTimeout(1000);

  // Click sample route button
  const sampleBtn = page.locator('button:has-text("Battery Park → SoHo / Canal")').first();
  await sampleBtn.waitFor({ state: 'visible', timeout: 5000 });
  console.log('Clicking sample route button: Battery Park → SoHo / Canal');
  await sampleBtn.click();
  await page.waitForTimeout(1000);

  const calcBtn = page.locator('button:has-text("Calculate Routes")').first();
  await calcBtn.waitFor({ state: 'visible', timeout: 5000 });
  console.log('Clicking Calculate Routes button');
  await calcBtn.click();
  await page.waitForTimeout(4000);

  const screenshot3Path = path.join(artifactDir, '03-route-rendered-on-osm-geometry.png');
  await page.screenshot({ path: screenshot3Path, fullPage: true });
  console.log('✓ Captured 03-route-rendered-on-osm-geometry.png');

  console.log('Page errors observed:', pageErrors);
  await browser.close();

  console.log('Test completed successfully!');
}

testRoadGeometryAudit().catch(err => {
  console.error('Audit failed:', err);
  process.exit(1);
});
