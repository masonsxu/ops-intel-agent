import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Dev: the SPA runs on Vite (5174) and proxies API calls to the FastAPI
// backend on :8000. Prod: the built bundle is served by FastAPI itself at "/",
// so all requests are same-origin and no proxy is needed.
const API_TARGET = process.env.OIA_API_URL || 'http://127.0.0.1:8000'
const apiPaths = [
  '/alerts',
  '/knowledge',
  '/actions',
  '/stats',
  '/health',
  '/ready',
]

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5174,
    proxy: Object.fromEntries(
      apiPaths.map((p) => [
        p,
        { target: API_TARGET, changeOrigin: true },
      ]),
    ),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
