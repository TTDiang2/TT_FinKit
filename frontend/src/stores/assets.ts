import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Asset } from '@/types'

export const useAssetsStore = defineStore('assets', () => {
  const assets = ref<Asset[]>([])
  const api = useApi()

  async function fetchAssets() { const res = await api.get('/assets'); assets.value = res.data }
  async function createAsset(data: Partial<Asset>) { const res = await api.post('/assets', data); assets.value.push(res.data); return res.data }
  async function updateAsset(id: string, data: Partial<Asset>) { const res = await api.put(`/assets/${id}`, data); const idx = assets.value.findIndex(a => a.id === id); if (idx !== -1) assets.value[idx] = res.data; return res.data }
  async function deleteAsset(id: string) { await api.delete(`/assets/${id}`); assets.value = assets.value.filter(a => a.id !== id) }

  return { assets, fetchAssets, createAsset, updateAsset, deleteAsset }
})
