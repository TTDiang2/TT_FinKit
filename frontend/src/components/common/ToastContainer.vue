<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-50 flex flex-col gap-2">
      <div v-for="toast in toasts" :key="toast.id"
        :class="['px-4 py-3 rounded-md shadow-md text-sm font-medium modal-in',
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
import { useToast } from '@/composables/useToast'
const { toasts } = useToast()
</script>
