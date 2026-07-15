<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { Approval } from '../api/types'
import PageState from '../components/PageState.vue'
import StatusBadge from '../components/StatusBadge.vue'

const approvals = ref<Approval[]>([])
const loading = ref(true)
const error = ref('')
const deciding = ref('')
async function load() { loading.value = true; error.value = ''; try { approvals.value = (await api.listApprovals()).items } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取审批失败' } finally { loading.value = false } }
async function decide(item: Approval, decision: 'APPROVE' | 'REJECT') { deciding.value = item.id; try { await api.decideApproval(item.id, decision, decision === 'APPROVE' ? '资料范围确认' : '资料范围不符合要求'); await load() } catch (reason) { error.value = reason instanceof Error ? reason.message : '审批失败' } finally { deciding.value = '' } }
onMounted(load)
</script>

<template>
  <section class="page"><header class="page-heading"><div><p class="eyebrow">APPROVALS</p><h1>人工审批中心</h1><p>本阶段仅处理 TASK_START 启动确认。</p></div></header>
    <PageState :loading="loading" :error="error" :empty="!approvals.length" empty-text="暂无审批" @retry="load">
      <div class="approval-list"><article v-for="item in approvals" :key="item.id" class="approval-row"><div><span class="label">{{ item.approval_type }}</span><h2>{{ item.task_title }}</h2><code>{{ item.task_id }}</code><p>提交人 {{ item.submitted_by }} · {{ new Date(item.submitted_at).toLocaleString() }}</p></div><StatusBadge :status="item.status" /><div class="row-actions" v-if="item.status === 'PENDING'"><button class="button button--danger-quiet" :disabled="deciding === item.id" @click="decide(item, 'REJECT')">拒绝</button><button class="button" :disabled="deciding === item.id" data-testid="approve-task" @click="decide(item, 'APPROVE')">批准启动</button></div><RouterLink v-else :to="`/tasks/${item.task_id}/workflow`">查看工作流</RouterLink></article></div>
    </PageState>
  </section>
</template>
