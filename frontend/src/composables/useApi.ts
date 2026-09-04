import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

// 重接口（批量操作/统计重算/详情分段/AI问答）走长超时：调用处用 apiLong
export const apiLong = axios.create({ baseURL: '/api', timeout: 180000 })

function attachAuth(instance: ReturnType<typeof axios.create>) {
  instance.interceptors.request.use((config) => {
    const authStore = useAuthStore()
    if (authStore.token) config.headers.Authorization = `Bearer ${authStore.token}`
    return config
  })
  instance.interceptors.response.use(
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
}

attachAuth(api)
attachAuth(apiLong)

export function useApi() { return api }
