<template>
  <n-layout has-sider position="absolute">
    <n-layout-sider
      bordered
      :width="220"
      :collapsed-width="64"
      collapse-mode="width"
      show-trigger="bar"
    >
      <div class="brand">
        <span class="logo">🛰️</span>
        <span v-if="!collapsed" class="title">Ops Intel</span>
      </div>
      <n-menu
        :value="activeKey"
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="20"
        :options="menuOptions"
        @update:value="onSelect"
      />
    </n-layout-sider>

    <n-layout>
      <n-layout-header bordered class="header">
        <div class="flex-between">
          <div>
            <div class="page-title">{{ currentTitle }}</div>
            <div class="page-subtitle">{{ currentSubtitle }}</div>
          </div>
          <n-space align="center" :size="12">
            <n-tag
              v-if="ready"
              :type="ready.status === 'ready' ? 'success' : 'warning'"
              round
              size="small"
            >
              {{ ready.vector_store }} · {{ ready.embedding_provider }}
            </n-tag>
            <n-tag v-else type="default" round size="small">连接中…</n-tag>
            <n-button quaternary circle @click="refreshAll" :loading="refreshing">
              <template #icon><n-icon>🔄</n-icon></template>
            </n-button>
          </n-space>
        </div>
      </n-layout-header>

      <n-layout-content class="content" :native-scrollbar="false">
        <div class="content-inner">
          <router-view />
        </div>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NIcon, type MenuOption } from 'naive-ui'
import { api } from '@/api/client'
import type { ReadyInfo } from '@/types'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)
const refreshing = ref(false)
const ready = ref<ReadyInfo | null>(null)

const activeKey = computed(() => route.name as string)

const menuOptions: MenuOption[] = [
  { label: '概览', key: 'dashboard', icon: () => h(NIcon, null, () => '📊') },
  { label: '告警消息', key: 'alerts', icon: () => h(NIcon, null, () => '🚨') },
  { label: '知识库', key: 'knowledge', icon: () => h(NIcon, null, () => '📚') },
  { type: 'divider' },
  { label: '设置', key: 'settings', icon: () => h(NIcon, null, () => '⚙️') },
]

const meta: Record<string, { title: string; sub: string }> = {
  dashboard: { title: '概览', sub: '系统健康度与告警/知识库一览' },
  alerts: { title: '告警消息', sub: '查看异常告警及其智能诊断报告' },
  knowledge: { title: '知识库', sub: '按日期精确检索 / 向量语义模糊搜索' },
  settings: { title: '设置', sub: 'API 密钥与后端配置' },
}

const currentTitle = computed(() => meta[route.name as string]?.title ?? '')
const currentSubtitle = computed(() => meta[route.name as string]?.sub ?? '')

function onSelect(key: string) {
  router.push({ name: key })
}

async function loadReady() {
  try {
    ready.value = await api.ready()
  } catch {
    ready.value = null
  }
}

async function refreshAll() {
  refreshing.value = true
  await loadReady()
  // small delay so the spinner is visible; views listen to route too.
  setTimeout(() => (refreshing.value = false), 300)
}

onMounted(loadReady)
</script>

<style scoped>
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  border-bottom: 1px solid var(--oia-border);
}
.brand .logo {
  font-size: 22px;
}
.brand .title {
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.5px;
}
.header {
  height: 72px;
  padding: 12px 24px;
  background: #fff;
}
.content {
  height: calc(100vh - 72px);
}
.content-inner {
  padding: 20px 24px 40px;
  max-width: 1280px;
  margin: 0 auto;
}
</style>
