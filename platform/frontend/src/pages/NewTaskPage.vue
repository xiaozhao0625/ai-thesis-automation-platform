<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'

const router = useRouter()
const submitting = ref(false)
const error = ref('')
const form = reactive({
  title: '实验室设备管理系统',
  capability_pack: 'python_web_management_v1',
  source_mount_path: 'benchmark/ingest-fixture-v1',
  created_by: 'operator',
})

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    await api.createTask(form)
    await router.push('/approvals')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '创建任务失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="page page--narrow">
    <header class="page-heading"><div><p class="eyebrow">NEW TASK</p><h1>新建论文任务</h1><p>P1-1 仅允许受控基准资料与固定能力包。</p></div></header>
    <form class="form-panel" @submit.prevent="submit">
      <label>任务标题<input v-model="form.title" required maxlength="240" data-testid="task-title" /></label>
      <label>能力包<select v-model="form.capability_pack"><option value="python_web_management_v1">Python Web 管理系统 V1</option></select></label>
      <label>受控资料目录<select v-model="form.source_mount_path"><option value="benchmark/ingest-fixture-v1">标准基准夹具 · 128 文件</option></select><small>不会扫描历史论文库，也不会接触真实隐私资料。</small></label>
      <label>操作人<input v-model="form.created_by" required /></label>
      <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
      <div class="form-actions"><RouterLink class="button button--secondary" to="/tasks">取消</RouterLink><button class="button" type="submit" :disabled="submitting">{{ submitting ? '正在创建…' : '创建并提交启动审批' }}</button></div>
    </form>
  </section>
</template>
