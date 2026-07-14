const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('playwright');

const prototype = path.join(__dirname, require('node:fs').readdirSync(__dirname).find(name => name.endsWith('.html')) || 'prototype.html');
let server, browser, page, origin;

async function activeClick(selector) {
  await page.locator(`section.page.active ${selector}`).first().click();
}
async function activeRoute(route) {
  await page.locator(`section.page.active [data-testid="task-subnav"] [data-route="${route}"]`).click();
}
async function taskOverview() {
  await page.locator('.nav-item[data-target="tasks"]').click();
  await activeClick('button[data-target="overview"]');
}

test.before(async () => {
  server = http.createServer(async (_req, res) => {
    res.writeHead(200, {'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store'});
    res.end(await fs.readFile(prototype));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
});
test.after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });
test.beforeEach(async () => { page = await browser.newPage({viewport: {width: 1440, height: 900}}); page.setDefaultTimeout(3000); await page.goto(origin); });
test.afterEach(async () => { await page?.close(); });

test('outline confirmation invalidates original DAG nodes without a duplicate result panel', async () => {
  await taskOverview();
  await activeClick('button[data-target="outline"]');
  await activeClick('button[data-action="outline-impact"]');
  await page.locator('#modalConfirm').click();
  assert.equal(await page.locator('#workflowInvalidationResult').count(), 0);
  assert.equal(await page.locator('[data-node-id="section_generate_group"]').getAttribute('data-runtime-status'), 'invalidated');
  assert.match(await page.locator('[data-node-id="section_generate_group"]').textContent(), /5 个节点已失效/);
  assert.equal(await page.locator('[data-node-id]').evaluateAll(nodes => new Set(nodes.map(node => node.dataset.nodeId)).size), await page.locator('[data-node-id]').count());
});

test('dead-letter recovery creates a separate queued NodeRun with provenance', async () => {
  await page.locator('.nav-item[data-target="dashboard"]').click();
  await activeClick('button[data-action="deadletter-recover"]');
  assert.equal(await page.locator('#recoveryReason').count(), 1);
  await page.locator('#recoveryReason').fill('补充可解析 PDF 后重新入队');
  await page.locator('#modalConfirm').click();
  assert.equal(await page.locator('#recoveryNodeRun').getAttribute('data-state'), 'queued');
  assert.match(await page.locator('#recoveryNodeRun').textContent(), /DeadLetter #DL-0017[\s\S]*补充可解析 PDF 后重新入队[\s\S]*source_parser_pdf/);
});

test('quality recheck exposes ReviewRun then advances the final quality gate', async () => {
  await taskOverview();
  await activeRoute('quality');
  await activeClick('button[data-action="quality-recheck"]');
  assert.equal(await page.locator('#reviewRunState').getAttribute('data-state'), 'running');
  assert.match(await page.locator('#reviewRunState').textContent(), /ReviewRun #RR-008[\s\S]*待复检问题2[\s\S]*quality_gate_finalWAITING/);
  await activeClick('button[data-action="quality-complete"]');
  assert.equal(await page.locator('#reviewRunState').getAttribute('data-state'), 'succeeded');
  assert.match(await page.locator('#reviewRunState').textContent(), /BLOCKING0[\s\S]*quality_gate_final[\s\S]*SUCCEEDED/);
});

test('delivery approval selects DeliveryPackage v3 and enables official download', async () => {
  await taskOverview();
  await activeRoute('delivery');
  await activeClick('button[data-action="delivery-approve"]');
  assert.equal(await page.locator('#deliveryApprovalDetail').getAttribute('data-gate'), 'delivery_approval');
  await page.locator('#approvalBar button[data-action="approval-approve"]').click();
  assert.equal(await page.locator('#deliveryPackageStatus').getAttribute('data-state'), 'approved');
  assert.equal(await page.locator('#officialDownload').isEnabled(), true);
  assert.equal(await page.locator('.page[data-page="approvals"] .panel-grid').evaluate(el => getComputedStyle(el).paddingBottom), '88px');
});

test('SVG DAG keeps every node within its stage and every edge on ports', async () => {
  await taskOverview();
  await activeClick('button[data-target="workflow"]');
  const report = await page.locator('#workflowCanvas').evaluate(canvas => {
    const tolerance = 2;
    const svg = canvas.querySelector('svg');
    const toScreen = point => {
      const svgPoint = svg.createSVGPoint();
      svgPoint.x = point.x; svgPoint.y = point.y;
      return svgPoint.matrixTransform(svg.getScreenCTM());
    };
    const nodesInsideStages = [...canvas.querySelectorAll('[data-node-id]')].every(node => {
      const stage = canvas.querySelector(`.workflow-stage[data-stage-id="${node.dataset.stageId}"]`);
      const nodeBox = node.getBoundingClientRect(), stageBox = stage.getBoundingClientRect();
      return nodeBox.left >= stageBox.left - tolerance && nodeBox.right <= stageBox.right + tolerance && nodeBox.top >= stageBox.top - tolerance && nodeBox.bottom <= stageBox.bottom + tolerance;
    });
    const edgesOnPorts = [...canvas.querySelectorAll('path[data-edge-id]')].every(path => {
      const length = path.getTotalLength();
      const start = toScreen(path.getPointAtLength(0)), end = toScreen(path.getPointAtLength(length));
      const source = canvas.querySelector(`[data-port-id="${path.dataset.sourcePort}"]`).getBoundingClientRect();
      const target = canvas.querySelector(`[data-port-id="${path.dataset.targetPort}"]`).getBoundingClientRect();
      const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
      return distance(start, {x: source.right, y: source.top + source.height / 2}) <= tolerance && distance(end, {x: target.left, y: target.top + target.height / 2}) <= tolerance;
    });
    return {nodesInsideStages, edgesOnPorts, stageWidths: [...canvas.querySelectorAll('.workflow-stage[data-stage-id]')].map(stage => stage.getBoundingClientRect().width)};
  });
  assert.equal(report.nodesInsideStages, true);
  assert.equal(report.edgesOnPorts, true);
  assert.ok(report.stageWidths.every(width => Math.round(width) >= 232));
});

test('chapter group expands in place and preserves a single node identity per NodeRun', async () => {
  await taskOverview();
  await activeClick('button[data-target="outline"]');
  await activeClick('button[data-action="outline-impact"]');
  await page.locator('#modalConfirm').click();
  await page.locator('[data-action="toggle-chapter-group"]').click();
  assert.equal(await page.locator('[data-node-id="section_generate_group"]').count(), 0);
  assert.equal(await page.locator('[data-node-id^="section_generate_ch"]').count(), 5);
  assert.equal(await page.locator('[data-node-id]').evaluateAll(nodes => new Set(nodes.map(node => node.dataset.nodeId)).size), await page.locator('[data-node-id]').count());
});

test('TaskSubNavigation supports all nine entries and History API state', async () => {
  await page.goto(`${origin}/tasks/task-001/workflow?node=engineering_verify&attempt=2`);
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'workflow');
  assert.equal(await page.locator('#inspector').getAttribute('data-selected-node'), 'engineering_verify');
  const routes = ['overview', 'workflow', 'materials', 'evidence', 'outline', 'content', 'engineering', 'quality', 'delivery'];
  for (const route of routes) {
    await activeRoute(route);
    assert.equal(await page.locator('section.page.active').getAttribute('data-page'), route);
    assert.match(page.url(), new RegExp(`/tasks/task-001/${route}`));
  }
  await activeRoute('workflow');
  await activeRoute('evidence');
  await page.goBack();
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'workflow');
  await page.goForward();
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'evidence');
  await page.reload();
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'evidence');
});
