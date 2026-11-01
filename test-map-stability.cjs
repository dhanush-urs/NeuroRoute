const { chromium } = require('playwright');
const path = require('path');

async function testMapStability() {
  console.log('Testing Map Stability & Refresh Fix...');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  let mapInits = 0;
  let pageErrors = [];

  page.on('pageerror', err => pageErrors.push(err.message));
  page.on('console', msg => {
    if (msg.text().includes('Initializing map') || msg.text().includes('Failed to fit bounds')) {
      console.log('Console:', msg.text());
    }
  });

  await page.goto('http://localhost:3000', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  // Check canvas element
  const canvas = page.locator('.maplibregl-canvas');
  await canvas.waitFor({ state: 'visible', timeout: 10000 });
  console.log('Canvas is visible');

  // Let simulation run for 8 seconds (multiple ticks)
  console.log('Observing map for 8 seconds under active WebSocket streaming...');
  const initialCanvasHandle = await canvas.elementHandle();
  await page.waitForTimeout(8000);
  const currentCanvasHandle = await canvas.elementHandle();

  // Verify the canvas element was NOT replaced / recreated in the DOM
  const isSameCanvas = await page.evaluate(
    ([c1, c2]) => c1 === c2,
    [initialCanvasHandle, currentCanvasHandle]
  );
  console.log('Canvas element persisted without DOM recreation (no glitch/refresh):', isSameCanvas);

  await page.screenshot({ path: path.join(__dirname, 'test-results', 'screenshots', '07-stable-map-fixed.png'), fullPage: true });

  console.log('Errors during 8s observation:', pageErrors);
  await browser.close();

  if (!isSameCanvas || pageErrors.length > 0) {
    console.error('Test FAILED: Canvas was replaced or errors occurred.');
    process.exit(1);
  } else {
    console.log('Test PASSED: Map remains stable and persistent without any flickering or reloading.');
  }
}

testMapStability().catch(err => {
  console.error(err);
  process.exit(1);
});
