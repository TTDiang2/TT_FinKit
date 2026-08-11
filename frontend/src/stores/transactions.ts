import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Transaction } from '@/types'

export const useTransactionsStore = defineStore('transactions', () => {
  const transactions = ref<Transaction[]>([])
  const api = useApi()
  async function fetchTransactions(params?: any) { const res = await api.get('/transactions', { params }); transactions.value = res.data }
  async function createTransaction(data: Partial<Transaction>) { const res = await api.post('/transactions', data); transactions.value.unshift(res.data); return res.data }
  async function updateTransaction(id: string, data: Partial<Transaction>) { const res = await api.put(`/transactions/${id}`, data); const idx = transactions.value.findIndex(t => t.id === id); if (idx !== -1) transactions.value[idx] = res.data; return res.data }
  async function deleteTransaction(id: string) { await api.delete(`/transactions/${id}`); transactions.value = transactions.value.filter(t => t.id !== id) }
  return { transactions, fetchTransactions, createTransaction, updateTransaction, deleteTransaction }
})
