import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '../api/client'
import type { Task } from '../api/types'

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const loading = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      tasks.value = (await api.listTasks()).items
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '读取任务失败'
    } finally {
      loading.value = false
    }
  }

  return { tasks, loading, error, load }
})
