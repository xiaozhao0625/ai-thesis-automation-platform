const test = require('node:test');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const {createPrototypeServer} = require('./prototype.server.cjs');

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
async function confirmProjectFactIntake() {
  await page.locator('.nav-item[data-target="tasks"]').click();
  await activeClick('button[data-target="new-task"]');
  if (await page.locator('#projectFactIntake').getAttribute('data-fact-gate-state') === 'PENDING_CONFIRMATION') {
    await activeClick('button[data-action="confirm-intake-facts"]');
    await page.locator('#projectFactIntake[data-fact-gate-state="CONFIRMED"]').waitFor();
  }
}

test.before(async () => {
  server = createPrototypeServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'});
});
test.after(async () => { await browser?.close(); await new Promise(resolve => server?.close(resolve)); });
test.beforeEach(async () => { page = await browser.newPage({viewport: {width: 1440, height: 900}}); page.setDefaultTimeout(3000); await page.goto(origin); await page.locator('body[data-project-fact-ready="true"]').waitFor(); });
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
  await page.waitForTimeout(2600);
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

test('startup gate confirms API-backed ProjectFacts with source locators', async () => {
  await page.locator('.nav-item[data-target="tasks"]').click();
  await activeClick('button[data-target="new-task"]');
  assert.equal(await page.locator('#projectFactIntake').getAttribute('data-fact-gate-state'), 'PENDING_CONFIRMATION');
  const mcu = page.locator('#projectFactIntake [data-fact-key="mcu_model"]');
  assert.equal(await mcu.getAttribute('data-canonical-value'), 'STM32F103C8T6');
  const sourceText = await mcu.textContent();
  for (const source of ['任务书.docx', 'config.py', 'BOM.xlsx', 'hardware-list.png']) assert.match(sourceText, new RegExp(source.replace('.', '\\.')));
  const before = await page.evaluate(() => fetch('/api/project-facts').then(response => response.json()));
  assert.equal(before.snapshot, null);
  assert.equal(before.entities.fact_versions.length, 0);
  assert.equal(before.entities.facts.every(fact => fact.status === 'PROPOSED' && fact.current_fact_version_id === null), true);
  await activeClick('button[data-action="confirm-intake-facts"]');
  await page.locator('#projectFactIntake[data-fact-gate-state="CONFIRMED"]').waitFor();
  assert.equal(await page.locator('#projectFactIntake').getAttribute('data-fact-gate-state'), 'CONFIRMED');
  assert.equal(await page.locator('#projectFactIntake [data-fact-id]').evaluateAll(rows => rows.every(row => row.dataset.status === 'LOCKED' && row.dataset.locked === 'true')), true);
  const after = await page.evaluate(() => fetch('/api/project-facts').then(response => response.json()));
  assert.equal(after.snapshot.status, 'ACTIVE');
  assert.match(after.snapshot.snapshot_hash, /^sha256:/);
  assert.equal(after.entities.fact_versions.length > 0, true);
  assert.equal(after.human_approval.approval_type, 'PROJECT_FACT_INTAKE_CONFIRMATION');
  assert.equal(after.audit_event.event_type, 'PROJECT_FACT_INTAKE_CONFIRMED');
});

test('ProjectFactSnapshot preserves exact models across materials, outline, content, BOM, and quality', async () => {
  await confirmProjectFactIntake();
  await taskOverview();
  await activeRoute('materials');
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-project-fact-snapshot-version'), '5');
  assert.equal(await page.locator('#materialProjectFacts [data-fact-key="mcu_model"]').getAttribute('data-canonical-value'), 'STM32F103C8T6');
  assert.equal(await page.locator('#materialProjectFacts [data-fact-key="sensor_model"]').getAttribute('data-canonical-value'), 'DHT11');
  assert.equal(await page.locator('#materialProjectFacts [data-fact-key="wireless_model"]').getAttribute('data-canonical-value'), 'ESP8266-01S');
  await activeRoute('outline');
  assert.equal(await page.locator('#outlineProjectFacts').getAttribute('data-fact-gate-state'), 'WAITING_FOR_APPROVAL');
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
  await confirmProjectFactIntake();
  await taskOverview();
  await activeRoute('evidence');
  assert.equal(await page.locator('#projectFactRetrieval [data-match-type="EXACT_MODEL"]').count(), 1);
  assert.equal(await page.locator('#projectFactRetrieval [data-match-type="SERIES_MATCH"]').count(), 1);
  assert.equal(await page.locator('#projectFactRetrieval [data-match-type="RELATED_MODEL"]').count(), 1);
  assert.match(await page.locator('#projectFactRetrieval').textContent(), /"STM32F103C8T6" 官方数据手册[\s\S]*MODEL_PARAMETER_EVIDENCE/);
  const related = page.locator('#projectFactRetrieval [data-match-type="RELATED_MODEL"]');
  assert.equal(await related.getAttribute('data-evidence-role'), 'COMPARISON_ONLY');
  assert.match(await related.textContent(), /STM32F407VET6[\s\S]*不得支撑型号参数/);
});

test('conflict applies dependency closure before confirmation and creates a new ready outline run', async () => {
  await confirmProjectFactIntake();
  await taskOverview();
  await activeRoute('workflow');
  const oldFingerprint = await page.locator('[data-node-id="outline_plan"]').getAttribute('data-execution-fingerprint');
  await activeRoute('materials');
  await activeClick('button[data-action="simulate-fact-conflict"]');
  await page.locator('#materialProjectFacts[data-conflict-status="OPEN"]').waitFor();
  assert.match(await page.locator('#projectFactConflict').textContent(), /STM32F103C8T6[\s\S]*STM32F407VET6[\s\S]*系统未自动选择/);
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-project-fact-snapshot-status'), 'SUSPENDED');
  assert.equal(await page.locator('#materialProjectFacts [data-fact-key="mcu_model"]').getAttribute('data-status'), 'CONFLICT');
  assert.equal(await page.locator('#materialProjectFacts [data-fact-key="mcu_model"]').getAttribute('data-locked'), 'false');
  await activeRoute('overview');
  assert.match(await page.locator('section.page.active .alert').textContent(), /PROJECT_FACT_CONFLICT[\s\S]*依赖图/);
  await activeRoute('materials');
  await activeRoute('outline');
  assert.equal(await page.locator('#outlineProjectFacts').getAttribute('data-fact-gate-state'), 'BLOCKED');
  await activeRoute('content');
  assert.equal(await page.locator('#contentProjectFacts').getAttribute('data-fact-content-state'), 'INVALIDATED');
  assert.doesNotMatch(await page.locator('#contentProjectFacts').textContent(), /BOM 主控[\s\S]*一致/);
  await activeRoute('quality');
  assert.equal(await page.locator('#projectFactQuality [data-rule-id="PROJECT_FACT_CONFLICT"]').getAttribute('data-severity'), 'BLOCKING');
  await activeRoute('delivery');
  assert.equal(await page.locator('#projectFactDelivery').getAttribute('data-delivery-fact-state'), 'INVALIDATED');
  await activeRoute('workflow');
  assert.equal(await page.locator('[data-node-id="outline_plan"]').getAttribute('data-runtime-status'), 'invalidated');
  assert.equal(await page.locator('[data-node-id="section_generate_pre_group"]').getAttribute('data-runtime-status'), 'invalidated');
  assert.equal(await page.locator('[data-node-id="engineering_verify"]').getAttribute('data-runtime-status'), 'cancel_requested');
  assert.equal(await page.locator('[data-node-id="section_generate_ch6"]').getAttribute('data-runtime-status'), 'blocked');
  assert.equal(await page.locator('[data-node-id="delivery_approval"]').getAttribute('data-runtime-status'), 'invalidated');
  await activeRoute('materials');
  await activeClick('button[data-action="review-project-fact-impact"]');
  await page.locator('#modal').waitFor({state: 'visible'});
  assert.equal(await page.locator('#modal').getAttribute('class'), 'modal-layer show');
  assert.match(await page.locator('#modalList').textContent(), /将失效[\s\S]*将阻断[\s\S]*保持有效[\s\S]*Snapshot v6/);
  assert.equal(await page.locator('#modalConfirm').textContent(), '确认事实并使受影响下游失效');
  await page.locator('#modalConfirm').click();
  await page.locator('#materialProjectFacts[data-conflict-status="RESOLVED"]').waitFor();
  assert.equal(await page.locator('#materialProjectFacts').getAttribute('data-project-fact-snapshot-version'), '6');
  assert.match(await page.locator('#materialProjectFacts').textContent(), /ProjectFactVersion v3[\s\S]*已被替代[\s\S]*旧 Snapshot v5/);
  await activeRoute('workflow');
  assert.equal(await page.locator('[data-node-id="project_fact_confirm"]').getAttribute('data-runtime-status'), 'succeeded');
  assert.equal(await page.locator('[data-node-id="outline_plan"]').getAttribute('data-runtime-status'), 'ready');
  assert.equal(await page.locator('[data-node-id="outline_plan"]').getAttribute('data-prior-node-run-state'), 'INVALIDATED');
  assert.notEqual(await page.locator('[data-node-id="outline_plan"]').getAttribute('data-execution-fingerprint'), oldFingerprint);
});
