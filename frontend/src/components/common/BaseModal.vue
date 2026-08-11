<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 modal-in">
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-default">
          <h3 class="font-semibold text-md">{{ title }}</h3>
          <button @click="$emit('close')" class="text-text-muted hover:text-text-primary transition-colors"><X :size="18" /></button>
        </div>
        <div class="px-5 py-4"><slot /></div>
        <div v-if="$slots.footer" class="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-default bg-bg-secondary rounded-b-lg">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
<script setup lang="ts">
import { X } from 'lucide-vue-next'
defineProps<{ title: string }>()
defineEmits(['close'])
</script>
