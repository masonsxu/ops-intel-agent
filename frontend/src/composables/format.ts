// Small formatting helpers shared across views.

export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return '-'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  // YYYY-MM-DD HH:mm:ss
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

export function fmtDate(s: string | null | undefined): string {
  if (!s) return '-'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

// timestamp(ms) from NDatePicker -> 'YYYY-MM-DD'
export function tsToDate(ts: number | null): string | undefined {
  if (ts === null || ts === undefined) return undefined
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function pct(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-'
  return `${(n * 100).toFixed(1)}%`
}
