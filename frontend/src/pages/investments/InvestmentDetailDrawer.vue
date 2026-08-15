<template>
  <teleport to="body">
    <div class="fixed inset-0 bg-black/40 z-40" @click="$emit('close')"></div>
    <div class="fixed inset-y-0 right-0 w-full max-w-[680px] bg-bg-primary shadow-2xl z-50 overflow-y-auto">
      <!-- Header -->
      <div class="sticky top-0 bg-bg-primary border-b border-border-default px-6 py-4 flex items-center justify-between z-10">
        <div>
          <h2 class="text-lg font-semibold">{{ investment.name }}</h2>
          <div class="text-xs text-text-muted mt-0.5">
            {{ TYPE_LABELS[investment.investment_type] || investment.investment_type }}
            <span v-if="investment.symbol"> · {{ investment.exchange }} {{ investment.symbol }}</span>
            <span v-if="investment.quantity"> · 持仓 {{ investment.quantity }}</span>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <button @click="showMigration = true"
                  class="text-sm px-3 py-1.5 border border-border-default rounded-md hover:bg-bg-tertiary text-text-secondary">
            补录投入
          </button>
          <button @click="$emit('close')" class="text-text-muted hover:text-text-primary text-3xl leading-none px-2">×</button>
        </div>
      </div>

      <div class="p-6 space-y-5">
        <!-- Metric cards -->
        <div class="grid grid-cols-3 gap-3">
          <div class="bg-white rounded-lg p-3 shadow-sm">
            <div class="text-xs text-text-muted">成本价（均价）</div>
            <div class="text-base font-semibold mt-1">{{ sym }}{{ fmt(costBasis) }}</div>
          </div>
          <div class="bg-white rounded-lg p-3 shadow-sm">
            <div class="text-xs text-text-muted">现价</div>
            <div class="text-base font-semibold mt-1">{{ sym }}{{ fmt(investment.current_price) }}</div>
          </div>
          <div class="bg-white rounded-lg p-3 shadow-sm">
            <div class="text-xs text-text-muted">距成本</div>
            <div class="text-base font-semibold mt-1" :class="costDist >= 0 ? 'text-income-color' : 'text-expense-color'">
              {{ costDist >= 0 ? '+' : '' }}{{ costDist.toFixed(2) }}%
            </div>
          </div>
          <div class="bg-white rounded-lg p-3 shadow-sm">
            <div class="text-xs text-text-muted">浮动盈亏</div>
            <div class="text-base font-semibold mt-1" :class="(investment.profit_loss || 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
              {{ signed(investment.profit_loss) }}
            </div>
          </div>
          <div class="bg-white rounded-lg p-3 shadow-sm">
            <div class="text-xs text-text-muted">最大回撤({{ period.label }})</div>
            <div class="text-base font-semibold mt-1 text-expense-color">{{ (maxDrawdown * 100).toFixed(1) }}%</div>
          </div>
          <div class="bg-white rounded-lg p-3 shadow-sm">
            <div class="text-xs text-text-muted">持有天数</div>
            <div class="text-base font-semibold mt-1">{{ daysHeld }} 天</div>
          </div>
        </div>

        <!-- Period switcher -->
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs text-text-muted mr-1">区间：</span>
          <button v-for="p in PERIODS" :key="p.days" @click="changePeriod(p)"
            :class="['px-3 py-1 text-xs rounded-md border', period.days === p.days ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default hover:bg-bg-tertiary']">
            {{ p.label }}
          </button>
          <span v-if="!loading && series.length" class="text-xs text-text-muted ml-auto">{{ series.length }} 个交易日</span>
        </div>

        <!-- NAV curve -->
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm font-medium mb-2">净值曲线 · 买卖点回顾</div>
          <div style="height: 340px; position: relative">
            <div v-if="loading" class="absolute inset-0 flex items-center justify-center text-text-muted">加载中…</div>
            <div v-else-if="error" class="absolute inset-0 flex flex-col items-center justify-center text-expense-color text-sm">
              <span>{{ error }}</span>
              <span class="text-xs text-text-muted mt-1">{{ errorHint }}</span>
            </div>
            <Line v-else-if="series.length >= 2" :data="chartData" :options="chartOpts" />
            <div v-else class="absolute inset-0 flex items-center justify-center text-text-muted text-sm">区间内数据不足</div>
          </div>
          <!-- Legend -->
          <div class="flex items-center gap-4 mt-2 text-xs text-text-muted flex-wrap">
            <span class="flex items-center gap-1"><span class="inline-block w-3 h-0.5 bg-blue-500"></span> 收盘净值</span>
            <span class="flex items-center gap-1"><span class="inline-block w-3 h-0 border-t-2 border-dashed border-orange-500"></span> 成本线</span>
            <span class="flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500"></span> 买入</span>
            <span class="flex items-center gap-1"><span class="inline-block w-2.5 h-2.5 rounded-full bg-red-500"></span> 卖出</span>
          </div>
        </div>

        <!-- Events timeline -->
        <div>
          <h3 class="text-sm font-semibold mb-2">交易流水（{{ events.length }} 条）</h3>
          <div class="space-y-1.5">
            <div v-for="tx in events" :key="tx.id"
              class="flex items-center gap-3 bg-white rounded-md px-3 py-2 shadow-sm text-sm">
              <span :class="['w-1.5 h-1.5 rounded-full shrink-0', dotColor(tx.event_type)]"></span>
              <span class="text-text-muted text-xs w-24 shrink-0">{{ tx.event_date }}</span>
              <span class="font-medium w-14 shrink-0" :class="tx.event_type === 'buy' ? 'text-income-color' : (tx.event_type === 'sell' ? 'text-expense-color' : 'text-text-secondary')">
                {{ TX_LABELS[tx.event_type] }}
              </span>
              <span class="text-text-secondary flex-1">
                <template v-if="tx.event_type === 'buy' || tx.event_type === 'sell'">
                  {{ Math.abs(tx.quantity) }} 份 @ {{ sym }}{{ fmt(tx.unit_price) }}
                </template>
                <template v-else-if="tx.event_type === 'dividend'">分红 {{ sym }}{{ fmt(Math.abs(tx.amount)) }}</template>
                <template v-else-if="tx.event_type === 'fee'">费用 {{ sym }}{{ fmt(Math.abs(tx.amount)) }}</template>
                <template v-else>{{ sym }}{{ fmt(Math.abs(tx.amount || 0)) }}</template>
              </span>
              <span v-if="tx.notes" class="text-xs text-text-muted truncate max-w-[160px]">{{ tx.notes }}</span>
            </div>
            <div v-if="!events.length" class="text-center text-text-muted text-sm py-4">暂无流水记录</div>
          </div>
        </div>
      </div>
    </div>
    <MigrationWizard v-if="showMigration" :investment="investment"
                     @close="showMigration = false"
                     @done="() => { showMigration = false; emit('updated'); loadHistory() }" />
  </teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import type { Investment, InvestmentTransaction, NavHistoryPoint } from '@/types'
import MigrationWizard from './MigrationWizard.vue'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const props = defineProps<{ investment: Investment }>()
const emit = defineEmits<{ close: []; updated: [] }>()

const api = useApi()
const settingsStore = useSettingsStore()
const sym = computed(() => settingsStore.settings.currency_symbol)

const TYPE_LABELS: Record<string, string> = { stock: '股票', fund: '基金', bond: '债券', crypto: '加密货币', deposit: '存款', other: '其他' }
const TX_LABELS: Record<string, string> = { buy: '买入', sell: '卖出', dividend: '分红', fee: '费用', adjustment: '调整' }
const PERIODS = [
  { label: '1月', days: 30 },
  { label: '3月', days: 90 },
  { label: '6月', days: 180 },
  { label: '1年', days: 365 },
  { label: '3年', days: 1095 },
]
const period = ref(PERIODS[3])
const showMigration = ref(false)

function fmt(n: number | undefined): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) }
function signed(n: number | undefined): string { const v = n ?? 0; return (v >= 0 ? '+' : '') + sym.value + fmt(Math.abs(v)) }
function dotColor(t: string): string {
  return t === 'buy' ? 'bg-emerald-500' : t === 'sell' ? 'bg-red-500' : t === 'dividend' ? 'bg-amber-500' : t === 'fee' ? 'bg-purple-500' : 'bg-gray-400'
}

// State
const loading = ref(false)
const error = ref('')
const errorHint = ref('')
const series = ref<NavHistoryPoint[]>([])
const events = ref<InvestmentTransaction[]>([])
const costBasis = ref(0)
const maxDrawdown = ref(0)

const costDist = computed(() => {
  const cb = costBasis.value || props.investment.purchase_price || 0
  const cur = props.investment.current_price || 0
  if (cb <= 0) return 0
  return ((cur - cb) / cb) * 100
})
const daysHeld = computed(() => {
  if (!props.investment.purchase_date) return 0
  const d = new Date(props.investment.purchase_date).getTime()
  if (isNaN(d)) return 0
  return Math.max(0, Math.floor((Date.now() - d) / 86400000))
})

// Chart data: NAV line + cost line + buy/sell scatter markers + MA lines
const chartData = computed(() => {
  const labels = series.value.map(p => p.date)
  const closes = series.value.map(p => p.close)
  const ma20 = series.value.map(p => p.ma20)
  const ma60 = series.value.map(p => p.ma60)
  const cb = costBasis.value || 0
  const costLine = labels.map(() => cb)

  // Map event dates onto the series by nearest preceding trading day
  const dateIndex = new Map<string, number>()
  labels.forEach((d, i) => dateIndex.set(d, i))
  const buyMarkers: (number | null)[] = labels.map(() => null)
  const sellMarkers: (number | null)[] = labels.map(() => null)
  const markerMeta: Record<string, { type: string; idx: number; tx: InvestmentTransaction }[]> = {}
  for (const tx of events.value) {
    if (tx.event_type !== 'buy' && tx.event_type !== 'sell') continue
    // exact match, else nearest preceding trading day
    let idx = dateIndex.get(tx.event_date)
    if (idx === undefined) {
      // find latest date <= event_date
      let best: number | null = null
      for (let i = 0; i < labels.length; i++) {
        if (labels[i] <= tx.event_date) best = i
        else break
      }
      idx = best ?? -1
    }
    if (idx < 0) continue
    const yVal = series.value[idx]?.close ?? tx.unit_price
    if (tx.event_type === 'buy') buyMarkers[idx] = yVal
    else sellMarkers[idx] = yVal
    const key = String(idx)
    ;(markerMeta[key] = markerMeta[key] || []).push({ type: tx.event_type, idx, tx })
  }

  return {
    labels,
    datasets: [
      {
        label: '收盘净值',
        data: closes,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59,130,246,0.08)',
        borderWidth: 1.5,
        tension: 0.25,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: true,
      },
      {
        label: '成本线',
        data: costLine,
        borderColor: '#f97316',
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        pointHoverRadius: 0,
        fill: false,
      },
      {
        label: 'MA20',
        data: ma20,
        borderColor: '#F59E0B',
        borderWidth: 1.5,
        borderDash: [5, 5],
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      },
      {
        label: 'MA60',
        data: ma60,
        borderColor: '#8B5CF6',
        borderWidth: 1.5,
        borderDash: [5, 5],
        pointRadius: 0,
        tension: 0.3,
        fill: false,
      },
      {
        label: '买入',
        data: buyMarkers,
        borderColor: '#10b981',
        backgroundColor: '#10b981',
        showLine: false,
        pointStyle: 'circle',
        pointRadius: 6,
        pointHoverRadius: 8,
      },
      {
        label: '卖出',
        data: sellMarkers,
        borderColor: '#ef4444',
        backgroundColor: '#ef4444',
        showLine: false,
        pointStyle: 'rectRot',
        pointRadius: 6,
        pointHoverRadius: 8,
      },
    ],
    // stash for tooltip lookup
    _markerMeta: markerMeta,
  } as any
})

const chartOpts = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { display: true },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const ds = ctx.dataset.label
          const val = ctx.parsed.y
          if (val === null) return
          if (ds === '收盘净值') return `${ds}: ${sym.value}${fmt(val)}`
          if (ds === '成本线') return `${ds}: ${sym.value}${fmt(val)}`
          if (ds === 'MA20' || ds === 'MA60') return `${ds}: ${sym.value}${fmt(val)}`
          // buy/sell marker — enrich with transaction detail
          const meta = (ctx.chart.data as any)._markerMeta?.[String(ctx.dataIndex)] || []
          const lines = [ds]
          for (const m of meta) {
            lines.push(`  ${TX_LABELS[m.tx.event_type]} ${Math.abs(m.tx.quantity)} @ ${sym.value}${fmt(m.tx.unit_price)}`)
          }
          return lines
        },
      },
    },
  },
  scales: {
    x: {
      ticks: { maxTicksLimit: 8, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 },
      grid: { display: false },
    },
    y: {
      ticks: { font: { size: 10 }, callback: (v: any) => sym.value + Number(v).toFixed(2) },
      grid: { color: 'rgba(0,0,0,0.05)' },
    },
  },
}))

async function loadHistory() {
  loading.value = true
  error.value = ''
  errorHint.value = ''
  try {
    const res = await api.get(`/investments/${props.investment.id}/nav-history`, { params: { days: period.value.days } })
    const data = res.data
    series.value = data.series || []
    events.value = (data.events || []) as InvestmentTransaction[]
    // events come oldest-first from API; reverse for timeline display
    events.value = [...events.value].reverse()
    costBasis.value = data.cost_basis || 0
    maxDrawdown.value = data.max_drawdown || 0
  } catch (e: any) {
    series.value = []
    error.value = e.response?.data?.detail || e.message || '获取净值历史失败'
    if (error.value.includes('凭证') || error.value.includes('iFinD')) {
      errorHint.value = '请在「设置」中配置同花顺 iFinD 账号'
    } else if (error.value.includes('代码') || error.value.includes('市场')) {
      errorHint.value = '请为该产品设置交易代码与市场'
    }
  } finally {
    loading.value = false
  }
}

function changePeriod(p: { label: string; days: number }) {
  if (period.value.days === p.days) return
  period.value = p
  loadHistory()
}

watch(() => props.investment.id, () => loadHistory())
onMounted(() => loadHistory())
</script>
