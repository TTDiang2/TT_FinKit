import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Tag } from '@/types'

export const useTagsStore = defineStore('tags', () => {
  const tags = ref<Tag[]>([])
  const api = useApi()
  async function fetchTags() { const res = await api.get('/tags'); tags.value = res.data }
  async function createTag(data: Partial<Tag>) { const res = await api.post('/tags', data); tags.value.push(res.data); return res.data }
  async function updateTag(id: string, data: Partial<Tag>) { const res = await api.put(`/tags/${id}`, data); const idx = tags.value.findIndex(t => t.id === id); if (idx !== -1) tags.value[idx] = res.data; return res.data }
  async function deleteTag(id: string) { await api.delete(`/tags/${id}`); tags.value = tags.value.filter(t => t.id !== id) }
  return { tags, fetchTags, createTag, updateTag, deleteTag }
})
