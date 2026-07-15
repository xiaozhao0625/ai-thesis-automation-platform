<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError, api } from '../api/client'
import type { IngestSummary, Task, Workflow } from '../api/types'
import PageState from '../components/PageState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TaskNav from '../components/TaskNav.vue'
const route = useRoute(); const taskId = String(route.params.taskId)
const task = ref<Task>(); const workflow = ref<Workflow>(); const summary = ref<IngestSummary>(); const loading = ref(true); const error = ref('')
async function load() { loading.value = true; error.value = ''; try { task.value = await api.getTask(taskId); workflow.value = await api.getWorkflow(taskId); try { summary.value = await api.getIngestSummary(taskId) } catch (reason) { if (!(reason instanceof ApiError && reason.status === 404)) throw reason } } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取任务失败' } finally { loading.value = false } }
onMounted(load)
</script>

<template><section class="page"><PageState :loading="loading" :error="error" @retry="load"><template v-if="task && workflow"><header class="page-heading task-heading"><div><p class="eyebrow">TASK OVERVIEW</p><h1>{{ task.title }}</h1><code>{{ task.id }}</code></div><StatusBadge :status="task.status" /></header><TaskNav :task-id="taskId" />
  <div class="summary-grid"><section><span>工作流版本</span><strong>{{ workflow.definition_version }}</strong></section><section><span>资料挂载</span><strong>{{ task.source_mount_path }}</strong></section><section><span>Manifest</span><strong>{{ summary?.manifest_status ?? '尚未生成' }}</strong></section></div>
  <div class="section-heading"><h2>固定工作流</h2><RouterLink :to="`/tasks/${taskId}/workflow`">打开节点检查器</RouterLink></div><ol class="timeline"><li v-for="node in workflow.nodes" :key="node.id"><StatusBadge :status="node.status" /><div><strong>{{ node.display_name }}</strong><code>{{ node.node_key }}</code></div></li></ol>
</template></PageState></section></template>
