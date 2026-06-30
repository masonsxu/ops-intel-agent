<template>
  <div class="settings-page">
    <n-card title="API 配置" size="small" :bordered="false">
      <template #header-extra>
        <n-tag v-if="isTauri" type="info" size="small">Tauri 桌面模式</n-tag>
        <n-tag v-else type="warning" size="small">浏览器预览模式</n-tag>
      </template>

      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        label-width="120"
        class="settings-form"
      >
        <n-form-item label="OpenAI API Key" path="openai_api_key">
          <n-input
            v-model:value="form.openai_api_key"
            type="password"
            show-password-on="click"
            placeholder="sk-..."
            :input-props="{ autocomplete: 'off' }"
          />
          <template #feedback>
            留空则使用本地离线模式（local embedding + local LLM，精度有限）
          </template>
        </n-form-item>

        <n-form-item label="OpenAI Base URL" path="openai_base_url">
          <n-input
            v-model:value="form.openai_base_url"
            placeholder="https://api.openai.com/v1"
          />
        </n-form-item>

        <n-grid :cols="2" :x-gap="16">
          <n-grid-item>
            <n-form-item label="Embedding 模型" path="embedding_model">
              <n-input v-model:value="form.embedding_model" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item>
            <n-form-item label="LLM 模型" path="llm_model">
              <n-input v-model:value="form.llm_model" />
            </n-form-item>
          </n-grid-item>
        </n-grid>

        <div class="form-actions">
          <n-button
            type="primary"
            @click="handleSave"
            :loading="saving"
          >
            保存配置
          </n-button>
          <n-button
            v-if="isTauri && needRestart"
            quaternary
            type="warning"
            @click="handleRestart"
          >
            重启后端
          </n-button>
        </div>

        <n-alert v-if="saved" type="success" :show-icon="true" closable>
          配置已保存。
          <template v-if="isTauri">点击「重启后端」使新配置生效。</template>
          <template v-else>重启后端进程使新配置生效。</template>
        </n-alert>
      </n-form>
    </n-card>

    <n-card title="关于" size="small" :bordered="false" class="about-card">
      <p class="text-secondary">Ops Intel Agent v0.1.0</p>
      <p class="text-secondary">Python 后端运行于 http://127.0.0.1:8000</p>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { settingsApi, type AppSettings } from '@/api/settings'

const message = useMessage()
const formRef = ref<any>(null)
const saving = ref(false)
const saved = ref(false)
const needRestart = ref(false)
const isTauri = ref(typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window)

const form = ref<AppSettings>({
  openai_api_key: '',
  openai_base_url: 'https://api.openai.com/v1',
  embedding_model: 'text-embedding-3-small',
  llm_model: 'gpt-4o-mini',
})

const rules = {
  openai_base_url: [{ type: 'url', trigger: 'blur', message: 'URL 格式不正确' }],
  embedding_model: [{ required: true, message: '请输入模型名称' }],
  llm_model: [{ required: true, message: '请输入模型名称' }],
}

async function loadSettings() {
  try {
    const s = await settingsApi.get()
    form.value = { ...s }
  } catch {
    // use defaults
  }
}

async function handleSave() {
  saving.value = true
  saved.value = false
  try {
    await settingsApi.save(form.value)
    saved.value = true
    needRestart.value = true
    message.success('配置已保存')
  } catch (e: any) {
    message.error('保存失败: ' + (e?.message || String(e)))
  } finally {
    saving.value = false
  }
}

async function handleRestart() {
  try {
    await settingsApi.restartBackend()
    message.success('后端已重启')
    needRestart.value = false
  } catch (e: any) {
    message.error('重启失败: ' + (e?.message || String(e)))
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-page {
  max-width: 640px;
}
.settings-form {
  margin-top: 8px;
}
.form-actions {
  display: flex;
  gap: 12px;
  margin: 24px 0 16px;
}
.about-card {
  margin-top: 16px;
}
.text-secondary {
  color: #888;
  font-size: 13px;
  margin: 4px 0;
}
</style>
