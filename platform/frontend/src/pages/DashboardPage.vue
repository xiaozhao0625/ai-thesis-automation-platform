<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '../api/client'
import type { Approval, Task, WorkerItem } from '../api/types'
import PageState from '../components/PageState.vue'
import StatusBadge from '../components/StatusBadge.vue'

const loading = ref(true)
const error = ref('')
const tasks = ref<Task[]>([])
const approvals = ref<Approval[]>([])
const workers = ref<WorkerItem[]>([])
const running = computed(() => tasks.value.filter((task) => task.status === 'RUNNING').length)
const blocked = computed(() => tasks.value.filter((task) => ['BLOCKED', 'FAILED'].includes(task.status)).length)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [taskResult, approvalResult, workerResult] = await Promise.all([
      api.listTasks(),
      api.listApprovals(),
      api.listWorkers(),
    ])
    tasks.value = taskResult.items
    approvals.value = approvalResult.items
    workers.value = workerResult.items
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '无法读取运营数据'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-heading">
      <div><p class="eyebrow">OPERATIONS</p><h1>运营工作台</h1><p>任务、审批与执行资源的真实运行状态。</p></div>
      <RouterLink class="button" to="/tasks/new">新建论文任务</RouterLink>
    </header>
    <PageState :loading="loading" :error="error" @retry="load">
      <div class="metric-strip">
        <div><span>全部任务</span><strong>{{ tasks.length }}</strong></div>
        <div><span>待审批</span><strong>{{ approvals.filter((item) => item.status === 'PENDING').length }}</strong></div>
        <div><span>运行中</span><strong>{{ running }}</strong></div>
        <div><span>阻断 / 失败</span><strong>{{ blocked }}</strong></div>
        <div><span>在线 Worker</span><strong>{{ workers.filter((item) => item.status !== 'OFFLINE').length }}</strong></div>
      </div>
      <div class="section-heading"><h2>最近任务</h2><RouterLink to="/tasks">查看全部</RouterLink></div>
      <div class="table-wrap">
        <table><thead><tr><th>任务</th><th>状态</th><th>能力包</th><th>创建时间</th></tr></thead>
          <tbody><tr v-for="task in tasks.slice(0, 8)" :key="task.id">
            <td><RouterLink :to="`/tasks/${task.id}/overview`"><strong>{{ task.title }}</strong></RouterLink><code>{{ task.id }}</code></td>
            <td><StatusBadge :status="task.status" /></td><td>{{ task.capability_pack }}</td><td>{{ new Date(task.created_at).toLocaleString() }}</td>
          </tr></tbody></table>
      </div>
    </PageState>
  </section>
</template>
