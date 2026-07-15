<script setup lang="ts">
defineProps<{ loading?: boolean; error?: string; empty?: boolean; emptyText?: string }>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <div v-if="loading" class="page-state" role="status">正在读取真实平台状态…</div>
  <div v-else-if="error" class="page-state page-state--error" role="alert">
    <strong>读取失败</strong><span>{{ error }}</span>
    <button type="button" class="button button--secondary" @click="$emit('retry')">重试</button>
  </div>
  <div v-else-if="empty" class="page-state"><span>{{ emptyText ?? '暂无数据' }}</span></div>
  <slot v-else />
</template>
