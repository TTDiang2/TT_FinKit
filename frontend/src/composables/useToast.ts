import { ref } from 'vue'

interface Toast { id: number; message: string; type: 'success' | 'error' | 'warning' | 'info' }
const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  const show = (message: string, type: Toast['type'] = 'info') => {
    const id = ++nextId
    toasts.value.push({ id, message, type })
    setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, 3000)
  }
  return { toasts, show }
}
