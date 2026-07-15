import type {
  Approval,
  ArtifactItem,
  Attempt,
  Collection,
  IngestSummary,
  NodeLog,
  OutboxItem,
  Task,
  WorkerItem,
  Workflow,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId?: string,
    public status?: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      accept: 'application/json',
      ...(init?.body ? { 'content-type': 'application/json' } : {}),
      ...init?.headers,
    },
  })
  const isJson = response.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await response.json() : null
  if (!response.ok) {
    const error = body?.error
    throw new ApiError(
      error?.code ?? 'HTTP_ERROR',
      error?.message ?? `HTTP ${response.status}`,
      error?.request_id,
      response.status,
    )
  }
  return body as T
}

export interface CreateTaskInput {
  title: string
  capability_pack: string
  source_mount_path: string
  created_by: string
}

export const api = {
  health: () => request<{ status: string; database: string; redis: string }>('/api/system/health'),
  listTasks: () => request<Collection<Task>>('/api/tasks'),
  getTask: (id: string) => request<Task>(`/api/tasks/${id}`),
  createTask: (payload: CreateTaskInput) =>
    request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify(payload) }),
  listApprovals: () => request<Collection<Approval>>('/api/approvals'),
  decideApproval: (id: string, decision: 'APPROVE' | 'REJECT', comment = '') =>
    request<Approval>(`/api/approvals/${id}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision, decided_by: 'operator', comment }),
    }),
  getWorkflow: (taskId: string) => request<Workflow>(`/api/tasks/${taskId}/workflow`),
  getAttempts: (nodeId: string) =>
    request<Collection<Attempt>>(`/api/node-runs/${nodeId}/attempts`),
  getLogs: (nodeId: string) => request<Collection<NodeLog>>(`/api/node-runs/${nodeId}/logs`),
  getIngestSummary: (taskId: string) =>
    request<IngestSummary>(`/api/tasks/${taskId}/ingest/summary`),
  getIngestArtifacts: (taskId: string) =>
    request<Collection<ArtifactItem>>(`/api/tasks/${taskId}/ingest/artifacts`),
  listWorkers: () => request<Collection<WorkerItem>>('/api/system/workers'),
  listOutbox: () => request<Collection<OutboxItem> & { pending: number }>('/api/system/outbox'),
  downloadUrl: (path: string) => `${API_BASE}${path}`,
}
