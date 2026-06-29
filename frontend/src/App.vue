<template>
  <n-config-provider :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <MainLayout />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { zhCN, dateZhCN, type GlobalThemeOverrides } from 'naive-ui'
import MainLayout from '@/layouts/MainLayout.vue'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#3358d4',
    primaryColorHover: '#2b6fe0',
    primaryColorPressed: '#2748b8',
    borderRadius: '8px',
  },
}
</script>
