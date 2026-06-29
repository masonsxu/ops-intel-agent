import type { TagProps } from 'naive-ui'

export interface StatusMeta {
  label: string
  type: TagProps['type']
}

// match_status on an alert
export function matchStatusMeta(s: string): StatusMeta {
  switch (s) {
    case 'matched':
      return { label: '命中历史', type: 'success' }
    case 'new_incident':
      return { label: '新增故障', type: 'warning' }
    case 'deposited':
      return { label: '已沉淀', type: 'info' }
    case 'aggregated':
      return { label: '已聚合', type: 'default' }
    default:
      return { label: s, type: 'default' }
  }
}

// alert.status (open / resolved)
export function alertStatusMeta(s: string): StatusMeta {
  switch (s) {
    case 'open':
      return { label: '待处理', type: 'error' }
    case 'resolved':
      return { label: '已解决', type: 'success' }
    default:
      return { label: s, type: 'default' }
  }
}

export function severityMeta(s: string): StatusMeta {
  switch ((s || '').toUpperCase()) {
    case 'FATAL':
    case 'CRITICAL':
    case 'PANIC':
      return { label: s, type: 'error' }
    case 'ERROR':
    case 'ERR':
      return { label: s, type: 'warning' }
    case 'WARN':
    case 'WARNING':
      return { label: s, type: 'info' }
    default:
      return { label: s, type: 'default' }
  }
}
