<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">投资</h1>
    </div>
    <div class="flex gap-2 mb-4">
      <router-link to="/investments" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          持仓与流水
        </button>
      </router-link>
      <router-link to="/investments/strategies" custom v-slot="{ navigate, isActive }">
        <button
          @click="navigate"
          :class="[
            'px-4 py-2 text-sm rounded-md transition-colors',
            isActive
              ? 'bg-accent-primary text-white'
              : 'border border-border-default text-text-secondary hover:bg-bg-tertiary',
          ]"
        >
          策略库
        </button>
      </router-link>
      <router-link to="/investments/backtests" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          回测
        </button>
      </router-link>
      <router-link to="/investments/assets" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          标的池
        </button>
      </router-link>
      <router-link to="/investments/factors" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          因子
        </button>
      </router-link>
      <router-link to="/investments/signals" custom v-slot="{ navigate, isActive }">
        <button @click="navigate" :class="['px-4 py-2 text-sm rounded-md transition-colors', isActive ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          信号
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