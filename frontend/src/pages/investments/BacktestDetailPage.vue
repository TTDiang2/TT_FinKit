<template>
  <div v-if="backtest">
    <div class="flex items-center gap-3 mb-4">
      <button @click="goBack" class="text-text-secondary hover:text-text-primary">← 返回</button>
      <h2 class="text-lg font-semibold">回测详情</h2>
      <span :class="statusClass(backtest.status)" class="px-1.5 py-0.5 text-xs rounded">{{ statusLabel(backtest.status) }}</span>
      <span v-if="backtest.strategy_name" class="text-sm text-text-muted">· {{ backtest.strategy_name }}</span>
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
          <div class="text-xl font-semibold text-text-primary">{{ fmtPct(backtest.results.metrics.ann_volatility) }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">夏普比率</div>
          <div class="text-xl font-semibold text-text-primary">{{ backtest.results.metrics.sharpe.toFixed(2) }}</div>
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
          <div class="text-xl font-semibold text-expense-color">{{ fmtPct(backtest.results.metrics.total_cost_ratio) }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">年换手率</div>
          <div class="text-xl font-semibold text-text-primary">{{ fmtPct(backtest.results.metrics.turnover_annual) }}</div>
        </div>
      </div>

      <!-- 净值曲线 (chart.js) + 买卖点标注 -->
      <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
        <h3 class="text-sm font-medium mb-3">净值曲线 <span class="text-xs text-text-muted font-normal">· 绿↑=买入 红↓=卖出 · 悬停查看详情</span></h3>
        <div style="height: 340px">
          <Line v-if="navChartData" :data="navChartData" :options="navChartOpts" />
        </div>
      </div>

      <!-- 因子效果 -->
      <div v-if="backtest.factor_keys?.length" class="bg-white rounded-lg shadow-sm p-4 mb-4">
        <h3 class="text-sm font-medium mb-3">策略因子效果</h3>
        <div class="grid grid-cols-4 gap-3">
          <div v-for="fk in backtest.factor_keys" :key="fk" class="border border-border-default rounded-lg p-3">
            <div class="text-xs text-text-muted mb-1">{{ factorName(fk) }}</div>
            <div v-if="factorEvalMap[fk]" class="space-y-0.5">
              <div class="flex justify-between text-xs"><span class="text-text-muted">IC</span><span :class="icColor(factorEvalMap[fk].ic_mean)">{{ factorEvalMap[fk].ic_mean.toFixed(4) }}</span></div>
              <div class="flex justify-between text-xs"><span class="text-text-muted">ICIR</span><span :class="icirColor(factorEvalMap[fk].icir)">{{ factorEvalMap[fk].icir.toFixed(3) }}</span></div>
              <div class="flex justify-between text-xs"><span class="text-text-muted">胜率</span><span>{{ (factorEvalMap[fk].win_rate * 100).toFixed(0) }}%</span></div>
              <div class="flex justify-between text-xs"><span class="text-text-muted">多空夏普</span><span>{{ factorEvalMap[fk].ls_sharpe?.toFixed(2) ?? '—' }}</span></div>
            </div>
            <div v-else class="text-xs text-text-muted py-2">暂无评估数据</div>
          </div>
        </div>
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
                <span v-for="t in rec.trades" :key="t.symbol" class="mr-2">
                  <span :class="t.side === 'buy' ? 'text-income-color' : 'text-expense-color'">{{ t.side === 'buy' ? '买' : '卖' }}</span>
                  {{ t.symbol }} ¥{{ t.amount.toFixed(0) }}
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
import { useRouter, useRoute } from 'vue-router'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'
import type { BacktestResponse } from '@/types'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const router = useRouter()
const route = useRoute()
const api = useApi()
const backtest = ref<BacktestResponse | null>(null)
const evalData = ref<{ thresholds: Record<string, number>; evaluations: any[] } | null>(null)

function goBack() {
  router.push('/investments/strategies?sub=backtest')
}

// NAV chart data: line + buy/sell scatter overlay
const navChartData = computed(() => {
  const r = backtest.value?.results
  if (!r?.nav_series?.length) return null
  const labels = r.nav_series.map(p => p.date)
  const navData = r.nav_series.map(p => p.nav)

  // Build buy/sell marker arrays aligned to nav_series labels (null = no trade that day)
  const dateIdx: Record<string, number> = {}
  r.nav_series.forEach((p, i) => { dateIdx[p.date] = i })
  const buyData: (number | null)[] = new Array(labels.length).fill(null)
  const sellData: (number | null)[] = new Array(labels.length).fill(null)
  const buyMeta: any[] = new Array(labels.length).fill(null)
  const sellMeta: any[] = new Array(labels.length).fill(null)
  for (const rec of r.rebalance_records) {
    const idx = dateIdx[rec.date]
    if (idx == null) continue
    const nav = r.nav_series[idx].nav
    const buys = rec.trades.filter(t => t.side === 'buy')
    const sells = rec.trades.filter(t => t.side === 'sell')
    if (buys.length) { buyData[idx] = nav; buyMeta[idx] = buys.map(t => `${t.symbol} ¥${t.amount.toFixed(0)}`).join(', ') }
    if (sells.length) { sellData[idx] = nav; sellMeta[idx] = sells.map(t => `${t.symbol} ¥${t.amount.toFixed(0)}`).join(', ') }
  }
  return {
    labels,
    datasets: [
      {
        label: '净值',
        data: navData,
        borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)',
        borderWidth: 1.5, tension: 0.25, pointRadius: 0, fill: true,
      },
      {
        label: '买入',
        data: buyData,
        borderColor: 'transparent', backgroundColor: '#10b981',
        pointStyle: 'triangle', pointRadius: 5, pointHoverRadius: 8,
        showLine: false,
        _meta: buyMeta,
      },
      {
        label: '卖出',
        data: sellData,
        borderColor: 'transparent', backgroundColor: '#ef4444',
        pointStyle: 'triangle', pointRotation: 180, pointRadius: 5, pointHoverRadius: 8,
        showLine: false,
        _meta: sellMeta,
      },
    ],
  }
})

const navChartOpts = {
  responsive: true, maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const ds = ctx.dataset
          const v = ctx.parsed.y
          if (ds.label === '净值') return `净值: ${v.toFixed(4)}`
          if (v == null) return ''
          const meta = ds._meta?.[ctx.dataIndex]
          if (meta) return `${ds.label}: ${meta}`
          return `${ds.label}`
        },
      },
    },
  },
  scales: {
    x: { ticks: { maxTicksLimit: 12, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 }, grid: { display: false } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => Number(v).toFixed(3) }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

// Factor evaluation lookup
const factorEvalMap = computed(() => {
  const map: Record<string, any> = {}
  if (!evalData.value?.evaluations) return map
  for (const e of evalData.value.evaluations) {
    map[e.factor_key] = e
  }
  return map
})

function factorName(key: string): string {
  const e = factorEvalMap.value[key]
  return e?.factor_name || key
}

function icColor(v: number) { return Math.abs(v) > 0.05 ? 'text-income-color' : 'text-text-muted' }
function icirColor(v: number) { return v > 0.5 ? 'text-income-color' : v > 0.3 ? 'text-warning' : 'text-text-muted' }

async function load() {
  const id = route.params.id as string
  const { data } = await api.get<BacktestResponse>(`/backtests/${id}`)
  backtest.value = data
  // Load factor evaluations if strategy declares factor_keys
  if (data.factor_keys?.length) {
    try {
      const { data: evals } = await api.get('/research/factors/evaluations')
      evalData.value = evals
    } catch { /* evaluation not critical */ }
  }
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
