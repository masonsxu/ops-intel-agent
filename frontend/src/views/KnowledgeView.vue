<template>
  <n-tabs type="line" animated>
    <!-- ── 向量模糊搜索 ─────────────────────────────────────────────── -->
    <n-tab-pane name="semantic" tab="向量模糊搜索">
      <n-card size="small" class="section-card">
        <n-space align="center" :wrap="false">
          <n-input
            v-model:value="semQuery"
            placeholder="用自然语言描述问题，例如：数据库连接池打满 / redis 内存溢出"
            clearable
            @keydown.enter="runSearch"
            style="width: 480px"
          />
          <n-input-number v-model:value="semK" :min="1" :max="20" style="width: 110px">
            <template #prefix>TopK</template>
          </n-input-number>
          <n-button type="primary" :loading="semLoading" @click="runSearch">语义检索</n-button>
        </n-space>
        <p class="muted hint">
          基于向量余弦相似度排序，按“语义”而非关键词匹配 —— 比如查“db pool timeout”也能命中已知的 MySQL HikariCP 案例。
        </p>
      </n-card>

      <n-spin :show="semLoading">
        <n-empty v-if="!semHits.length && !semLoading" description="输入问题后点击“语义检索”查看相似案例" />
        <n-space v-else vertical :size="12">
          <n-card
            v-for="hit in semHits"
            :key="hit.id"
            size="small"
            class="kb-card"
            hoverable
            @click="open(hit)"
          >
            <div class="flex-between">
              <n-space align="center" :size="8">
                <n-tag type="primary" size="small">{{ pct(hit.similarity) }}</n-tag>
                <strong>{{ hit.title }}</strong>
              </n-space>
              <n-space :size="6">
                <n-tag v-if="hit.error_type" size="tiny">{{ hit.error_type }}</n-tag>
                <n-tag v-for="t in hit.tags" :key="t" size="tiny" type="info" :bordered="false">{{ t }}</n-tag>
              </n-space>
            </div>
            <div class="muted small">{{ hit.raw_log_sample }}</div>
          </n-card>
        </n-space>
      </n-spin>
    </n-tab-pane>

    <!-- ── 日期精确搜索 / 列表 ──────────────────────────────────────── -->
    <n-tab-pane name="list" tab="按日期 / 列表">
      <n-card size="small" class="section-card">
        <n-form inline :show-feedback="false" label-placement="left">
          <n-form-item label="日期(精确)">
            <n-date-picker
              v-model:formatted-value="filters.date"
              type="date"
              value-format="yyyy-MM-dd"
              clearable
              style="width: 170px"
            />
          </n-form-item>
          <n-form-item label="范围">
            <n-date-picker
              v-model:formatted-value="filters.date_from"
              type="date"
              value-format="yyyy-MM-dd"
              clearable
              placeholder="开始"
              style="width: 150px"
            />
            <span style="padding: 0 6px">~</span>
            <n-date-picker
              v-model:formatted-value="filters.date_to"
              type="date"
              value-format="yyyy-MM-dd"
              clearable
              placeholder="结束"
              style="width: 150px"
            />
          </n-form-item>
          <n-form-item label="类型">
            <n-input
              v-model:value="filters.error_type"
              placeholder="error_type"
              clearable
              style="width: 150px"
            />
          </n-form-item>
          <n-form-item label="关键词">
            <n-input
              v-model:value="filters.q"
              placeholder="标题 / 根因 / 日志"
              clearable
              style="width: 200px"
              @keydown.enter="loadList"
            />
          </n-form-item>
          <n-form-item>
            <n-space>
              <n-button type="primary" :loading="listLoading" @click="loadList">查询</n-button>
              <n-button @click="resetList">重置</n-button>
            </n-space>
          </n-form-item>
        </n-form>
      </n-card>

      <n-spin :show="listLoading">
        <n-empty
          v-if="!listRows.length && !listLoading"
          description="没有匹配的知识条目"
          style="padding: 32px"
        />
        <n-space v-else vertical :size="12">
          <n-card
            v-for="kb in listRows"
            :key="kb.id"
            size="small"
            class="kb-card"
            hoverable
            @click="open(kb)"
          >
            <div class="flex-between">
              <n-space align="center" :size="8">
                <n-tag size="small" :bordered="false">命中 {{ kb.occurrence_count }}</n-tag>
                <strong>{{ kb.title }}</strong>
              </n-space>
              <n-space :size="6">
                <n-tag v-if="kb.error_type" size="tiny">{{ kb.error_type }}</n-tag>
                <n-tag size="tiny" :type="kb.source.startsWith('engineer') ? 'success' : 'default'">
                  {{ kb.source }}
                </n-tag>
                <n-tag size="tiny" type="default">{{ fmtDate(kb.created_at) }}</n-tag>
              </n-space>
            </div>
            <div class="muted small">{{ kb.root_cause || kb.raw_log_sample }}</div>
          </n-card>
        </n-space>
      </n-spin>
    </n-tab-pane>
  </n-tabs>

  <!-- ── 详情抽屉 ─────────────────────────────────────────────────── -->
  <n-drawer v-model:show="showDetail" :width="560" placement="right">
    <n-drawer-content :title="current?.title ?? '知识条目'" closable>
      <template v-if="current">
        <n-descriptions label-placement="left" :column="1" size="small" bordered>
          <n-descriptions-item label="ID">#{{ current.id }}</n-descriptions-item>
          <n-descriptions-item label="类型">{{ current.error_type || '-' }}</n-descriptions-item>
          <n-descriptions-item label="来源">{{ current.source }}</n-descriptions-item>
          <n-descriptions-item label="命中次数">{{ current.occurrence_count }}</n-descriptions-item>
          <n-descriptions-item label="置信度">{{ pct(current.confidence) }}</n-descriptions-item>
          <n-descriptions-item label="标签">
            <n-space :size="4">
              <n-tag v-for="t in current.tags" :key="t" size="tiny" type="info" :bordered="false">{{ t }}</n-tag>
              <span v-if="!current.tags?.length" class="muted">-</span>
            </n-space>
          </n-descriptions-item>
          <n-descriptions-item label="创建时间">{{ fmtDateTime(current.created_at) }}</n-descriptions-item>
        </n-descriptions>

        <n-divider title-placement="left" style="font-size: 13px">原始日志样本</n-divider>
        <div class="pre-wrap detail-block">{{ current.raw_log_sample }}</div>

        <n-divider title-placement="left" style="font-size: 13px">根因</n-divider>
        <div class="detail-block">{{ current.root_cause || '—' }}</div>

        <n-divider title-placement="left" style="font-size: 13px">用户指引</n-divider>
        <div class="detail-block">{{ current.user_guide }}</div>

        <n-divider title-placement="left" style="font-size: 13px">工程师 Playbook</n-divider>
        <div class="pre-wrap detail-block">{{ current.engineer_guide }}</div>

        <n-space justify="end" style="margin-top: 16px">
          <n-popconfirm @positive-click="removeCurrent">
            <template #trigger>
              <n-button ghost type="error" size="small">停用此条目</n-button>
            </template>
            停用后会从向量库移除，确认？
          </n-popconfirm>
        </n-space>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { api } from '@/api/client'
import type { Knowledge, KnowledgeSearchHit } from '@/types'
import { fmtDate, fmtDateTime, pct } from '@/composables/format'

const message = useMessage()

// ── semantic search state ───────────────────────────────────────────────
const semQuery = ref('')
const semK = ref(5)
const semLoading = ref(false)
const semHits = ref<KnowledgeSearchHit[]>([])

async function runSearch() {
  if (!semQuery.value.trim()) {
    message.warning('请输入查询内容')
    return
  }
  semLoading.value = true
  try {
    semHits.value = await api.searchKnowledge(semQuery.value.trim(), semK.value)
    if (!semHits.value.length) message.info('未检索到相似案例')
  } catch (e) {
    message.error('检索失败')
  } finally {
    semLoading.value = false
  }
}

// ── date/list state ─────────────────────────────────────────────────────
const listLoading = ref(false)
const listRows = ref<Knowledge[]>([])
const filters = reactive({
  date: null as string | null,
  date_from: null as string | null,
  date_to: null as string | null,
  error_type: '',
  q: '',
})

async function loadList() {
  listLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (filters.date) params.date = filters.date
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to) params.date_to = filters.date_to
    if (filters.error_type) params.error_type = filters.error_type
    if (filters.q) params.q = filters.q
    listRows.value = await api.listKnowledge(params)
  } finally {
    listLoading.value = false
  }
}

function resetList() {
  filters.date = null
  filters.date_from = null
  filters.date_to = null
  filters.error_type = ''
  filters.q = ''
  loadList()
}

// ── detail drawer ───────────────────────────────────────────────────────
const showDetail = ref(false)
const current = ref<Knowledge | null>(null)

function open(kb: Knowledge) {
  current.value = kb
  showDetail.value = true
}

async function removeCurrent() {
  if (!current.value) return
  try {
    await api.deleteKnowledge(current.value.id)
    message.success('已停用')
    showDetail.value = false
    loadList()
  } catch {
    message.error('停用失败')
  }
}

onMounted(loadList)
</script>

<style scoped>
.hint {
  font-size: 12px;
  margin: 8px 0 0;
}
.small {
  font-size: 12.5px;
  margin-top: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-card {
  cursor: pointer;
}
.detail-block {
  background: #f7f9fc;
  border: 1px solid var(--oia-border);
  border-radius: 6px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
