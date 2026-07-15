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
  assert.equal(await page.locator('[data-node-id="section_generate_pre_group"]').getAttribute('data-runtime-status'), 'invalidated');
  assert.match(await page.locator('[data-node-id="section_generate_pre_group"]').textContent(), /5 个前置章节已失效/);
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
      const sourcePort = canvas.querySelector(`[data-port-id="${path.dataset.sourcePort}"]`);
      const targetPort = canvas.querySelector(`[data-port-id="${path.dataset.targetPort}"]`);
      const source = sourcePort.getBoundingClientRect(), target = targetPort.getBoundingClientRect();
      const anchor = (box, side) => {
        if (side === 'out-right') return {x: box.right, y: box.top + box.height / 2};
        if (side === 'in-left') return {x: box.left, y: box.top + box.height / 2};
        if (side === 'out-bottom') return {x: box.left + box.width / 2, y: box.bottom};
        return {x: box.left + box.width / 2, y: box.top};
      };
      const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
      return distance(start, anchor(source, sourcePort.dataset.portSide)) <= tolerance && distance(end, anchor(target, targetPort.dataset.portSide)) <= tolerance;
    });
    return {nodesInsideStages, edgesOnPorts, stageWidths: [...canvas.querySelectorAll('.workflow-stage[data-stage-id]')].map(stage => stage.getBoundingClientRect().width), edgeIds: [...canvas.querySelectorAll('path[data-edge-id]')].map(edge => edge.dataset.edgeId)};
  });
  assert.equal(report.nodesInsideStages, true);
  assert.equal(report.edgesOnPorts, true);
  assert.ok(report.stageWidths.every(width => Math.round(width) >= 232));
  assert.equal(report.stageWidths.length, 8);
  assert.deepEqual(report.edgeIds, [
    'task_start_approval--project_source_parse',
    'project_source_parse--project_fact_confirm',
    'project_fact_confirm--outline_plan',
    'outline_plan--section_generate_pre_group',
    'section_generate_pre_group--engineering_verify',
    'engineering_verify--section_generate_ch6',
    'section_generate_ch6--section_generate_ch7',
    'section_generate_ch7--manuscript_quality_check',
    'manuscript_quality_check--quality_gate_final',
    'quality_gate_final--docx_render',
    'docx_render--delivery_approval'
  ]);
});

test('chapter group expands in place and preserves a single node identity per NodeRun', async () => {
  await taskOverview();
  await activeClick('button[data-target="outline"]');
  await activeClick('button[data-action="outline-impact"]');
  await page.locator('#modalConfirm').click();
  await page.locator('[data-action="toggle-chapter-group"]').click();
  assert.equal(await page.locator('[data-node-id="section_generate_pre_group"]').count(), 0);
  assert.equal(await page.locator('[data-node-id^="section_generate_pre_ch"]').count(), 5);
  assert.equal(await page.locator('[data-node-id]').evaluateAll(nodes => new Set(nodes.map(node => node.dataset.nodeId)).size), await page.locator('[data-node-id]').count());
});

test('TaskSubNavigation supports all nine entries and History API state', async () => {
  await page.goto(`${origin}/tasks/task-001/workflow?node=engineering_verify&attempt=2`);
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'workflow');
  assert.equal(await page.locator('#inspector').getAttribute('data-selected-node'), 'engineering_verify');
  await activeRoute('materials');
  assert.equal(new URL(page.url()).search, '');
  assert.equal(await page.locator('#inspector').getAttribute('data-selected-node'), '');
  assert.equal(await page.locator('#inspector').getAttribute('data-owner-page'), '');
  assert.equal(await page.locator('#inspector').evaluate(inspector => inspector.classList.contains('closed')), true);
  await page.goBack();
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

test('direct task URLs sanitize foreign query keys and keep the Workflow Inspector isolated', async () => {
  await page.goto(`${origin}/tasks/task-001/evidence?node=engineering_verify&attempt=2&claim=Claim-219&source=EC-043`);
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'evidence');
  assert.equal(new URL(page.url()).search, '?claim=Claim-219&source=EC-043');
  assert.equal(await page.locator('#inspector').getAttribute('data-selected-node'), '');
  assert.equal(await page.locator('#inspector').evaluate(inspector => inspector.classList.contains('closed')), true);
  await page.reload();
  assert.equal(new URL(page.url()).search, '?claim=Claim-219&source=EC-043');
  assert.equal(await page.locator('#inspector').evaluate(inspector => inspector.classList.contains('closed')), true);
});

test('global navigation updates URL, History state, and active page for every destination', async () => {
  const routes = [
    ['dashboard', '/dashboard'],
    ['tasks', '/tasks'],
    ['approvals', '/approvals'],
    ['benchmarks', '/benchmarks'],
    ['templates', '/templates'],
    ['workers', '/system/workers'],
    ['model-calls', '/system/model-calls'],
    ['audit', '/system/audit']
  ];
  for (const [target, pathname] of routes) {
    await page.locator(`.nav-item[data-target="${target}"]`).click();
    assert.equal(new URL(page.url()).pathname, pathname);
    assert.equal(await page.locator('section.page.active').getAttribute('data-page'), target);
    assert.equal(await page.evaluate(() => history.state?.page), target);
  }
  await page.goBack();
  assert.equal(new URL(page.url()).pathname, '/system/model-calls');
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'model-calls');
  await page.goForward();
  assert.equal(new URL(page.url()).pathname, '/system/audit');
  await page.reload();
  assert.equal(await page.locator('section.page.active').getAttribute('data-page'), 'audit');
});

test('startup gate confirms extracted ProjectFacts without changing exact part numbers', async () => {
  await page.locator('.nav-item[data-target="tasks"]').click();
  await activeClick('button[data-target="new-task"]');
  assert.equal(await page.locator('#projectFactIntake').getAttribute('data-fact-gate-state'), 'PENDING_CONFIRMATION');
  assert.deepEqual(await page.locator('#projectFactIntake [data-fact-id]').evaluateAll(rows => rows.slice(0, 4).map(row => row.dataset.canonicalValue)), [
    'STM32F103C8T6', 'DHT11', 'ESP8266-01S', '0.96 英寸 OLED / SSD1306'
  ]);
  await activeClick('button[data-action="confirm-intake-facts"]');
  assert.equal(await page.locator('#projectFactIntake').getAttribute('data-fact-gate-state'), 'CONFIRMED');
  assert.equal(await page.locator('#projectFactIntake [data-fact-id]').evaluateAll(rows => rows.every(row => row.dataset.status === 'CONFIRMED' && row.dataset.locked === 'true')), true);
});

test('ProjectFactSnapshot preserves exact models across materials, outline, content, BOM, and quality', async () => {
  await taskOverview();
  await activeRoute('materials');
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-project-fact-snapshot-version'), '5');
  assert.deepEqual(await page.locator('#materialProjectFacts [data-fact-id]').evaluateAll(rows => rows.slice(0, 4).map(row => row.dataset.canonicalValue)), [
    'STM32F103C8T6', 'DHT11', 'ESP8266-01S', '0.96 英寸 OLED / SSD1306'
  ]);
  await activeRoute('outline');
  assert.equal(await page.locator('#outlineProjectFacts').getAttribute('data-fact-gate-state'), 'READY');
  assert.equal(await page.locator('#outlineProjectFacts').getAttribute('data-project-fact-snapshot-version'), '5');
  await activeRoute('content');
  const contentFacts = await page.locator('#contentProjectFacts').textContent();
  assert.match(contentFacts, /STM32F103C8T6[\s\S]*DHT11[\s\S]*ESP8266-01S[\s\S]*SSD1306/);
  assert.doesNotMatch(contentFacts, /STM32F407|DHT22|ESP32/);
  assert.match(await page.locator('#contentProjectFacts [data-fact-surface="bom"]').textContent(), /STM32F103C8T6[\s\S]*SSD1306/);
  await activeRoute('quality');
  assert.equal(await page.locator('#projectFactQuality').getAttribute('data-project-fact-snapshot-version'), '5');
  assert.equal(await page.locator('#projectFactQuality [data-rule-id="FACT_CONSTRAINT_VIOLATION"]').count(), 1);
});

test('retrieval policy separates exact, series, and related models', async () => {
  await taskOverview();
  await activeRoute('evidence');
  assert.equal(await page.locator('#projectFactRetrieval [data-match-type="EXACT_MATCH"]').count(), 1);
  assert.equal(await page.locator('#projectFactRetrieval [data-match-type="SERIES_MATCH"]').count(), 1);
  assert.equal(await page.locator('#projectFactRetrieval [data-match-type="RELATED_MODEL"]').count(), 1);
  assert.match(await page.locator('#projectFactRetrieval').textContent(), /"STM32F103C8T6" 官方数据手册[\s\S]*可支撑型号专属参数/);
  const related = page.locator('#projectFactRetrieval [data-match-type="RELATED_MODEL"]');
  assert.equal(await related.getAttribute('data-model-context'), 'comparison');
  assert.match(await related.textContent(), /STM32F407[\s\S]*不得支撑当前实现主张/);
});

test('conflicting user materials block the outline until human confirmation creates a new snapshot', async () => {
  await taskOverview();
  await activeRoute('materials');
  await activeClick('button[data-action="simulate-fact-conflict"]');
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-conflict-status'), 'OPEN');
  assert.match(await page.locator('#projectFactConflict').textContent(), /STM32F103C8T6[\s\S]*STM32F407VET6[\s\S]*未自动选择/);
  assert.equal(await page.locator('#materialProjectFacts [data-fact-id="fact-mcu-001"]').getAttribute('data-canonical-value'), 'STM32F103C8T6');
  await activeRoute('outline');
  assert.equal(await page.locator('#outlineProjectFacts').getAttribute('data-fact-gate-state'), 'BLOCKED');
  await activeRoute('workflow');
  assert.equal(await page.locator('[data-node-id="project_fact_confirm"]').getAttribute('data-runtime-status'), 'blocked');
  assert.equal(await page.locator('[data-node-id="outline_plan"]').getAttribute('data-runtime-status'), 'blocked');
  await activeRoute('materials');
  await activeClick('button[data-action="confirm-project-fact"]');
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-conflict-status'), 'RESOLVED');
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-project-fact-snapshot-version'), '6');
  await activeRoute('workflow');
  assert.equal(await page.locator('[data-node-id="project_fact_confirm"]').getAttribute('data-runtime-status'), 'succeeded');
  assert.equal(await page.locator('[data-node-id="section_generate_pre_group"]').getAttribute('data-runtime-status'), 'invalidated');
  assert.equal(await page.locator('[data-node-id="quality_gate_final"]').getAttribute('data-runtime-status'), 'invalidated');
  await activeRoute('quality');
  assert.match(await page.locator('#projectFactQuality').textContent(), /Snapshot v6[\s\S]*INVALIDATED/);
});
