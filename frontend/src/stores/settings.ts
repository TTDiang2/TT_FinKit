import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { UserSettings } from '@/types'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<UserSettings>({ language: 'zh', currency_symbol: '¥', date_format: 'YYYY-MM-DD', timezone: 'Asia/Shanghai', sidebar_expanded: true })
  const api = useApi()
  async function fetchSettings() { try { const res = await api.get('/settings'); settings.value = res.data } catch {} }
  async function updateSettings(data: Partial<UserSettings>) { const res = await api.put('/settings', data); settings.value = res.data; return res.data }
  return { settings, fetchSettings, updateSettings }
}, { persist: true })
