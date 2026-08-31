import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

// 重接口（批量操作/统计重算/详情分段）走长超时：调用处用 api.long
export const apiLong = axios.create({ baseURL: '/api', timeout: 180000 })

api.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) config.headers.Authorization = `Bearer ${authStore.token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      if (router.currentRoute.value.name !== 'login') {
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)

export function useApi() { return api }
