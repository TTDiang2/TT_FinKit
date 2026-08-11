<template>
  <aside :class="['h-screen bg-bg-sidebar border-r border-border-default flex flex-col transition-all duration-300', expanded ? 'w-[220px]' : 'w-[64px]']">
    <div class="h-14 flex items-center px-4 border-b border-border-default">
      <svg v-if="!expanded" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="flex-shrink-0">
        <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M2 9h20" stroke="currentColor" stroke-width="2"/>
        <path d="M16 12.5a2 2 0 100-4 2 2 0 000 4z" fill="currentColor"/>
      </svg>
      <template v-if="expanded">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="flex-shrink-0">
          <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
          <path d="M2 9h20" stroke="currentColor" stroke-width="2"/>
          <path d="M16 12.5a2 2 0 100-4 2 2 0 000 4z" fill="currentColor"/>
        </svg>
        <span class="font-semibold text-xl ml-2">FinKit</span>
      </template>
    </div>
    <nav class="flex-1 py-3 overflow-hidden">
      <div v-for="item in navItems" :key="item.path">
        <router-link :to="item.path" :title="!expanded ? item.label : ''"
          :class="['flex items-center gap-3 px-4 py-2.5 mx-2 rounded-md transition-colors duration-75 relative group',
            isActive(item.path) ? 'bg-accent-primary text-white' : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary']">
          <component :is="item.icon" :size="20" />
          <span v-if="expanded" class="text-sm font-medium whitespace-nowrap">{{ item.label }}</span>
          <div v-if="!expanded" class="absolute left-full ml-2 px-2 py-1 bg-accent-primary text-white text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity z-50">
            {{ item.label }}
          </div>
        </router-link>
      </div>
    </nav>
    <div class="p-3 border-t border-border-default">
      <button @click="toggleSidebar" class="w-full flex items-center justify-center p-2 rounded-md hover:bg-bg-tertiary transition-colors">
        <ChevronLeft v-if="expanded" :size="18" class="text-text-secondary" />
        <ChevronRight v-else :size="18" class="text-text-secondary" />
      </button>
    </div>
  </aside>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { Home, Edit3, Wallet, TrendingUp, BarChart2, FileText, Settings, Shield, ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const settingsStore = useSettingsStore()
const navItems = [
  { path: '/', label: '首页', icon: Home },
  { path: '/bookkeeping', label: '记账', icon: Edit3 },
  { path: '/assets', label: '资产', icon: Wallet },
  { path: '/investments', label: '投资', icon: TrendingUp },
  { path: '/statistics', label: '统计', icon: BarChart2 },
  { path: '/reports', label: '报表', icon: FileText },
  { path: '/settings', label: '设置', icon: Settings },
  { path: '/admin', label: '管理', icon: Shield },
]
const expanded = ref(settingsStore.settings.sidebar_expanded)
function isActive(path: string) { return path === '/' ? route.path === '/' : route.path.startsWith(path) }
function toggleSidebar() { expanded.value = !expanded.value; settingsStore.updateSettings({ sidebar_expanded: expanded.value }) }
</script>
