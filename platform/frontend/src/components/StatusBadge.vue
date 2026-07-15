<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ status: string }>()

const mapping: Record<string, { label: string; tone: string }> = {
  DRAFT: { label: '草稿', tone: 'neutral' },
  PENDING: { label: '待处理', tone: 'neutral' },
  READY: { label: '已就绪', tone: 'info' },
  QUEUED: { label: '队列中', tone: 'info' },
  RUNNING: { label: '运行中', tone: 'running' },
  WAITING_FOR_APPROVAL: { label: '待审批', tone: 'waiting' },
  APPROVED: { label: '已批准', tone: 'success' },
  SUCCEEDED: { label: '已完成', tone: 'success' },
  COMPLETED: { label: '已完成', tone: 'success' },
  PUBLISHED: { label: '已发布', tone: 'success' },
  ONLINE: { label: '在线', tone: 'success' },
  BUSY: { label: '执行中', tone: 'running' },
  RETRYING: { label: '重试中', tone: 'waiting' },
  BLOCKED: { label: '已阻断', tone: 'danger' },
  FAILED: { label: '失败', tone: 'danger' },
  REJECTED: { label: '已拒绝', tone: 'danger' },
  OFFLINE: { label: '离线', tone: 'neutral' },
}

const statusInfo = computed(() => mapping[props.status] ?? { label: props.status, tone: 'neutral' })
</script>

<template>
  <span class="status-badge" :class="`status--${statusInfo.tone}`">
    <span class="status-dot" />{{ statusInfo.label }}
  </span>
</template>
