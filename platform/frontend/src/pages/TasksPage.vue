<script setup lang="ts">
import { onMounted } from 'vue'
import PageState from '../components/PageState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useTaskStore } from '../stores/tasks'
const store = useTaskStore()
onMounted(store.load)
</script>

<template>
  <section class="page">
    <header class="page-heading"><div><p class="eyebrow">TASKS</p><h1>论文任务</h1><p>所有任务均来自 PostgreSQL。</p></div><RouterLink class="button" to="/tasks/new">新建任务</RouterLink></header>
    <PageState :loading="store.loading" :error="store.error" :empty="!store.tasks.length" empty-text="尚未创建任务" @retry="store.load">
      <div class="table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>资料挂载</th><th>创建者</th><th>更新时间</th></tr></thead>
        <tbody><tr v-for="task in store.tasks" :key="task.id"><td><RouterLink :to="`/tasks/${task.id}/overview`"><strong>{{ task.title }}</strong></RouterLink><code>{{ task.id }}</code></td><td><StatusBadge :status="task.status" /></td><td><code>{{ task.source_mount_path }}</code></td><td>{{ task.created_by }}</td><td>{{ new Date(task.updated_at).toLocaleString() }}</td></tr></tbody>
      </table></div>
    </PageState>
  </section>
</template>
