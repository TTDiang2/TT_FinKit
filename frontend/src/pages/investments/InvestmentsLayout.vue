<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">投资</h1>
    </div>
    <div class="flex gap-2 mb-4 flex-wrap">
      <router-link to="/investments" custom v-slot="{ navigate, isExactActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isExactActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          持仓与流水
        </button>
      </router-link>
      <router-link to="/investments/assets" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          标的
        </button>
      </router-link>
      <router-link to="/investments/factors" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          因子
        </button>
      </router-link>
      <router-link to="/investments/strategies" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          策略
        </button>
      </router-link>
      <router-link to="/investments/monitor" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          监控
        </button>
      </router-link>
      <router-link to="/investments/ai" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors flex items-center gap-1', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          AI 分析 <span class="text-xs opacity-70">(Beta)</span>
        </button>
      </router-link>
    </div>
    <RouterView />
  </div>
</template>
<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>