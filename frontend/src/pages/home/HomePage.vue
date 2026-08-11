<template>
  <div class="p-6">
    <h1 class="text-xl font-bold mb-6">首页</h1>
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-2">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">总资产</div>
        <div class="text-lg font-bold truncate">{{ sym }}{{ fmt(overview?.total_assets) }}</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">本月收入</div>
        <div class="text-lg font-bold text-income-color truncate">{{ sym }}{{ fmt(overview?.total_income_month) }}</div>
        <div class="text-xs mt-0.5" :class="(overview?.vs_last_month_income ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
          {{ (overview?.vs_last_month_income ?? 0) >= 0 ? '↑' : '↓' }} {{ Math.abs(overview?.vs_last_month_income ?? 0) }}%
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">本月支出</div>
        <div class="text-lg font-bold text-expense-color truncate">{{ sym }}{{ fmt(overview?.total_expense_month) }}</div>
        <div class="text-xs text-text-muted mt-0.5">{{ sym }}{{ fmt(overview?.avg_daily_expense) }}/日</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">本月结余</div>
        <div class="text-lg font-bold truncate" :class="(overview?.net_balance ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
          {{ sym }}{{ fmt(overview?.net_balance) }}
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">储蓄率</div>
        <div class="text-lg font-bold text-accent-primary">{{ fmt(overview?.savings_rate, 1) }}%</div>
        <div class="text-[10px] text-text-muted mt-0.5">=(收入-支出)/收入</div>
      </div>
    </div>
    <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">必要支出占比</div>
        <div class="text-lg font-bold text-expense-color">{{ fmt(overview?.necessary_expense_ratio, 1) }}%</div>
        <div class="text-[10px] text-text-muted mt-0.5">近三月</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">投资比率</div>
        <div class="text-lg font-bold text-accent-primary">{{ fmt(overview?.investment_ratio, 1) }}%</div>
        <div class="text-[10px] text-text-muted mt-0.5">=投资/总资产</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">紧急储备</div>
        <div class="text-lg font-bold truncate">{{ fmt(overview?.emergency_reserve_coverage, 1) }}月</div>
        <div class="text-[10px] mt-0.5" :class="(overview?.emergency_reserve_coverage ?? 0) < 3 ? 'text-expense-color' : (overview?.emergency_reserve_coverage ?? 0) >= 6 ? 'text-income-color' : 'text-text-muted'">
          {{ (overview?.emergency_reserve_coverage ?? 0) < 3 ? '危险' : (overview?.emergency_reserve_coverage ?? 0) >= 6 ? '安全' : '正常' }}
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">净资产增长</div>
        <div class="text-lg font-bold truncate" :class="(overview?.net_worth_growth_rate ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
          {{ (overview?.net_worth_growth_rate ?? 0) >= 0 ? '↑' : '↓' }}{{ fmt(Math.abs(overview?.net_worth_growth_rate ?? 0), 1) }}%
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-xs text-text-secondary mb-0.5">投资收益率</div>
        <div class="text-lg font-bold truncate" :class="(overview?.investment_return_rate ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
          {{ (overview?.investment_return_rate ?? 0) >= 0 ? '↑' : '↓' }}{{ fmt(Math.abs(overview?.investment_return_rate ?? 0), 1) }}%
        </div>
        <div class="text-[10px] text-text-muted mt-0.5">年化: {{ fmt(overview?.investment_return_rate_annualized, 1) }}%</div>
      </div>
    </div>

    <div class="bg-white rounded-lg p-5 shadow-sm mb-6">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold">支出分类</h3>
        <div class="flex gap-2 text-xs">
          <button v-for="range in dateRanges" :key="range.label" @click="setDateRange(range)" class="px-2 py-1 border rounded text-text-secondary hover:bg-gray-50 transition-colors" :class="activeRange === range.label ? 'border-accent-primary bg-accent-primary/10' : 'border-border-default'">
            {{ range.label }}
          </button>
        </div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="flex items-center justify-center">
          <div class="w-96">
            <Doughnut v-if="expenseData.labels.length" :data="expenseData" :options="{ responsive: true, plugins: { legend: { position: 'right' as const } } }" />
          </div>
        </div>
        <div>
          <h4 class="font-medium text-sm text-text-secondary mb-2">Top 支出</h4>
          <div v-if="topExpenses.length" class="space-y-2">
            <div v-for="(txn, i) in topExpenses" :key="txn.id" class="flex items-center gap-3 py-1.5 border-b border-border-default last:border-0">
              <span class="w-5 h-5 rounded-full bg-expense-color text-white text-xs flex items-center justify-center flex-shrink-0">{{ i + 1 }}</span>
              <div class="flex-1 min-w-0">
                <div class="text-sm truncate">{{ txn.description || txn.category_name }}</div>
                <div class="text-xs text-text-muted">{{ txn.account_name }}</div>
              </div>
              <div class="text-sm font-medium text-expense-color flex-shrink-0">-{{ sym }}{{ fmt(txn.amount) }}</div>
            </div>
          </div>
          <div v-else class="text-center text-text-muted py-6">暂无数据</div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      <div class="bg-white rounded-lg p-5 shadow-sm h-64">
        <h3 class="font-semibold mb-4">收支趋势（近12月）</h3>
        <canvas ref="trendCanvas"></canvas>
      </div>
      <div class="bg-white rounded-lg p-5 shadow-sm h-64">
        <h3 class="font-semibold mb-4">每月结余趋势</h3>
        <canvas ref="balanceCanvas"></canvas>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      <div class="bg-white rounded-lg p-5 shadow-sm h-52">
        <h3 class="font-semibold mb-4">净资产趋势</h3>
        <Line v-if="netWorthData.labels.length" :data="netWorthData" :options="lineOptions(netWorthData)" />
        <div v-else class="text-center text-text-muted py-8">暂无数据</div>
      </div>
      <div class="bg-white rounded-lg p-5 shadow-sm h-52">
        <h3 class="font-semibold mb-4">净资产增长率</h3>
        <canvas ref="growthCanvas"></canvas>
      </div>
    </div>

    <div class="bg-white rounded-lg p-5 shadow-sm">
      <h3 class="font-semibold mb-4">最近交易</h3>
      <div v-if="recent.length" class="space-y-2">
        <div v-for="txn in recent" :key="txn.id" class="flex items-center justify-between py-2 border-b border-border-default last:border-0">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
              :class="txn.type === 'income' ? 'bg-income-color' : txn.type === 'expense' ? 'bg-expense-color' : 'bg-transfer-color'">
              {{ txn.type === 'income' ? '收' : txn.type === 'expense' ? '支' : '转' }}
            </div>
            <div class="min-w-0">
              <div class="text-sm font-medium truncate">{{ txn.description || txn.category_name || txn.type }}</div>
              <div class="text-xs text-text-muted">{{ txn.account_name }} · {{ txn.date }}</div>
            </div>
          </div>
          <div class="text-sm font-bold flex-shrink-0" :class="txn.type === 'income' ? 'text-income-color' : txn.type === 'expense' ? 'text-expense-color' : 'text-transfer-color'">
            {{ txn.type === 'income' ? '+' : txn.type === 'expense' ? '-' : '' }}{{ sym }}{{ fmt(txn.amount) }}
          </div>
        </div>
      </div>
      <div v-else class="text-center text-text-muted py-8">暂无交易记录</div>
    </div>

    <router-link to="/bookkeeping" class="fixed bottom-6 right-6 w-14 h-14 bg-accent-primary text-white rounded-full shadow-lg flex items-center justify-center hover:bg-accent-hover transition-colors cursor-pointer">
      <Plus :size="24" />
    </router-link>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { Bar, Doughnut, Line } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement, Filler } from 'chart.js'
import { Plus } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'
import { useTransactionsStore } from '@/stores/transactions'
import type { Overview, NetWorthTrend, NetWorthGrowthTrend } from '@/types'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement, Filler)

const api = useApi()
const settingsStore = useSettingsStore()
const txnStore = useTransactionsStore()
const sym = computed(() => settingsStore.settings.currency_symbol)
const overview = ref<Overview | null>(null)
const trends = ref<{ month: string; income: number; expense: number }[]>([])
const netWorthTrend = ref<NetWorthTrend[]>([])
const netWorthGrowthTrend = ref<NetWorthGrowthTrend[]>([])
const expenseCats = ref<{ category_name: string; category_color: string; total: number }[]>([])
const topExpenses = ref<{ id: string; description: string; account_name: string; amount: number; category_name: string }[]>([])

const now = new Date()
const expStartDate = ref('')
const expEndDate = ref('')
const activeRange = ref('近一月')

const dateRanges = [
  { label: '近一月', months: 1 },
  { label: '近三月', months: 3 },
  { label: '近一年', months: 12 },
]

function setDateRange(range: { label: string; months: number }) {
  activeRange.value = range.label
  const end = new Date()
  const start = new Date()
  start.setMonth(start.getMonth() - range.months)
  expStartDate.value = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`
  expEndDate.value = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, '0')}-${String(end.getDate()).padStart(2, '0')}`
}

function fmt(n: number | undefined, decimals?: number): string {
  if (decimals !== undefined) return (n || 0).toFixed(decimals)
  return (n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function maxWithBuffer(datasets: { data: (number | null)[] }[]): number {
  let maxVal = 0
  for (const ds of datasets) {
    for (const v of ds.data) {
      if (v !== null && v > maxVal) maxVal = v
    }
  }
  return maxVal * 1.15
}

function lineOptions(chartData: { datasets: { data: (number | null)[] }[] }) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' as const, labels: { usePointStyle: true } } },
    scales: { x: { ticks: { font: { size: 10 }, maxRotation: 0 } }, y: { suggestedMax: maxWithBuffer(chartData.datasets) } }
  }
}

function calcMoMPercent(current: number, prev: number): number | null {
  if (!prev || prev === 0) return null
  return ((current - prev) / prev) * 100
}

// Trend chart: uses Chart.js directly (mixed bar+line)
const trendCanvas = ref<HTMLCanvasElement | null>(null)
let trendChartInstance: ChartJS | null = null

// Balance trend chart: uses Chart.js directly (mixed bar+line)
const balanceCanvas = ref<HTMLCanvasElement | null>(null)
let balanceChartInstance: ChartJS | null = null

// Net worth growth chart: uses Chart.js directly (bar+line)
const growthCanvas = ref<HTMLCanvasElement | null>(null)
let growthChartInstance: ChartJS | null = null

function renderTrendChart() {
  if (trendChartInstance) { trendChartInstance.destroy(); trendChartInstance = null }
  const data = trendData.value
  if (!trendCanvas.value || !data.labels.length) return

  trendChartInstance = new ChartJS(trendCanvas.value, {
    type: 'bar',
    data: data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: {
        x: { ticks: { font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
        y: { suggestedMax: maxWithBuffer(data.datasets.filter((d: any) => d.type === 'bar')) },
        y1: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: '环比%' } }
      }
    }
  })
}

function renderBalanceChart() {
  if (balanceChartInstance) { balanceChartInstance.destroy(); balanceChartInstance = null }
  const data = balanceTrendData.value
  if (!balanceCanvas.value || !data.labels.length) return

  balanceChartInstance = new ChartJS(balanceCanvas.value, {
    type: 'bar',
    data: data,
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: {
        x: { ticks: { font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
        y: { title: { display: true, text: '当月结余' } },
        y1: { position: 'right', title: { display: true, text: '累计结余' }, grid: { drawOnChartArea: false } }
      }
    }
  })
}

function renderGrowthChart() {
  if (growthChartInstance) { growthChartInstance.destroy(); growthChartInstance = null }
  const data = netWorthGrowthData.value
  if (!growthCanvas.value || !data.labels.length) return

  growthChartInstance = new ChartJS(growthCanvas.value, {
    type: 'bar',
    data: { labels: data.labels, datasets: [data.datasets[0]] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
      scales: {
        x: { ticks: { font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
        y: { title: { display: true, text: '增长率%' } }
      }
    }
  })
}

const trendData = computed(() => {
  const labels = trends.value.map(t => t.month)
  const incomes = trends.value.map(t => t.income)
  const expenses = trends.value.map(t => t.expense)

  const incomeMoM: (number | null)[] = []
  const expenseMoM: (number | null)[] = []

  for (let i = 0; i < incomes.length; i++) {
    if (i === 0) {
      incomeMoM.push(null)
      expenseMoM.push(null)
    } else {
      incomeMoM.push(calcMoMPercent(incomes[i], incomes[i - 1]))
      expenseMoM.push(calcMoMPercent(expenses[i], expenses[i - 1]))
    }
  }

  return {
    labels,
    datasets: [
      { type: 'bar' as const, label: '收入', data: incomes, backgroundColor: '#F44336' },
      { type: 'bar' as const, label: '支出', data: expenses, backgroundColor: '#4CAF50' },
      { type: 'line' as const, label: '收入环比%', data: incomeMoM, borderColor: '#2196F3', borderDash: [5, 3], tension: 0.3, yAxisID: 'y1', pointStyle: 'line' },
      { type: 'line' as const, label: '支出环比%', data: expenseMoM, borderColor: '#FF9800', borderDash: [5, 3], tension: 0.3, yAxisID: 'y1', pointStyle: 'line' },
    ]
  }
})

const balanceTrendData = computed(() => {
  const data = trends.value.map(t => t.income - t.expense)
  const bgColors = data.map(v => v >= 0 ? '#F44336' : '#4CAF50')
  return {
    labels: trends.value.map(t => t.month),
    datasets: [
      { label: '当月结余', type: 'bar' as const, data, backgroundColor: bgColors, yAxisID: 'y' },
      { label: '累计结余', type: 'line' as const, data: trends.value.map((t, i) => {
        const balances = trends.value.slice(0, i + 1).map(tr => tr.income - tr.expense)
        return balances.reduce((a, b) => a + b, 0)
      }), borderColor: '#FF9800', tension: 0.3, yAxisID: 'y1', pointStyle: 'circle' }
    ]
  }
})

const netWorthData = computed(() => ({
  labels: netWorthTrend.value.map(t => t.month),
  datasets: [
    { label: '净资产', data: netWorthTrend.value.map(t => t.net_worth), borderColor: '#FF9800', backgroundColor: 'rgba(255, 152, 0, 0.1)', tension: 0.3, fill: true, pointStyle: 'circle' }
  ]
}))

const netWorthGrowthData = computed(() => ({
  labels: netWorthGrowthTrend.value.map(t => t.month),
  datasets: [
    { label: '增长率', type: 'bar' as const, data: netWorthGrowthTrend.value.map(t => t.growth_rate), backgroundColor: '#2196F3', yAxisID: 'y' },
    { label: '同比增长率', type: 'line' as const, data: netWorthGrowthTrend.value.map(t => t.yoy_growth_rate), borderColor: '#FF9800', tension: 0.3, yAxisID: 'y1' }
  ]
}))

watch(trendData, () => { nextTick(renderTrendChart) }, { deep: true })
watch(balanceTrendData, () => { nextTick(renderBalanceChart) }, { deep: true })
watch(netWorthGrowthData, () => { nextTick(renderGrowthChart) }, { deep: true })
onBeforeUnmount(() => {
  if (trendChartInstance) { trendChartInstance.destroy(); trendChartInstance = null }
  if (balanceChartInstance) { balanceChartInstance.destroy(); balanceChartInstance = null }
  if (growthChartInstance) { growthChartInstance.destroy(); growthChartInstance = null }
})

const expenseData = computed(() => ({
  labels: expenseCats.value.map(c => c.category_name),
  datasets: [{
    data: expenseCats.value.map(c => c.total),
    backgroundColor: expenseCats.value.map(c => c.category_color),
  }]
}))

const recent = computed(() => txnStore.transactions.slice(0, 10))

async function loadExpenseCats() {
  try {
    const res = await api.get('/statistics/by-category', {
      params: { type_filter: 'expense', start_date: expStartDate.value, end_date: expEndDate.value }
    })
    expenseCats.value = res.data
  } catch (e) { console.error(e) }
}

async function loadTopExpenses() {
  try {
    const res = await api.get('/statistics/top-expenses', {
      params: { limit: 5, start_date: expStartDate.value, end_date: expEndDate.value }
    })
    topExpenses.value = res.data
  } catch (e) { console.error(e) }
}

watch([expStartDate, expEndDate], () => { loadExpenseCats(); loadTopExpenses() })

onMounted(async () => {
  setDateRange({ label: '近一月', months: 1 })
  try {
    const [ov, tr, nw, nwg, tx] = await Promise.all([
      api.get('/statistics/overview'),
      api.get('/statistics/monthly-trend'),
      api.get('/statistics/net-worth-trend'),
      api.get('/statistics/net-worth-growth-trend'),
      api.get('/transactions', { params: { page_size: 10 } }),
    ])
    overview.value = ov.data as Overview
    trends.value = tr.data
    netWorthTrend.value = nw.data
    netWorthGrowthTrend.value = nwg.data
    txnStore.transactions = tx.data
    await loadExpenseCats()
    await loadTopExpenses()
    nextTick(renderTrendChart)
    nextTick(renderBalanceChart)
    nextTick(renderGrowthChart)
  } catch (e) { console.error(e) }
})
</script>
