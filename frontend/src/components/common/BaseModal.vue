<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')"></div>
      <div class="relative flex flex-col bg-white rounded-lg shadow-xl w-full mx-4 modal-in max-h-[90vh]" :class="width ?? 'max-w-2xl'">
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-default shrink-0">
          <h3 class="font-semibold text-md">{{ title }}</h3>
          <button @click="$emit('close')" class="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"><X :size="18" /></button>
        </div>
        <div class="px-5 py-4 overflow-y-auto flex-1 min-h-0">
          <slot />
        </div>
        <div v-if="$slots.footer" class="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-default bg-bg-secondary rounded-b-lg shrink-0">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { X } from 'lucide-vue-next'
defineProps<{ title: string; width?: string }>()
defineEmits(['close'])
</script>
