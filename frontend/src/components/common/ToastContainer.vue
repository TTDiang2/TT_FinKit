<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-50 flex flex-col gap-2 items-end">
      <div v-for="toast in topToasts" :key="toast.id"
        :class="['px-4 py-3 rounded-md shadow-md text-sm font-medium modal-in max-w-md whitespace-pre-line',
          toast.type === 'success' ? 'bg-success text-white' : '',
          toast.type === 'error' ? 'bg-error text-white' : '',
          toast.type === 'warning' ? 'bg-warning text-white' : '',
          toast.type === 'info' ? 'bg-info text-white' : '']">
        {{ toast.message }}
      </div>
    </div>
    <div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end">
      <div v-for="toast in bottomToasts" :key="toast.id"
        :class="['px-4 py-3 rounded-md shadow-md text-sm font-medium modal-in max-w-md whitespace-pre-line',
          toast.type === 'success' ? 'bg-success text-white' : '',
          toast.type === 'error' ? 'bg-error text-white' : '',
          toast.type === 'warning' ? 'bg-warning text-white' : '',
          toast.type === 'info' ? 'bg-info text-white' : '']">
        {{ toast.message }}
      </div>
    </div>
  </Teleport>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useToast } from '@/composables/useToast'
const { toasts } = useToast()
const topToasts = computed(() => toasts.value.filter(t => t.position === 'top'))
const bottomToasts = computed(() => toasts.value.filter(t => t.position === 'bottom'))
</script>
