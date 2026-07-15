<script setup lang="ts">
import type { WorkflowNode } from '../api/types'
import StatusBadge from './StatusBadge.vue'

defineProps<{ node: WorkflowNode; selected?: boolean }>()
defineEmits<{ select: [node: WorkflowNode] }>()
</script>

<template>
  <button
    class="workflow-node"
    :class="[{ 'workflow-node--selected': selected }, `node-${node.node_key}`]"
    type="button"
    :data-testid="`node-${node.node_key}`"
    @click="$emit('select', node)"
  >
    <div class="node-head">
      <strong>{{ node.display_name }}</strong>
      <StatusBadge :status="node.status" />
    </div>
    <code>{{ node.node_key }}</code>
    <div class="node-meta">
      <span>Attempt {{ node.attempt_count }} / {{ node.max_attempts }}</span>
      <span>{{ node.current_output_count }} 个产物</span>
    </div>
  </button>
</template>
