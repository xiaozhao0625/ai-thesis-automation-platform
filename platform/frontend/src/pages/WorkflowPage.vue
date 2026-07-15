<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { Attempt, NodeLog, Workflow, WorkflowNode } from '../api/types'
import PageState from '../components/PageState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TaskNav from '../components/TaskNav.vue'
import WorkflowNodeCard from '../components/WorkflowNode.vue'
const route = useRoute(); const taskId = String(route.params.taskId)
const workflow = ref<Workflow>(); const selected = ref<WorkflowNode>(); const attempts = ref<Attempt[]>([]); const logs = ref<NodeLog[]>([]); const loading = ref(true); const error = ref(''); let timer: number | undefined
async function load(silent = false) { if (!silent) loading.value = true; try { workflow.value = await api.getWorkflow(taskId); selected.value = workflow.value.nodes.find((node) => node.id === selected.value?.id) ?? workflow.value.nodes[1]; error.value = '' } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取工作流失败' } finally { loading.value = false } }
async function loadInspector(node?: WorkflowNode) { if (!node) return; const [attemptResult, logResult] = await Promise.all([api.getAttempts(node.id), api.getLogs(node.id)]); attempts.value = attemptResult.items; logs.value = logResult.items }
watch(selected, loadInspector)
onMounted(async () => { await load(); timer = window.setInterval(() => load(true), 1000) })
onBeforeUnmount(() => timer && window.clearInterval(timer))
</script>

<template><section class="page page--workflow"><PageState :loading="loading" :error="error" @retry="() => load()"><template v-if="workflow"><header class="page-heading"><div><p class="eyebrow">WORKFLOW RUN</p><h1>工作流全景</h1><code>WorkflowRun #{{ workflow.id }}</code></div><StatusBadge :status="workflow.status" /></header><TaskNav :task-id="taskId" />
  <div class="workflow-layout"><div class="workflow-canvas"><div class="phase-rail"><span>启动</span><span>执行</span><span>人工治理</span></div><div class="node-chain"><template v-for="(node, index) in workflow.nodes" :key="node.id"><WorkflowNodeCard :node="node" :selected="selected?.id === node.id" @select="selected = $event" /><span v-if="index < workflow.nodes.length - 1" class="connector">→</span></template></div><p class="canvas-note">状态每秒从真实后端刷新；点击节点查看 Attempt、Lease 与日志。</p></div>
    <aside class="inspector" v-if="selected"><div class="inspector-head"><div><span class="label">NODE INSPECTOR</span><h2>{{ selected.display_name }}</h2><code>{{ selected.node_key }}</code></div><StatusBadge :status="selected.status" /></div><dl><div><dt>Attempt</dt><dd>{{ selected.attempt_count }} / {{ selected.max_attempts }}</dd></div><div><dt>当前产物</dt><dd>{{ selected.current_output_count }}</dd></div><div><dt>执行指纹</dt><dd><code>{{ selected.execution_fingerprint ?? '—' }}</code></dd></div></dl><h3>执行尝试</h3><div class="attempt-list" v-if="attempts.length"><article v-for="attempt in attempts" :key="attempt.id"><div><strong>Attempt {{ attempt.attempt_number }}</strong><StatusBadge :status="attempt.status" /></div><code>{{ attempt.worker_id }}</code><small>Lease {{ attempt.lease_id ?? '—' }}</small><p v-if="attempt.error_code" class="inline-error">{{ attempt.error_code }} · {{ attempt.error_message }}</p></article></div><p v-else class="muted">尚无 Worker Attempt。</p><h3>实时日志</h3><div class="log-view"><p v-for="log in logs" :key="log.sequence"><span>{{ String(log.sequence).padStart(2, '0') }}</span> {{ log.event }} · {{ log.message }}</p><p v-if="!logs.length">等待节点日志…</p></div></aside>
  </div></template></PageState></section></template>
