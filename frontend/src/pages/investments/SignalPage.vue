<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">信号</h2>
      <button @click="runSignal" :disabled="running" class="btn-primary disabled:opacity-50">
        <Zap :size="14" /> {{ running ? '生成中...' : '运行策略生成信号' }}
      </button>
    </div>

    <!-- 当前信号 -->
    <div v-if="currentSignal" class="bg-white rounded-lg shadow-sm p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-medium">当前信号</h3>
        <div class="text-xs text-text-muted">
          生成于 {{ currentSignal.run_date }} | 数据截止 {{ currentSignal.as_of_date }}
        </div>
      </div>

      <!-- 风险告警 -->
      <div v-if="currentSignal.risk_status?.warnings?.length" class="mb-4">
        <div v-for="w in currentSignal.risk_status.warnings" :key="w"
          class="flex items-center gap-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700 mb-1">
          <span>⚠</span> {{ w }}
        </div>
      </div>

      <!-- 目标权重表 -->
      <div class="mb-4">
        <h4 class="text-sm font-medium mb-2">目标权重</h4>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-1.5 font-medium">标的</th>
              <th class="px-3 py-1.5 font-medium text-right">目标权重</th>
              <th class="px-3 py-1.5 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(weight, assetId) in currentSignal.target_weights" :key="assetId"
              class="border-t border-border-default">
              <td class="px-3 py-1.5 font-medium">{{ assetId }}</td>
              <td class="px-3 py-1.5 text-right">{{ (weight * 100).toFixed(1) }}%</td>
              <td class="px-3 py-1.5 text-right">
                <button class="text-xs text-accent-primary hover:underline">加为持仓</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 下一调仓日 -->
      <div v-if="currentSignal.next_rebalance_date" class="flex items-center gap-2 px-3 py-2 bg-blue-50 rounded text-sm">
        <span class="text-blue-600">📅</span>
        下一调仓日：<span class="font-medium">{{ currentSignal.next_rebalance_date }}</span>
      </div>
    </div>

    <div v-else class="bg-white rounded-lg shadow-sm p-8 text-center text-text-muted mb-6">
      暂无信号。请先在策略库激活或导入策略，然后运行策略生成信号。
    </div>

    <!-- 错误提示 -->
    <div v-if="runError" class="mb-4 px-4 py-3 bg-expense-bg border border-expense-color rounded text-sm text-expense-color">
      {{ runError }}
    </div>

    <!-- 历史信号 -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <div class="px-4 py-3 bg-bg-tertiary font-medium text-sm">历史信号</div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">运行日期</th>
            <th class="px-3 py-2 font-medium">数据截止日</th>
            <th class="px-3 py-2 font-medium text-center">下一调仓日</th>
            <th class="px-3 py-2 font-medium">关联回测</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sig in signals" :key="sig.id" class="border-t border-border-default">
            <td class="px-3 py-2">{{ sig.run_date }}</td>
            <td class="px-3 py-2 text-text-secondary">{{ sig.as_of_date }}</td>
            <td class="px-3 py-2 text-center text-text-secondary">{{ sig.next_rebalance_date || '-' }}</td>
            <td class="px-3 py-2 text-xs text-text-muted">{{ sig.backtest_id ? sig.backtest_id.slice(0, 8) + '...' : '-' }}</td>
          </tr>
          <tr v-if="!signals.length">
            <td colspan="4" class="px-4 py-6 text-center text-text-muted">暂无历史信号</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { AxiosError } from 'axios'
import { Zap } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import type { SignalResponse, SignalRunResult } from '@/types'

const api = useApi()
const currentSignal = ref<SignalResponse | null>(null)
const signals = ref<SignalResponse[]>([])
const running = ref(false)
const runError = ref('')

async function loadSignals() {
  const [current, list] = await Promise.all([
    api.get<SignalResponse | null>('/signals/current').then(r => r.data).catch(() => null),
    api.get<SignalResponse[]>('/signals').then(r => r.data).catch(() => []),
  ])
  currentSignal.value = current
  signals.value = list
}

async function runSignal() {
  running.value = true
  runError.value = ''
  try {
    const result = await api.post<SignalRunResult>('/signals/run', {})
    if (result.data.status === 'ok') {
      await loadSignals()
    } else {
      runError.value = result.data.error || '信号生成失败'
    }
  } catch (e) {
    const err = e as AxiosError<{ detail?: string }>
    runError.value = err.response?.data?.detail || String(e)
  } finally {
    running.value = false
  }
}

onMounted(loadSignals)
</script>
