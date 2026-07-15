<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { ArtifactItem, IngestSummary } from '../api/types'
import PageState from '../components/PageState.vue'
import TaskNav from '../components/TaskNav.vue'
const route = useRoute(); const taskId = String(route.params.taskId); const summary = ref<IngestSummary>(); const artifacts = ref<ArtifactItem[]>([]); const loading = ref(true); const error = ref('')
async function load() { loading.value = true; try { const [summaryResult, artifactResult] = await Promise.all([api.getIngestSummary(taskId), api.getIngestArtifacts(taskId)]); summary.value = summaryResult; artifacts.value = artifactResult.items; error.value = '' } catch (reason) { error.value = reason instanceof Error ? reason.message : '摄取结果尚不可用' } finally { loading.value = false } }
onMounted(load)
</script>

<template><section class="page"><header class="page-heading"><div><p class="eyebrow">MATERIAL INGEST</p><h1>项目与材料</h1><p>由 Ingest CLI 验证并归档的真实清单。</p></div></header><TaskNav :task-id="taskId" /><PageState :loading="loading" :error="error" @retry="load"><template v-if="summary"><div class="decision-grid"><div><span>ACCEPTED</span><strong>{{ summary.accepted_files }}</strong></div><div><span>EXCLUDED</span><strong>{{ summary.excluded_files }}</strong></div><div><span>QUARANTINED</span><strong>{{ summary.quarantined_files }}</strong></div><div><span>DUPLICATE</span><strong>{{ summary.duplicate_files }}</strong></div><div><span>NEEDS_REVIEW</span><strong>{{ summary.needs_review_files }}</strong></div></div><div class="section-heading"><h2>不可变产物版本</h2><span>{{ artifacts.length }} 项</span></div><div class="table-wrap"><table><thead><tr><th>输出角色</th><th>文件</th><th>版本</th><th>Hash</th><th>大小</th><th></th></tr></thead><tbody><tr v-for="item in artifacts" :key="item.artifact_version_id"><td><strong>{{ item.output_role }}</strong></td><td>{{ item.filename }}</td><td>v{{ item.version }}</td><td><code>{{ item.content_hash.slice(0, 24) }}…</code></td><td>{{ item.size_bytes.toLocaleString() }} B</td><td><a class="text-action" :href="api.downloadUrl(item.download_url)">下载</a></td></tr></tbody></table></div></template></PageState></section></template>
