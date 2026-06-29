// ── Backend entity types (mirror ops_intel_agent/schemas) ───────────────────

export interface Alert {
  id: number
  external_id: string | null
  server_ip: string | null
  host: string | null
  service: string | null
  severity: string
  raw_log: string
  error_message: string | null
  matched_knowledge_id: number | null
  similarity_score: number | null
  match_status: 'matched' | 'new_incident' | 'aggregated' | 'deposited' | string
  status: 'open' | 'resolved' | string
  ai_summary: string | null
  cluster_key: string | null
  created_at: string
}

export interface RetrievalHit {
  knowledge_id: number
  title: string
  similarity: number
  error_type: string | null
  user_guide: string | null
  engineer_guide: string | null
}

export interface ActionSpec {
  name: string
  label: string
  description: string
  risk_level: 'low' | 'medium' | 'high' | string
  params?: Record<string, string>
}

export interface DiagnosticReport {
  matched: boolean
  best_similarity: number
  plain_language: string
  user_actions: string
  engineer_guide: string
  suggested_actions: ActionSpec[]
  retrieval: RetrievalHit[]
  cluster_summary?: string | null
}

export interface AlertWithReport extends Alert {
  report: DiagnosticReport | null
}

export interface Knowledge {
  id: number
  error_type: string | null
  title: string
  raw_log_sample: string
  root_cause: string | null
  user_guide: string
  engineer_guide: string
  occurrence_count: number
  source: string
  tags: string[]
  confidence: number
  is_active: boolean
  created_at: string
}

export interface KnowledgeSearchHit extends Knowledge {
  similarity: number
}

export interface Stats {
  alerts: {
    total: number
    open: number
    resolved: number
    matched: number
    new_incident: number
  }
  knowledge: {
    total: number
    active: number
    vectors: number
  }
}

export interface ReadyInfo {
  status: string
  embedding_provider: string
  llm_provider: string
  vector_store: string
  notifier: string
  knowledge_vectors: number
}
