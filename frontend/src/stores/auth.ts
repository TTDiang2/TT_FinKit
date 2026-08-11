import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(sessionStorage.getItem('token'))
  const user = ref<User | null>(null)
  const isReady = ref(false)
  const api = useApi()

  async function login(email: string, password: string) {
    const res = await api.post('/auth/login', { email, password })
    token.value = res.data.access_token
    sessionStorage.setItem('token', res.data.access_token)
    await fetchMe()
  }

  async function register(email: string, password: string, name: string) {
    const res = await api.post('/auth/register', { email, password, name })
    token.value = res.data.access_token
    sessionStorage.setItem('token', res.data.access_token)
    await fetchMe()
  }

  async function fetchMe() {
    try {
      const res = await api.get('/auth/me')
      user.value = res.data
    } catch {
      user.value = null
      token.value = null
      sessionStorage.removeItem('token')
    } finally {
      isReady.value = true
    }
  }

  function logout() {
    token.value = null
    user.value = null
    sessionStorage.removeItem('token')
  }

  if (token.value) {
    fetchMe()
  } else {
    isReady.value = true
  }

  return { token, user, isReady, login, register, logout, fetchMe }
})
