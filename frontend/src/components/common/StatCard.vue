<template>
  <div class="bg-white rounded-lg p-4 shadow-sm">
    <div class="text-sm text-text-secondary">{{ label }}</div>
    <div class="text-lg font-bold" :class="colorClass">{{ value }}</div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ label: string; value: string; colorClass?: string }>()
</script>