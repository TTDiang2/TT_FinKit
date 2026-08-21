import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Investment, InvestmentCashFlow, PortfolioOverview, LookupCandidate, ClosedPositionsResponse } from '@/types'

export const useInvestmentsStore = defineStore('investments', () => {
  const investments = ref<Investment[]>([])
  const cashFlows = ref<InvestmentCashFlow[]>([])
  const portfolioOverview = ref<PortfolioOverview | null>(null)
  const closedPositions = ref<ClosedPositionsResponse | null>(null)
  const api = useApi()

  async function fetchInvestments() { const res = await api.get('/investments'); investments.value = res.data }
  async function createInvestment(data: Partial<Investment>) { const res = await api.post('/investments', data); investments.value.push(res.data); return res.data }
  async function updateInvestment(id: string, data: Partial<Investment>) { const res = await api.put(`/investments/${id}`, data); const idx = investments.value.findIndex(a => a.id === id); if (idx !== -1) investments.value[idx] = res.data; return res.data }
  async function deleteInvestment(id: string) { await api.delete(`/investments/${id}`); investments.value = investments.value.filter(a => a.id !== id) }

  async function fetchCashFlows() { const res = await api.get('/investments/cash-flows'); cashFlows.value = res.data }
  async function createCashFlow(data: Partial<InvestmentCashFlow>) { const res = await api.post('/investments/cash-flows', data); await fetchCashFlows(); return res.data }
  async function updateCashFlow(id: string, data: Partial<InvestmentCashFlow>) { const res = await api.put(`/investments/cash-flows/${id}`, data); await fetchCashFlows(); return res.data }
  async function deleteCashFlow(id: string) { await api.delete(`/investments/cash-flows/${id}`); cashFlows.value = cashFlows.value.filter(f => f.id !== id) }

  async function fetchPortfolioOverview() { const res = await api.get('/investments/portfolio-metrics'); portfolioOverview.value = res.data }
  async function fetchClosedPositions() { const res = await api.get('/investments/closed-positions'); closedPositions.value = res.data }

  async function lookupSymbol(symbol: string): Promise<LookupCandidate[]> {
    const res = await api.get('/investments/lookup', { params: { symbol } })
    return res.data
  }

  return {
    investments, cashFlows, portfolioOverview, closedPositions,
    fetchInvestments, createInvestment, updateInvestment, deleteInvestment,
    fetchCashFlows, createCashFlow, updateCashFlow, deleteCashFlow,
    fetchPortfolioOverview, fetchClosedPositions, lookupSymbol,
  }
})
