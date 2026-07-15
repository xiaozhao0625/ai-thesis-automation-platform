<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const context = computed(() => route.path.startsWith('/tasks/') ? '论文任务 / 当前任务' : 'AI 论文自动化生产平台')
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <RouterLink to="/dashboard" class="brand"><span class="brand-mark" />SPECTRUM LEDGER</RouterLink>
      <nav>
        <p>WORKSPACE</p>
        <RouterLink to="/dashboard"><span>◫</span>运营工作台</RouterLink>
        <RouterLink to="/tasks"><span>▤</span>论文任务</RouterLink>
        <RouterLink to="/approvals"><span>✓</span>待办审批</RouterLink>
        <hr />
        <p>GOVERNANCE</p>
        <RouterLink to="/tasks"><span>⌘</span>项目与材料</RouterLink>
        <hr />
        <p>SYSTEM</p>
        <RouterLink to="/system/workers"><span>◉</span>系统运行</RouterLink>
        <RouterLink to="/system/outbox"><span>≡</span>Outbox 事件</RouterLink>
      </nav>
      <div class="sidebar-foot"><span class="health-dot" />P1-1 本地环境</div>
    </aside>
    <main class="main-area">
      <header class="topbar"><span>{{ context }}</span><div class="topbar-actions"><span class="system-health"><i />系统健康</span><span class="avatar">运</span></div></header>
      <RouterView />
    </main>
  </div>
</template>
