import axios from 'axios'
import type {
  Alert,
  AlertWithReport,
  Knowledge,
  KnowledgeSearchHit,
  ReadyInfo,
  Stats,
} from '@/types'

// Relative baseURL: in dev Vite proxies API paths to :8000, in prod the SPA is
// served by FastAPI on the same origin. Either way, relative URLs just work.
const http = axios.create({
  baseURL: '',
  timeout: 15000,
})

export interface AlertFilters {
  status?: string
  match_status?: string
  service?: string
  date?: string
  date_from?: string
  date_to?: string
  q?: string
  limit?: number
}

export const api = {
  async health(): Promise<{ status: string }> {
    const { data } = await http.get('/health')
    return data
  },

  async ready(): Promise<ReadyInfo> {
    const { data } = await http.get('/ready')
    return data
  },

  async stats(): Promise<Stats> {
    const { data } = await http.get('/stats')
    return data
  },

  // ── Alerts ───────────────────────────────────────────────────────────────
  async listAlerts(filters: AlertFilters = {}): Promise<Alert[]> {
    const { data } = await http.get<Alert[]>('/alerts', { params: filters })
    return data
  },

  async getAlert(id: number): Promise<AlertWithReport> {
    const { data } = await http.get<AlertWithReport>(`/alerts/${id}`)
    return data
  },

  // ── Knowledge ────────────────────────────────────────────────────────────
  async listKnowledge(filters: {
    date?: string
    date_from?: string
    date_to?: string
    error_type?: string
    q?: string
    limit?: number
  } = {}): Promise<Knowledge[]> {
    const { data } = await http.get<Knowledge[]>('/knowledge', { params: filters })
    return data
  },

  async searchKnowledge(q: string, k = 5): Promise<KnowledgeSearchHit[]> {
    const { data } = await http.get<KnowledgeSearchHit[]>('/knowledge/search', {
      params: { q, k },
    })
    return data
  },

  async getKnowledge(id: number): Promise<Knowledge> {
    const { data } = await http.get<Knowledge>(`/knowledge/${id}`)
    return data
  },

  async deleteKnowledge(id: number): Promise<void> {
    await http.delete(`/knowledge/${id}`)
  },
}

export default api
