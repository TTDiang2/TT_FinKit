import { ref } from 'vue'

type ToastPosition = 'top' | 'bottom'

interface Toast { id: number; message: string; type: 'success' | 'error' | 'warning' | 'info'; position: ToastPosition }
const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  const show = (message: string, type: Toast['type'] = 'info', options?: { position?: ToastPosition; duration?: number }) => {
    const id = ++nextId
    toasts.value.push({ id, message, type, position: options?.position ?? 'top' })
    setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, options?.duration ?? 3000)
  }
  return { toasts, show }
}
