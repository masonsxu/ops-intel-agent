<template>
  <n-spin :show="loading">
    <n-grid cols="2 s:3 m:6" responsive="screen" :x-gap="12" :y-gap="12">
      <n-gi>
        <StatCard label="告警总数" :value="stats?.alerts.total ?? 0" icon="🚨" tone="#3358d4" />
      </n-gi>
      <n-gi>
        <StatCard label="待处理" :value="stats?.alerts.open ?? 0" icon="⏳" tone="#d4380d" />
      </n-gi>
      <n-gi>
        <StatCard label="命中历史" :value="stats?.alerts.matched ?? 0" icon="✅" tone="#389e0d" />
      </n-gi>
      <n-gi>
        <StatCard label="新增故障" :value="stats?.alerts.new_incident ?? 0" icon="🆕" tone="#d48806" />
      </n-gi>
      <n-gi>
        <StatCard label="知识库条目" :value="stats?.knowledge.active ?? 0" icon="📚" tone="#531dab" />
      </n-gi>
      <n-gi>
        <StatCard label="向量数" :value="stats?.knowledge.vectors ?? 0" icon="🧠" tone="#08979c" />
      </n-gi>
    </n-grid>

    <n-grid cols="1 m:2" responsive="screen" :x-gap="16" :y-gap="16" style="margin-top: 16px">
      <n-gi>
        <n-card title="后端就绪状态" size="small" class="section-card">
          <n-descriptions v-if="ready" label-placement="left" :column="1" size="small" bordered>
            <n-descriptions-item label="状态">
              <n-tag :type="ready.status === 'ready' ? 'success' : 'warning'" size="small">
                {{ ready.status }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="Embedding">{{ ready.embedding_provider }}</n-descriptions-item>
            <n-descriptions-item label="LLM">{{ ready.llm_provider }}</n-descriptions-item>
            <n-descriptions-item label="向量库">{{ ready.vector_store }}</n-descriptions-item>
            <n-descriptions-item label="通知器">{{ ready.notifier }}</n-descriptions-item>
          </n-descriptions>
          <n-empty v-else description="无法连接后端，请确认 API 已启动" />
        </n-card>
      </n-gi>
      <n-gi>
        <n-card title="最近告警" size="small" class="section-card">
          <template #header-extra>
            <n-button text type="primary" @click="$router.push('/alerts')">查看全部 →</n-button>
          </template>
          <n-empty v-if="!recent.length" description="暂无告警" />
          <n-list v-else hoverable clickable @click="$router.push('/alerts')">
            <n-list-item v-for="a in recent" :key="a.id">
              <n-thing>
                <template #header>
                  <n-space align="center" :size="8">
                    <n-tag :type="matchStatusMeta(a.match_status).type" size="tiny">
                      {{ matchStatusMeta(a.match_status).label }}
                    </n-tag>
                    <span>{{ a.service || a.host || '未知服务' }}</span>
                    <span class="muted" style="font-size: 12px">{{ fmtDateTime(a.created_at) }}</span>
                  </n-space>
                </template>
                <div class="recent-log">{{ a.raw_log }}</div>
              </n-thing>
            </n-list-item>
          </n-list>
        </n-card>
      </n-gi>
    </n-grid>
  </n-spin>
</template>

<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { NStatistic } from 'naive-ui'
import { api } from '@/api/client'
import type { Alert, ReadyInfo, Stats } from '@/types'
import { fmtDateTime } from '@/composables/format'
import { matchStatusMeta } from '@/composables/status'

const loading = ref(false)
const stats = ref<Stats | null>(null)
const ready = ref<ReadyInfo | null>(null)
const recent = ref<Alert[]>([])

// Local stat card built on NStatistic to keep the template tidy.
const StatCard = (props: { label: string; value: number; icon: string; tone: string }) =>
  h(
    'div',
    {
      style: {
        background: '#fff',
        borderRadius: '8px',
        padding: '16px',
        border: '1px solid var(--oia-border)',
        borderTop: `3px solid ${props.tone}`,
        height: '100%',
      },
    },
    [
      h('div', { style: { display: 'flex', alignItems: 'center', gap: '8px' } }, [
        h('span', { style: { fontSize: '18px' } }, props.icon),
        h('span', { class: 'muted', style: { fontSize: '13px' } }, props.label),
      ]),
      h(NStatistic, { value: props.value }),
    ],
  )

async function load() {
  loading.value = true
  try {
    const [s, r, a] = await Promise.all([api.stats(), api.ready().catch(() => null), api.listAlerts({ limit: 5 })])
    stats.value = s
    ready.value = r
    recent.value = a
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.recent-log {
  font-family: 'FiraCode', monospace;
  font-size: 12.5px;
  color: #4b5260;
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
