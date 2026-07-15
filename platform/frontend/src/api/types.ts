export interface Task {
  id: string
  title: string
  status: string
  capability_pack: string
  source_mount_path: string
  created_by: string
  created_at: string
  updated_at: string
  task_start_approval_id?: string
  workflow_run_id?: string
}

export interface Approval {
  id: string
  task_id: string
  task_title: string
  approval_type: string
  status: string
  submitted_by: string
  decided_by: string | null
  decision: string | null
  comment: string | null
  submitted_at: string
  decided_at: string | null
}

export interface WorkflowNode {
  id: string
  workflow_run_id?: string
  node_key: string
  display_name: string
  status: string
  execution_fingerprint?: string | null
  attempt_count: number
  max_attempts: number
  current_output_count: number
  created_at?: string
  updated_at?: string
}

export interface Workflow {
  id: string
  task_id: string
  definition_version: string
  status: string
  started_at: string | null
  finished_at: string | null
  nodes: WorkflowNode[]
}

export interface Attempt {
  id: string
  attempt_number: number
  worker_id: string
  lease_id: string | null
  status: string
  started_at: string
  heartbeat_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
}

export interface NodeLog {
  sequence: number
  level: string
  event: string
  message: string
  details: Record<string, unknown>
  created_at: string
}

export interface IngestSummary {
  total_files: number
  accepted_files: number
  excluded_files: number
  quarantined_files: number
  duplicate_files: number
  needs_review_files: number
  issue_count: number
  manifest_status: string
  [key: string]: unknown
}

export interface ArtifactItem {
  artifact_id: string
  artifact_version_id: string
  output_role: string
  version: number
  filename: string
  content_hash: string
  media_type: string
  size_bytes: number
  created_at: string
  download_url: string
}

export interface WorkerItem {
  id: string
  status: string
  current_node_run_id: string | null
  heartbeat_at: string
  hostname: string
  process_id: number
}

export interface OutboxItem {
  id: string
  event_type: string
  aggregate_id: string
  status: string
  publish_attempt_count: number
  created_at: string
  published_at: string | null
  last_error: string | null
}

export interface Collection<T> {
  items: T[]
  total: number
}
