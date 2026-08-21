<template>
  <div v-if="backtest">
    <div class="flex items-center gap-3 mb-4">
      <button @click="$router.back()" class="text-text-secondary hover:text-text-primary">← 返回</button>
      <h2 class="text-lg font-semibold">回测详情</h2>
      <span :class="statusClass(backtest.status)" class="px-1.5 py-0.5 text-xs rounded">{{ statusLabel(backtest.status) }}</span>
    </div>

    <div v-if="backtest.status === 'done' && backtest.results">
      <!-- 核心指标卡 -->
      <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">年化收益</div>
          <div class="text-xl font-semibold" :class="backtest.results.metrics.ann_return >= 0 ? 'text-income-color' : 'text-expense-color'">
            {{ fmtPct(backtest.results.metrics.ann_return) }}
          </div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">年化波动</div>
          <div class="text-xl font-semibold text-text-primary">
            {{ fmtPct(backtest.results.metrics.ann_volatility) }}
          </div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">夏普比率</div>
          <div class="text-xl font-semibold text-text-primary">
            {{ backtest.results.metrics.sharpe.toFixed(2) }}
          </div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">最大回撤</div>
          <div class="text-xl font-semibold" :class="backtest.results.metrics.max_drawdown < 0 ? 'text-expense-color' : 'text-text-primary'">
            {{ fmtPct(backtest.results.metrics.max_drawdown) }}
          </div>
        </div>
      </div>

      <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">Calmar</div>
          <div class="text-xl font-semibold text-text-primary">{{ backtest.results.metrics.calmar.toFixed(2) }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">索提诺</div>
          <div class="text-xl font-semibold text-text-primary">{{ backtest.results.metrics.sortino.toFixed(2) }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">总成本</div>
          <div class="text-xl font-semibold text-expense-color">{{ fmtPct(backtest.results.metrics.total_cost) }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">年换手率</div>
          <div class="text-xl font-semibold text-text-primary">{{ fmtPct(backtest.results.metrics.turnover_annual) }}</div>
        </div>
      </div>

      <!-- 净值曲线 (simple SVG polyline) -->
      <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
        <h3 class="text-sm font-medium mb-3">净值曲线</h3>
        <svg :viewBox="`0 0 ${navWidth} ${navHeight}`" class="w-full" style="height: 200px;">
          <polyline :points="navPoints" fill="none" stroke="#3b82f6" stroke-width="2" />
        </svg>
      </div>

      <!-- 调仓记录 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">调仓记录</h3>
        <table class="w-full text-xs">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-2 py-1.5 font-medium">日期</th>
              <th class="px-2 py-1.5 font-medium">交易</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rec in backtest.results.rebalance_records" :key="rec.date" class="border-t border-border-default">
              <td class="px-2 py-1.5">{{ rec.date }}</td>
              <td class="px-2 py-1.5">
                <span v-for="t in rec.trades" :key="t.asset_id" class="mr-2">
                  <span :class="t.side === 'buy' ? 'text-income-color' : 'text-expense-color'">{{ t.side === 'buy' ? '买' : '卖' }}</span>
                  {{ t.asset_id }} ¥{{ t.amount.toFixed(0) }}
                </span>
              </td>
            </tr>
            <tr v-if="!backtest.results.rebalance_records.length">
              <td colspan="2" class="px-2 py-2 text-center text-text-muted">无调仓记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else-if="backtest.status === 'failed'" class="bg-expense-bg rounded-lg p-4">
      <div class="text-expense-color font-medium">回测失败</div>
      <div class="text-sm text-expense-color mt-1">{{ backtest.error }}</div>
    </div>
    <div v-else-if="backtest.status === 'running' || backtest.status === 'pending'" class="bg-blue-50 rounded-lg p-4">
      <div class="text-blue-700">回测进行中，请稍后刷新...</div>
    </div>
  </div>
  <div v-else class="text-center py-8 text-text-muted">加载中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApi } from '@/composables/useApi'
import type { BacktestResponse } from '@/types'

const route = useRoute()
const api = useApi()
const backtest = ref<BacktestResponse | null>(null)
const navWidth = 600
const navHeight = 180

const navPoints = computed(() => {
  if (!backtest.value?.results?.nav_series?.length) return ''
  const series = backtest.value.results.nav_series
  const vals = series.map(p => p.nav)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  return series.map((p, i) => {
    const x = (i / (series.length - 1)) * navWidth
    const y = navHeight - ((p.nav - min) / range) * (navHeight - 20) - 10
    return `${x},${y}`
  }).join(' ')
})

async function load() {
  const id = route.params.id as string
  const { data } = await api.get<BacktestResponse>(`/backtests/${id}`)
  backtest.value = data
}

function fmtPct(v?: number) { return v != null ? `${(v * 100).toFixed(1)}%` : '-' }
function statusClass(s: string) {
  const m = { done: 'bg-income-bg text-income-color', running: 'bg-blue-100 text-blue-700', failed: 'bg-expense-bg text-expense-color', pending: 'bg-gray-100 text-gray-500' }
  return m[s as keyof typeof m] || ''
}
function statusLabel(s: string) {
  const m = { done: '完成', running: '运行中', failed: '失败', pending: '等待' }
  return m[s as keyof typeof m] || s
}

onMounted(load)
</script>
