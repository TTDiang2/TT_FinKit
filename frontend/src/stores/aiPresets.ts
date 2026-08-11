import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import type { AiPreset } from '@/types'

export const useAiPresetsStore = defineStore('aiPresets', () => {
  const presets = ref<AiPreset[]>([])
  const api = useApi()
  const defaultPreset = computed(() => presets.value.find(p => p.is_default))
  
  async function fetchPresets() {
    const res = await api.get('/ai-presets')
    presets.value = res.data
  }
  
  async function createPreset(data: Partial<AiPreset>) {
    const res = await api.post('/ai-presets', data)
    presets.value.push(res.data)
    return res.data
  }
  
  async function updatePreset(id: string, data: Partial<AiPreset>) {
    const res = await api.put(`/ai-presets/${id}`, data)
    const idx = presets.value.findIndex(p => p.id === id)
    if (idx !== -1) presets.value[idx] = res.data
    return res.data
  }
  
  async function deletePreset(id: string) {
    await api.delete(`/ai-presets/${id}`)
    presets.value = presets.value.filter(p => p.id !== id)
  }
  
  async function setDefault(id: string) {
    for (const p of presets.value) {
      if (p.is_default) {
        await api.put(`/ai-presets/${p.id}`, { is_default: false })
        p.is_default = false
      }
    }
    const res = await api.put(`/ai-presets/${id}`, { is_default: true })
    const idx = presets.value.findIndex(p => p.id === id)
    if (idx !== -1) presets.value[idx] = res.data
    return res.data
  }
  
  return { presets, defaultPreset, fetchPresets, createPreset, updatePreset, deletePreset, setDefault }
})