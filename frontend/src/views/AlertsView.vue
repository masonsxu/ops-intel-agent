<template>
  <n-card size="small" class="section-card">
    <n-form inline :show-feedback="false" label-placement="left">
      <n-form-item label="关键词">
        <n-input
          v-model:value="filters.q"
          placeholder="搜索 raw log / 错误信息"
          clearable
          style="width: 220px"
          @keydown.enter="load"
        />
      </n-form-item>
      <n-form-item label="处理状态">
        <n-select
          v-model:value="filters.status"
          :options="statusOptions"
          placeholder="全部"
          clearable
          style="width: 140px"
        />
      </n-form-item>
      <n-form-item label="匹配">
        <n-select
          v-model:value="filters.match_status"
          :options="matchOptions"
          placeholder="全部"
          clearable
          style="width: 140px"
        />
      </n-form-item>
      <n-form-item label="服务">
        <n-input
          v-model:value="filters.service"
          placeholder="service="
          clearable
          style="width: 140px"
          @keydown.enter="load"
        />
      </n-form-item>
      <n-form-item label="日期(精确)">
        <n-date-picker
          v-model:formatted-value="filters.date"
          type="date"
          value-format="yyyy-MM-dd"
          clearable
          style="width: 170px"
        />
      </n-form-item>
      <n-form-item>
        <n-space>
          <n-button type="primary" @click="load" :loading="loading">查询</n-button>
          <n-button @click="reset">重置</n-button>
        </n-space>
      </n-form-item>
    </n-form>
  </n-card>

  <n-card size="small">
    <n-data-table
      remote
      :columns="columns"
      :data="rows"
      :loading="loading"
      :row-key="(r: Alert) => r.id"
      :bordered="false"
      :max-height="520"
      @update:sorter="onSort"
    />
    <n-empty v-if="!loading && !rows.length" description="没有匹配的告警" style="padding: 32px" />
  </n-card>

  <n-drawer v-model:show="showDetail" :width="560" placement="right">
    <n-drawer-content :title="`告警 #${current?.id ?? ''}`" closable>
      <n-spin :show="detailLoading">
        <template v-if="current">
          <n-descriptions label-placement="left" :column="1" size="small" bordered>
            <n-descriptions-item label="服务">{{ current.service || '-' }}</n-descriptions-item>
            <n-descriptions-item label="主机/IP">
              {{ [current.host, current.server_ip].filter(Boolean).join(' / ') || '-' }}
            </n-descriptions-item>
            <n-descriptions-item label="级别">
              <n-tag :type="severityMeta(current.severity).type" size="small">{{ current.severity }}</n-tag>
            </n-descriptions-item>
            <n-descriptions-item label="匹配">
              <n-space :size="6">
                <n-tag :type="matchStatusMeta(current.match_status).type" size="small">
                  {{ matchStatusMeta(current.match_status).label }}
                </n-tag>
                <n-tag :type="alertStatusMeta(current.status).type" size="small">
                  {{ alertStatusMeta(current.status).label }}
                </n-tag>
                <n-tag v-if="current.similarity_score !== null" size="small">
                  相似度 {{ pct(current.similarity_score) }}
                </n-tag>
              </n-space>
            </n-descriptions-item>
            <n-descriptions-item label="时间">{{ fmtDateTime(current.created_at) }}</n-descriptions-item>
          </n-descriptions>

          <n-divider title-placement="left" style="font-size: 13px">原始日志</n-divider>
          <div class="pre-wrap detail-block">{{ current.raw_log }}</div>

          <template v-if="current.report">
            <n-divider title-placement="left" style="font-size: 13px">📢 大白话解释</n-divider>
            <div class="detail-block">{{ current.report.plain_language }}</div>

            <n-divider title-placement="left" style="font-size: 13px">🛠️ 建议操作</n-divider>
            <div class="detail-block">{{ current.report.user_actions || '—' }}</div>

            <n-divider title-placement="left" style="font-size: 13px">👨‍💻 工程师 Playbook</n-divider>
            <div class="pre-wrap detail-block">{{ current.report.engineer_guide }}</div>

            <template v-if="current.report.retrieval?.length">
              <n-divider title-placement="left" style="font-size: 13px">📚 命中的历史案例</n-divider>
              <n-space vertical :size="8">
                <n-card
                  v-for="r in current.report.retrieval"
                  :key="r.knowledge_id"
                  size="small"
                  embedded
                >
                  <n-space align="center" justify="space-between">
                    <strong>#{{ r.knowledge_id }} {{ r.title }}</strong>
                    <n-tag size="small" :type="r.similarity >= 0.78 ? 'success' : 'default'">
                      相似度 {{ pct(r.similarity) }}
                    </n-tag>
                  </n-space>
                  <div v-if="r.error_type" class="muted" style="margin-top: 4px; font-size: 12px">
                    {{ r.error_type }}
                  </div>
                </n-card>
              </n-space>
            </template>
          </template>
          <n-alert v-else type="info" style="margin-top: 12px">该告警暂无诊断报告。</n-alert>
        </template>
      </n-spin>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { h, onMounted, reactive, ref } from 'vue'
import { NButton, NTag, type DataTableColumns } from 'naive-ui'
import { api, type AlertFilters } from '@/api/client'
import type { Alert, AlertWithReport } from '@/types'
import { fmtDateTime, pct } from '@/composables/format'
import { alertStatusMeta, matchStatusMeta, severityMeta } from '@/composables/status'

const loading = ref(false)
const rows = ref<Alert[]>([])

const filters = reactive<Required<Pick<AlertFilters, 'q' | 'status' | 'match_status' | 'service' | 'date'>> & {
  limit: number
}>({
  q: '',
  status: '',
  match_status: '',
  service: '',
  date: null as unknown as string,
  limit: 100,
})

const statusOptions = [
  { label: '待处理', value: 'open' },
  { label: '已解决', value: 'resolved' },
]
const matchOptions = [
  { label: '命中历史', value: 'matched' },
  { label: '新增故障', value: 'new_incident' },
  { label: '已沉淀', value: 'deposited' },
  { label: '已聚合', value: 'aggregated' },
]

const columns: DataTableColumns<Alert> = [
  { title: 'ID', key: 'id', width: 70 },
  {
    title: '时间',
    key: 'created_at',
    width: 170,
    render: (r) => fmtDateTime(r.created_at),
  },
  { title: '服务', key: 'service', width: 110, render: (r) => r.service || r.host || '-' },
  {
    title: '级别',
    key: 'severity',
    width: 80,
    render: (r) => h(NTag, { type: severityMeta(r.severity).type, size: 'small' }, () => r.severity),
  },
  {
    title: '匹配',
    key: 'match_status',
    width: 110,
    render: (r) =>
      h(NTag, { type: matchStatusMeta(r.match_status).type, size: 'small' }, () =>
        matchStatusMeta(r.match_status).label,
      ),
  },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (r) =>
      h(NTag, { type: alertStatusMeta(r.status).type, size: 'small' }, () =>
        alertStatusMeta(r.status).label,
      ),
  },
  {
    title: '相似度',
    key: 'similarity_score',
    width: 90,
    render: (r) => (r.similarity_score !== null ? pct(r.similarity_score) : '-'),
  },
  { title: '日志摘要', key: 'raw_log', ellipsis: { tooltip: true } },
  {
    title: '操作',
    key: '__op',
    width: 90,
    render: (r) =>
      h(NButton, { size: 'small', text: true, type: 'primary', onClick: () => open(r.id) }, () => '详情'),
  },
]

function onSort() {
  // server returns newest-first already; reserved for future use.
}

async function load() {
  loading.value = true
  try {
    const params: AlertFilters = { limit: filters.limit }
    if (filters.q) params.q = filters.q
    if (filters.status) params.status = filters.status
    if (filters.match_status) params.match_status = filters.match_status
    if (filters.service) params.service = filters.service
    if (filters.date) params.date = filters.date
    rows.value = await api.listAlerts(params)
  } finally {
    loading.value = false
  }
}

function reset() {
  filters.q = ''
  filters.status = ''
  filters.match_status = ''
  filters.service = ''
  filters.date = null as unknown as string
  load()
}

const showDetail = ref(false)
const detailLoading = ref(false)
const current = ref<AlertWithReport | null>(null)

async function open(id: number) {
  showDetail.value = true
  detailLoading.value = true
  try {
    current.value = await api.getAlert(id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.detail-block {
  background: #f7f9fc;
  border: 1px solid var(--oia-border);
  border-radius: 6px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
