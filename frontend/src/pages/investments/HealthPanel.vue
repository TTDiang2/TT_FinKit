<template>
  <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
    <div v-if="loading" class="flex items-center justify-center py-8 text-text-muted">
      <span>加载中…</span>
    </div>
    <div v-else-if="error" class="flex items-center justify-center py-8 text-expense-color">
      <span>{{ error }}</span>
    </div>
    <div v-else>
      <!-- Portfolio floating P&L cards -->
      <div v-if="health" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4 text-sm">
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">整体浮盈亏（未平仓）</div>
          <div class="font-semibold text-base" :class="colorClass(health.floating_pnl)">{{ signed(health.floating_pnl) }}</div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">整体浮动收益率</div>
          <div class="font-semibold text-base" :class="colorClass(health.floating_pnl_pct)">
            {{ health.floating_pnl_pct >= 0 ? '+' : '' }}{{ health.floating_pnl_pct.toFixed(2) }}%
          </div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">持仓总市值</div>
          <div class="font-semibold text-base">{{ sym }}{{ fmt(health.total_market_value) }}</div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">持仓总成本（摊薄）</div>
          <div class="font-semibold text-base">{{ sym }}{{ fmt(health.total_cost) }}</div>
        </div>
      </div>

      <!-- Portfolio NAV curve -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2 flex-wrap gap-2">
          <div>
            <h3 class="text-sm font-medium">组合净值曲线</h3>
            <div class="text-xs text-text-muted mt-0.5">单位法：入金/出金不影响曲线涨跌，可直接算波动率与夏普</div>
          </div>
          <div class="flex items-center gap-2">
            <span v-if="navSource" class="text-xs text-text-muted">数据源：{{ navSource }}</span>
            <button v-for="p in PERIODS" :key="p.days" @click="changePeriod(p)"
              :class="['px-2.5 py-1 text-xs rounded-md border', period.days === p.days ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default hover:bg-bg-tertiary']">
              {{ p.label }}
            </button>
          </div>
        </div>
        <div style="height: 280px; position: relative">
          <div v-if="navLoading" class="absolute inset-0 flex items-center justify-center text-text-muted text-sm">组合净值计算中…</div>
          <div v-else-if="navError" class="absolute inset-0 flex flex-col items-center justify-center text-expense-color text-sm">
            <span>{{ navError }}</span>
            <span class="text-xs text-text-muted mt-1">组合曲线需持仓产品都配置代码；单产品曲线请在持仓列表点击名称查看</span>
          </div>
          <Line v-else-if="navSeries.length >= 2" :data="navChartData" :options="navChartOpts" />
          <div v-else class="absolute inset-0 flex items-center justify-center text-text-muted text-sm">区间内数据不足</div>
        </div>
        <div v-if="navMetrics" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-3 text-sm">
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">年化收益率</div>
            <div class="font-semibold" :class="colorClassNullable(navMetrics.ann_return)">{{ pct(navMetrics.ann_return) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">年化波动率</div>
            <div class="font-semibold">{{ pct(navMetrics.ann_volatility) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">夏普比率（rf=2%）</div>
            <div class="font-semibold" :class="colorClassNullable(navMetrics.sharpe)">{{ navMetrics.sharpe === null ? '—' : navMetrics.sharpe.toFixed(2) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">最大回撤</div>
            <div class="font-semibold text-expense-color">{{ pct(navMetrics.max_drawdown) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">Sortino（rf=2%）</div>
            <div class="font-semibold" :class="colorClassNullable(navMetrics.sortino)">{{ navMetrics.sortino === null ? '—' : navMetrics.sortino.toFixed(2) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">Calmar</div>
            <div class="font-semibold" :class="colorClassNullable(navMetrics.calmar)">{{ navMetrics.calmar === null ? '—' : navMetrics.calmar.toFixed(2) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">下行波动率</div>
            <div class="font-semibold">{{ pct(navMetrics.downside_deviation) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-secondary">
            <div class="text-xs text-text-muted">最长回撤期 / 恢复天数</div>
            <div class="font-semibold">
              {{ navMetrics.max_drawdown_duration ?? '—' }}<span class="text-text-muted font-normal">天</span>
              <span class="text-text-muted font-normal"> / </span>
              {{ navMetrics.recovery_days === null ? '未收复' : (navMetrics.recovery_days + '天') }}
            </div>
          </div>
        </div>
        <div v-if="navMetrics && benchmark" class="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-2 text-sm">
          <div class="p-2 rounded-md bg-bg-tertiary">
            <div class="text-xs text-text-muted">沪深300 同期年化</div>
            <div class="font-semibold" :class="colorClassNullable(benchmark.ann_return)">{{ pct(benchmark.ann_return) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-tertiary">
            <div class="text-xs text-text-muted">Beta（vs 沪深300）</div>
            <div class="font-semibold">{{ benchmark.beta === null ? '—' : benchmark.beta.toFixed(2) }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-tertiary">
            <div class="text-xs text-text-muted">Alpha（年化）</div>
            <div class="font-semibold" :class="colorClassNullable(benchmark.alpha)">{{ benchmark.alpha === null ? '—' : (benchmark.alpha * 100).toFixed(2) + '%' }}</div>
          </div>
          <div class="p-2 rounded-md bg-bg-tertiary">
            <div class="text-xs text-text-muted">超额收益（年化）</div>
            <div class="font-semibold" :class="colorClassNullable(benchmark.excess_return)">{{ pct(benchmark.excess_return) }}</div>
          </div>
        </div>
      </div>

      <!-- PnL distribution bar chart -->
      <div class="rounded-lg border border-border-default p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-medium">盈亏分布</h3>
          <div class="flex gap-2">
            <button v-for="g in PNL_GRANS" :key="g.key" @click="changePnlGran(g)"
              :class="['px-2.5 py-1 text-xs rounded-md border', pnlGranularity === g.key ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default hover:bg-bg-tertiary']">
              {{ g.label }}
            </button>
          </div>
        </div>
        <div style="height: 220px; position: relative">
          <div v-if="pnlLoading" class="absolute inset-0 flex items-center justify-center text-text-muted text-sm">盈亏计算中…</div>
          <div v-else-if="pnlError" class="absolute inset-0 flex items-center justify-center text-expense-color text-sm">{{ pnlError }}</div>
          <Bar v-else-if="pnlSeries.length" :data="pnlChartData" :options="pnlChartOpts" />
          <div v-else class="absolute inset-0 flex items-center justify-center text-text-muted text-sm">区间内无数据</div>
        </div>
        <div class="text-xs text-text-muted mt-2">口径：当日盈亏 = 组合市值变动 − 当日净入金（含已实现与浮动盈亏）</div>
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
import { Line, Bar } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'
import type { HealthResult, HealthWarning, NavEvent, PortfolioNavResponse, PnLHistoryResponse } from '@/types'

ChartJS.register(LineElement, PointElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const api = useApi()
const settingsStore = useSettingsStore()
const sym = computed(() => settingsStore.settings.currency_symbol)

const PERIODS = [
  { label: '3月', days: 90 },
  { label: '6月', days: 180 },
  { label: '1年', days: 365 },
  { label: '3年', days: 1095 },
]
const period = ref(PERIODS[2])

const loading = ref(false)
const error = ref('')
const healthResult = ref<HealthResult | null>(null)
const navLoading = ref(false)
const navError = ref('')
const navData = ref<PortfolioNavResponse | null>(null)

const PNL_GRANS = [
  { key: 'day', label: '日' },
  { key: 'month', label: '月' },
  { key: 'year', label: '年' },
]
const pnlGranularity = ref('month')
const pnlLoading = ref(false)
const pnlError = ref('')
const pnlSeries = ref<PnLHistoryResponse['series']>([])

const health = computed(() => healthResult.value)
const navSeries = computed(() => navData.value?.series ?? [])
const navMetrics = computed(() => navData.value?.metrics ?? null)
const benchmark = computed(() => navData.value?.benchmark ?? null)
const navSource = computed(() => {
  const srcs = [...new Set((navData.value?.funds ?? []).map(f => f.source))]
  return srcs.length ? srcs.join('/') : ''
})

function fmt(n: number | undefined): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function signed(n: number | undefined): string { const v = n ?? 0; return (v >= 0 ? '+' : '') + sym.value + fmt(Math.abs(v)) }
function colorClass(n: number): string { return n >= 0 ? 'text-income-color' : 'text-expense-color' }
function colorClassNullable(n: number | null | undefined): string { return n === null || n === undefined ? '' : (n >= 0 ? 'text-income-color' : 'text-expense-color') }
function pct(n: number | null | undefined): string { return n === null || n === undefined ? '—' : (n * 100).toFixed(2) + '%' }

const navEvents = computed(() => navData.value?.events ?? [])
const navEventByDate = computed(() => {
  const m = new Map<string, NavEvent[]>()
  for (const e of navEvents.value) {
    const arr = m.get(e.date) ?? []
    arr.push(e)
    m.set(e.date, arr)
  }
  return m
})

function eventTooltipLines(date: string): string[] {
  const evs = navEventByDate.value.get(date)
  if (!evs) return []
  return evs.map(e => `${e.type === 'buy' ? '申购' : '赎回'} ${e.name} ${e.quantity}份 ${sym.value}${fmt(e.amount)}`)
}

const navChartData = computed(() => {
  const base = navSeries.value.map(p => p.nav)
  const start = base.length && base[0] !== 0 ? base[0] : 1
  const datasets: any[] = [{
    label: '组合净值',
    data: base.map(v => v / start),
    borderColor: '#6366f1',
    backgroundColor: 'rgba(99,102,241,0.08)',
    borderWidth: 1.5,
    tension: 0.25,
    pointRadius: 0,
    pointHoverRadius: 4,
    fill: true,
    yAxisID: 'y',
  }]
  const bm = benchmark.value
  if (bm?.series?.length) {
    const b0 = bm.series[0].close
    if (b0 !== 0) {
      datasets.push({
        label: '沪深300（起点归一）',
        data: bm.series.map(p => p.close / b0),
        borderColor: '#9ca3af',
        borderDash: [5, 4],
        borderWidth: 1.2,
        tension: 0.25,
        pointRadius: 0,
        fill: false,
        yAxisID: 'y',
      })
    }
  }
  if (navEventByDate.value.size) {
    const ev = (type: 'buy' | 'sell') => navSeries.value.map((p, i) => {
      const evs = navEventByDate.value.get(p.date)
      return evs && evs.some(e => e.type === type) ? p.nav / start : null
    })
    datasets.push({
      label: '申购',
      data: ev('buy'),
      borderColor: '#ef4444',
      backgroundColor: '#ef4444',
      pointRadius: 3.5,
      pointHoverRadius: 5,
      showLine: false,
      fill: false,
      yAxisID: 'y',
    })
    datasets.push({
      label: '赎回',
      data: ev('sell'),
      borderColor: '#3b82f6',
      backgroundColor: '#3b82f6',
      pointRadius: 3.5,
      pointHoverRadius: 5,
      showLine: false,
      fill: false,
      yAxisID: 'y',
    })
  }
  return { labels: navSeries.value.map(p => p.date), datasets }
})

const navChartOpts = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { display: !!(benchmark.value?.series?.length || navEventByDate.value.size), labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const p = navSeries.value[ctx.dataIndex]
          if (ctx.dataset.label === '申购') return eventTooltipLines(p?.date ?? '')
          if (ctx.dataset.label === '赎回') return []
          if (!p) return `净值 ${ctx.parsed.y.toFixed(4)}`
          return [`净值 ${p.nav.toFixed(4)}`, `总值 ${sym.value}${fmt(p.total_value)}`]
        },
      },
    },
  },
  scales: {
    x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 }, grid: { display: false } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => Number(v).toFixed(3) }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
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

async function loadNav() {
  navLoading.value = true
  navError.value = ''
  try {
    const res = await api.get('/investments/portfolio-nav', { params: { days: period.value.days } })
    navData.value = res.data
  } catch (e: any) {
    navData.value = null
    navError.value = e.response?.data?.detail || '组合净值获取失败'
  } finally {
    navLoading.value = false
  }
}

function changePeriod(p: { label: string; days: number }) {
  if (period.value.days === p.days) return
  period.value = p
  loadNav()
  loadPnl()
}

async function loadPnl() {
  pnlLoading.value = true
  pnlError.value = ''
  try {
    const res = await api.get('/investments/pnl-history', {
      params: { granularity: pnlGranularity.value, days: period.value.days },
    })
    pnlSeries.value = res.data?.series ?? []
  } catch (e: any) {
    pnlSeries.value = []
    pnlError.value = e.response?.data?.detail || '盈亏数据获取失败'
  } finally {
    pnlLoading.value = false
  }
}

function changePnlGran(g: { key: string; label: string }) {
  if (pnlGranularity.value === g.key) return
  pnlGranularity.value = g.key
  loadPnl()
}

const pnlChartData = computed(() => {
  const items = pnlSeries.value
  return {
    labels: items.map(p => p.date),
    datasets: [{
      label: '盈亏（元）',
      data: items.map(p => p.pnl),
      backgroundColor: items.map(p => (p.pnl >= 0 ? 'rgba(34,197,94,0.75)' : 'rgba(239,68,68,0.75)')),
      borderColor: items.map(p => (p.pnl >= 0 ? '#16a34a' : '#dc2626')),
      borderWidth: 1,
      maxBarThickness: 40,
    }],
  }
})

const pnlChartOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const v = ctx.parsed.y as number
          return (v >= 0 ? '+' : '') + sym.value + fmt(v)
        },
      },
    },
  },
  scales: {
    y: {
      ticks: { callback: (v: any) => sym.value + fmt(Number(v)) },
    },
  },
}

function refresh() {
  loadHealthData()
  loadNav()
  loadPnl()
}

loadHealthData()
loadNav()
loadPnl()
defineExpose({ refresh })
</script>