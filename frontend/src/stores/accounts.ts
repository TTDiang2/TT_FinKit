import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Account } from '@/types'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<Account[]>([])
  const api = useApi()

  async function fetchAccounts() { const res = await api.get('/accounts'); accounts.value = res.data }
  async function createAccount(data: Partial<Account>) { const res = await api.post('/accounts', data); accounts.value.push(res.data); return res.data }
  async function updateAccount(id: string, data: Partial<Account>) { const res = await api.put(`/accounts/${id}`, data); const idx = accounts.value.findIndex(a => a.id === id); if (idx !== -1) accounts.value[idx] = res.data; return res.data }
  async function deleteAccount(id: string) { await api.delete(`/accounts/${id}`); accounts.value = accounts.value.filter(a => a.id !== id) }

  return { accounts, fetchAccounts, createAccount, updateAccount, deleteAccount }
})
