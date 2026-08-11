<template>
  <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
    <div v-if="loading" class="flex items-center justify-center py-8 text-text-muted">
      <span>加载中…</span>
    </div>
    <div v-else-if="error" class="flex items-center justify-center py-8 text-expense-color">
      <span>{{ error }}</span>
    </div>
    <div v-else>
      <!-- Top row: Concentration + Allocation -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <!-- Concentration card -->
        <div class="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4">
          <h3 class="text-sm font-medium text-blue-900 mb-3">集中度</h3>
          <div class="space-y-2">
            <div class="flex justify-between items-center">
              <span class="text-xs text-blue-700">最大单只占比</span>
              <span class="text-lg font-bold text-blue-900">{{ maxSinglePct }}%</span>
            </div>
            <div class="flex justify-between items-center">
              <span class="text-xs text-blue-700">前 3 只占比</span>
              <span class="text-lg font-bold text-blue-900">{{ top3Pct }}%</span>
            </div>
          </div>
        </div>

        <!-- Allocation chart -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="text-sm font-medium mb-3">资产配置</h3>
          <div class="h-32 flex items-center justify-center">
            <Doughnut v-if="allocationChart.labels.length" :data="allocationChart" :options="doughnutOpts" />
            <div v-else class="text-text-muted text-sm">暂无持仓数据</div>
          </div>
        </div>
      </div>

      <!-- Warnings section -->
      <div>
        <h3 class="text-sm font-medium mb-3">组合健康预警</h3>
        <div v-if="(healthResult?.warnings?.length ?? 0) === 0" class="bg-green-50 rounded-lg p-3">
          <div class="flex items-center">
            <span class="text-green-600 mr-2">●</span>
            <span class="text-sm text-green-700">组合健康，无预警</span>
          </div>
        </div>
        <div v-else class="space-y-2">
          <div v-for="(warning, index) in (healthResult?.warnings ?? [])" :key="index" class="flex items-start p-2 rounded-lg" :class="warningSeverityClass(warning.severity)">
            <span class="mt-0.5 mr-2 flex-shrink-0" :class="warningSeverityDot(warning.severity)"></span>
            <span class="text-sm">{{ warning.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import { useApi } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'
import type { HealthResult, HealthWarning } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend)

const api = useApi()
const settingsStore = useSettingsStore()
const sym = computed(() => settingsStore.settings.currency_symbol)

const loading = ref(false)
const error = ref('')
const healthResult = ref<HealthResult | null>(null)

// Computed properties
const maxSinglePct = computed(() => {
  if (!healthResult.value?.concentration) return 0
  return healthResult.value.concentration.max_single_pct ?? 0
})

const top3Pct = computed(() => {
  if (!healthResult.value?.concentration) return 0
  return healthResult.value.concentration.top3_pct ?? 0
})

const allocationChart = computed(() => {
  if (!healthResult.value?.allocation) return { labels: [], datasets: [] }
  
  const entries = Object.entries(healthResult.value.allocation)
  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16']
  
  return {
    labels: entries.map(([k]) => k),
    datasets: [{
      data: entries.map(([, v]) => Number(v)),
      backgroundColor: entries.map((_, i) => colors[i % colors.length])
    }]
  }
})

const doughnutOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'bottom' as const,
      labels: {
        boxWidth: 12,
        font: { size: 11 },
        padding: 10
      }
    }
  }
}

function warningSeverityClass(severity: HealthWarning['severity']) {
  switch (severity) {
    case 'high': return 'bg-red-50'
    case 'medium': return 'bg-amber-50'
    case 'low': return 'bg-gray-50'
    default: return 'bg-gray-50'
  }
}

function warningSeverityDot(severity: HealthWarning['severity']) {
  switch (severity) {
    case 'high': return 'w-2 h-2 bg-red-500 rounded-full'
    case 'medium': return 'w-2 h-2 bg-amber-500 rounded-full'
    case 'low': return 'w-2 h-2 bg-gray-500 rounded-full'
    default: return 'w-2 h-2 bg-gray-500 rounded-full'
  }
}

// Load health data
async function loadHealthData() {
  loading.value = true
  error.value = ''
  try {
    const response = await api.get('/investments/portfolio-health')
    healthResult.value = response.data
  } catch (e: any) {
    error.value = e.response?.data?.detail || '获取组合健康数据失败'
    console.warn('Failed to load portfolio health:', e)
  } finally {
    loading.value = false
  }
}

// Initialize
loadHealthData()
</script>