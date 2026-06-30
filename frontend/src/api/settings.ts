export interface AppSettings {
  openai_api_key: string
  openai_base_url: string
  embedding_model: string
  llm_model: string
}

const DEFAULT_SETTINGS: AppSettings = {
  openai_api_key: '',
  openai_base_url: 'https://api.openai.com/v1',
  embedding_model: 'text-embedding-3-small',
  llm_model: 'gpt-4o-mini',
}

let cached: AppSettings | null = null

// Tauri v2 injects `__TAURI_INTERNALS__` into every webview; the legacy
// `__TAURI__` global only exists when `app.withGlobalTauri` is enabled, so we
// test for the internals handle which is always present inside the desktop app.
export const isTauri = (): boolean => {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

export const settingsApi = {
  async get(): Promise<AppSettings> {
    const isTauriApp = isTauri()
    if (isTauriApp) {
      const { invoke } = await import('@tauri-apps/api/core')
      cached = await invoke<AppSettings>('get_settings')
      return cached!
    }
    return cached ?? DEFAULT_SETTINGS
  },

  async save(settings: AppSettings): Promise<void> {
    cached = settings
    const isTauriApp = isTauri()
    if (isTauriApp) {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('save_settings', { settings })
    } else {
      localStorage.setItem('oia_settings', JSON.stringify(settings))
    }
  },

  async restartBackend(): Promise<void> {
    const isTauriApp = isTauri()
    if (isTauriApp) {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('restart_backend')
    }
  },
}
