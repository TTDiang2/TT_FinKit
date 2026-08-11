import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Investment } from '@/types'

export const useInvestmentsStore = defineStore('investments', () => {
  const investments = ref<Investment[]>([])
  const api = useApi()

  async function fetchInvestments() { const res = await api.get('/investments'); investments.value = res.data }
  async function createInvestment(data: Partial<Investment>) { const res = await api.post('/investments', data); investments.value.push(res.data); return res.data }
  async function updateInvestment(id: string, data: Partial<Investment>) { const res = await api.put(`/investments/${id}`, data); const idx = investments.value.findIndex(a => a.id === id); if (idx !== -1) investments.value[idx] = res.data; return res.data }
  async function deleteInvestment(id: string) { await api.delete(`/investments/${id}`); investments.value = investments.value.filter(a => a.id !== id) }

  return { investments, fetchInvestments, createInvestment, updateInvestment, deleteInvestment }
})
