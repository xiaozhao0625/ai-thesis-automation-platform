import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';

const files = await readdir(new URL('.', import.meta.url));
const htmlName = files.find(name => name.endsWith('.html'));
assert.ok(htmlName, 'missing prototype HTML file');
const file = new URL(`./${htmlName}`, import.meta.url);
const html = await readFile(file, 'utf8');
const projectFactPayload = JSON.parse(await readFile(new URL('./project-fact-r6.json', import.meta.url), 'utf8'));
const server = await readFile(new URL('./prototype.server.cjs', import.meta.url), 'utf8');

const pages = [
  'dashboard', 'tasks', 'new-task', 'overview', 'workflow', 'inspector', 'evidence',
  'content', 'engineering', 'quality', 'templates', 'delivery', 'approvals',
  'materials', 'outline', 'components', 'benchmarks', 'workers', 'model-calls', 'audit'
];

for (const page of pages) {
  if (page === 'inspector') {
    assert.match(html, /id="inspector"/, 'missing node inspector page');
  } else {
    assert.match(html, new RegExp(`data-page="${page}"`), `missing page: ${page}`);
  }
}
assert.match(html, /data-page="components"/, 'missing component state library');

for (const id of ['create-task', 'outline-impact', 'deadletter-recover', 'quality-recheck', 'quality-complete', 'delivery-approve']) {
  assert.match(html, new RegExp(`data-action="${id}"`), `missing core interaction: ${id}`);
}

assert.match(html, /--domain-engineering:\s*#16825D/i, 'engineering domain token missing');
assert.match(html, /Attempt 2\/3/, 'Attempt denominator must be 3');
assert.doesNotMatch(html, /Attempt 3\/5/, 'obsolete retry sample must not reappear');
assert.match(html, /修订轮次 2\/2/, 'revision round limit missing');
for (const id of ['recoveryNodeRun', 'reviewRunState', 'deliveryApprovalDetail', 'deliveryPackageStatus', 'officialDownload']) {
  assert.match(html, new RegExp(`(?:id\\s*=|\\.id=)["']${id}["']|#${id}`), `missing v1.2.1 interaction target: ${id}`);
}
assert.match(html, /page\[data-page="approvals"\] \.panel-grid\{padding-bottom:88px/, 'approval safety area missing');
assert.doesNotMatch(html, /workflowInvalidationResult/, 'duplicate invalidation result panel must not return');
assert.match(html, /<svg class="wf-svg"/, 'workflow edges must use SVG');
assert.match(html, /data-node-id=/, 'workflow nodes must expose stable node identities');
assert.match(html, /data-source-port=/, 'SVG edges must bind source ports');
assert.match(html, /data-target-port=/, 'SVG edges must bind target ports');
assert.match(html, /task-subnav/, 'shared TaskSubNavigation component missing');
assert.match(html, /history\[replace\?'replaceState':'pushState'\]/, 'History API routing missing');
assert.match(html, /toggle-chapter-group/, 'collapsed chapter group control missing');
assert.match(html, /v1\.2\.4-P0-r6 ProjectFact 闭环修复候选/, 'r6 candidate title missing');

const semanticEdges = [
  ['task_start_approval', 'project_source_parse'],
  ['project_source_parse', 'project_fact_confirm'],
  ['project_fact_confirm', 'outline_plan'],
  ['outline_plan', 'section_generate_pre_group'],
  ['section_generate_pre_group', 'engineering_verify'],
  ['engineering_verify', 'section_generate_ch6'],
  ['section_generate_ch6', 'section_generate_ch7'],
  ['section_generate_ch7', 'manuscript_quality_check'],
  ['manuscript_quality_check', 'quality_gate_final'],
  ['quality_gate_final', 'docx_render'],
  ['docx_render', 'delivery_approval']
];
for (const [source, target] of semanticEdges) {
  assert.match(html, new RegExp(`(?:horizontal|vertical)\\('${source}','${target}'\\)`), `missing semantic edge: ${source} -> ${target}`);
}
assert.match(html, /\['start','启动','workflow'\].*\['preproduce','前置生产','content'\].*\['engineering','工程验证','engineering'\].*\['postproduce','后置生产','content'\].*\['delivery','交付','delivery'\]/s, 'eight-stage workflow order missing');

for (const route of ['/dashboard', '/tasks', '/approvals', '/benchmarks', '/templates', '/system/workers', '/system/model-calls', '/system/audit']) {
  assert.ok(html.includes(`'${route}'`), `missing formal route: ${route}`);
}
assert.match(html, /workflow:\['node','attempt'\]/, 'workflow query allowlist missing');
assert.match(html, /materials:\['asset','parser'\]/, 'materials query allowlist missing');
assert.match(html, /evidence:\['claim','source'\]/, 'evidence query allowlist missing');
assert.match(html, /content:\['chapter','claim','version'\]/, 'content query allowlist missing');
assert.match(html, /pageName==='workflow'\?new URL\(location\.href\)\.searchParams\.get\('node'\):null/, 'inspector must be scoped to workflow route');
assert.doesNotMatch(html, /searchParams\.set\('taskId'/, 'taskId must not leak into page query state');

for (const marker of ['PROJECT_FACT_CONFLICT', 'FACT_CONSTRAINT_VIOLATION', 'INVALIDATED_TO_READY']) {
  assert.ok(html.includes(marker), `missing ProjectFact marker: ${marker}`);
}
for (const action of ['simulate-fact-conflict', 'review-project-fact-impact', 'confirm-intake-facts', 'view-fact-source']) {
  assert.match(html, new RegExp(`data-action=["']${action}["']|dataset\\.action=["']${action}["']`), `missing ProjectFact interaction: ${action}`);
}
assert.match(html, /公开资料决定内容丰富度；用户锁定事实决定项目真实性/, 'source authority principle missing');
assert.doesNotMatch(html, /const facts=\[/, 'ProjectFact data must not be hardcoded in HTML');
assert.doesNotMatch(html, /snapshotVersion\s*\+=\s*1/, 'snapshot versions must come from the executable candidate');
for (const endpoint of ['/api/project-facts', '/api/project-facts/confirm-intake', '/api/project-facts/conflict', '/api/project-facts/impact', '/api/project-facts/confirm']) {
  assert.ok(server.includes(endpoint), `missing ProjectFact API endpoint: ${endpoint}`);
}
assert.match(server, /resolveConflictWithExecutable/, 'conflict confirmation must invoke the executable candidate');
assert.match(server, /readJsonBody/, 'conflict confirmation must read the request body');
assert.match(server, /project_fact_r6\.cli/, 'server must invoke the r6 executable candidate');
const generatedOutputs = projectFactPayload.intake_confirmation.generated_outputs;
assert.ok(generatedOutputs.every(item => typeof item.content === 'string'), 'all fact-bound outputs must use content');
assert.ok(generatedOutputs.every(item => item.fact_bindings.rtc_model?.canonical_value === 'DS3231'), 'dynamic rtc_model binding missing');
assert.ok(generatedOutputs.every(item => !('text' in item)), 'obsolete text field must not return');
assert.match(html, /conflictCandidate/, 'conflict confirmation must allow a candidate selection');
assert.match(html, /conflictReason/, 'conflict confirmation must collect a reason');
assert.match(html, /conflictApprover/, 'conflict confirmation must collect an approver');
assert.equal(projectFactPayload.initial.snapshot, null, 'initial intake must not pre-create an ACTIVE Snapshot');
assert.equal(projectFactPayload.initial.entities.fact_versions.length, 0, 'initial intake must not pre-create ProjectFactVersion objects');
assert.ok(projectFactPayload.initial.entities.facts.every(item => item.status === 'PROPOSED' && item.current_fact_version_id === null), 'initial facts must remain PROPOSED');
const intakeMcu = projectFactPayload.intake_confirmation.entities.fact_versions.find(item => item.fact_key === 'mcu_model');
assert.equal(intakeMcu.canonical_value, 'STM32F103C8T6');
assert.equal(projectFactPayload.intake_confirmation.snapshot.status, 'ACTIVE');
assert.equal(projectFactPayload.intake_confirmation.human_approval.approval_type, 'PROJECT_FACT_INTAKE_CONFIRMATION');
assert.equal(projectFactPayload.intake_confirmation.audit_event.event_type, 'PROJECT_FACT_INTAKE_CONFIRMED');
assert.deepEqual(projectFactPayload.intake_confirmation.retrieval.map(item => item.match_type), ['EXACT_MODEL', 'SERIES_MATCH', 'RELATED_MODEL']);
assert.ok(projectFactPayload.intake_confirmation.generated_outputs.every(output =>
  ['PROJECT_FACT_OUTPUT', 'PROJECT_IMPLEMENTATION'].includes(output.resolved_context_role)
  && output.fact_bindings.mcu_model.canonical_value === 'STM32F103C8T6'
), 'generated outputs must carry server-resolved ProjectFact bindings');
assert.equal(projectFactPayload.conflict.project_fact_conflict.status, 'OPEN');
assert.equal(projectFactPayload.conflict.snapshot.status, 'SUSPENDED');
const conflictedMcu = projectFactPayload.conflict.entities.facts.find(item => item.fact_key === 'mcu_model');
assert.equal(conflictedMcu.current_fact_version_id, null);
assert.equal(conflictedMcu.last_locked_fact_version_id, 'fact-mcu-model-v2');
assert.equal(projectFactPayload.conflict.snapshot_status_transition.from_status, 'ACTIVE');
assert.equal('historical_snapshot' in projectFactPayload.conflict, false);
assert.equal(projectFactPayload.confirmation.outline_transition.old_state, 'INVALIDATED');
assert.equal(projectFactPayload.confirmation.outline_transition.new_state, 'READY');
assert.equal(projectFactPayload.confirmation.human_approval.approval_type, 'PROJECT_FACT_CONFLICT_RESOLUTION');
assert.equal(projectFactPayload.confirmation.audit_event.event_type, 'PROJECT_FACT_CONFLICT_RESOLVED');
