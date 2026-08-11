import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Category } from '@/types'

export const useCategoriesStore = defineStore('categories', () => {
  const categories = ref<Category[]>([])
  const api = useApi()
  const incomeCategories = computed(() => categories.value.filter(c => c.type === 'income'))
  const expenseCategories = computed(() => categories.value.filter(c => c.type === 'expense'))
  async function fetchCategories() { const res = await api.get('/categories'); categories.value = res.data }
  async function createCategory(data: Partial<Category>) { const res = await api.post('/categories', data); categories.value.push(res.data); return res.data }
  async function updateCategory(id: string, data: Partial<Category>) { const res = await api.put(`/categories/${id}`, data); const idx = categories.value.findIndex(c => c.id === id); if (idx !== -1) categories.value[idx] = res.data; return res.data }
  async function deleteCategory(id: string) { await api.delete(`/categories/${id}`); categories.value = categories.value.filter(c => c.id !== id) }
  return { categories, incomeCategories, expenseCategories, fetchCategories, createCategory, updateCategory, deleteCategory }
})
