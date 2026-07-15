<script setup lang="ts">
defineProps<{ taskId: string }>()
</script>

<template>
  <nav class="task-nav" aria-label="任务区域导航">
    <RouterLink :to="`/tasks/${taskId}/overview`">总览</RouterLink>
    <RouterLink :to="`/tasks/${taskId}/workflow`">工作流</RouterLink>
    <RouterLink :to="`/tasks/${taskId}/materials`">项目与材料</RouterLink>
  </nav>
</template>
