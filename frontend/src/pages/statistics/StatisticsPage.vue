<template>
  <div class="p-6">
    <h1 class="text-xl font-bold mb-4">统计</h1>
    <div class="flex gap-2 mb-4">
      <button v-for="tab in tabs" :key="tab.key" @click="activeTab = tab.key"
        :class="['px-4 py-2 text-sm rounded-md transition-colors', activeTab === tab.key ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
        {{ tab.label }}
      </button>
    </div>

    <div class="bg-white rounded-lg p-4 shadow-sm mb-4 flex flex-wrap gap-3 items-center">
      <div class="flex gap-2">
        <button @click="setQuickRange('1m')" :class="['px-3 py-1.5 text-sm rounded-md transition-colors', range === '1m' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">近一月</button>
        <button @click="setQuickRange('3m')" :class="['px-3 py-1.5 text-sm rounded-md transition-colors', range === '3m' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">近三月</button>
        <button @click="setQuickRange('1y')" :class="['px-3 py-1.5 text-sm rounded-md transition-colors', range === '1y' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">近一年</button>
      </div>
      <div class="flex items-center gap-2 ml-auto">
        <input v-model="startDate" type="date" class="px-3 py-1.5 border border-border-default rounded-md text-sm" />
        <span class="text-text-secondary">至</span>
        <input v-model="endDate" type="date" class="px-3 py-1.5 border border-border-default rounded-md text-sm" />
        <button @click="loadData" class="px-3 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">查询</button>
      </div>
    </div>

    <!-- Overview Tab -->
    <template v-if="activeTab === 'overview'">
      <!-- Core Data Display Section -->
      <div class="grid grid-cols-2 lg:grid-cols-6 gap-4 mb-6">
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm text-text-secondary">累计收入</div>
          <div class="text-lg font-bold text-income-color">{{ sym }}{{ fmt(coreStats.totalIncome) }}</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm text-text-secondary">累计支出</div>
          <div class="text-lg font-bold text-expense-color">{{ sym }}{{ fmt(coreStats.totalExpense) }}</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm text-text-secondary">累计结余</div>
          <div class="text-lg font-bold" :class="coreStats.totalBalance >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(coreStats.totalBalance) }}</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm text-text-secondary">平均月收入</div>
          <div class="text-lg font-bold text-income-color">{{ sym }}{{ fmt(coreStats.avgMonthlyIncome) }}</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm text-text-secondary">平均月支出</div>
          <div class="text-lg font-bold text-expense-color">{{ sym }}{{ fmt(coreStats.avgMonthlyExpense) }}</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <div class="text-sm text-text-secondary">储蓄率</div>
          <div class="text-lg font-bold" :class="coreStats.savingsRate >= 0 ? 'text-income-color' : 'text-expense-color'">{{ coreStats.savingsRate.toFixed(1) }}%</div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">支出分类</h3>
          <div class="h-48"><Doughnut v-if="expCats.labels.length" :data="expCats" :options="legendRight" /></div>
          <div v-if="!expCats.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">收入分类</h3>
          <div class="h-48"><Doughnut v-if="incCats.labels.length" :data="incCats" :options="legendRight" /></div>
          <div v-if="!incCats.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">每日收支</h3>
          <div class="h-48"><Line v-if="dailyData.labels.length" :data="dailyData" :options="legendTop" /></div>
          <div v-if="!dailyData.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">星期消费模式</h3>
          <div class="h-48"><Bar v-if="weekdayData.labels.length" :data="weekdayData" :options="legendTop" /></div>
          <div v-if="!weekdayData.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm mb-6">
        <h3 class="font-semibold mb-2 text-sm">收支对比（月度）</h3>
        <div class="h-52"><Bar v-if="trend.labels.length" :data="trend" :options="legendTop" /></div>
        <div v-if="!trend.labels.length" class="text-center text-text-muted py-6">暂无数据</div>
      </div>

      <!-- New Overview Charts -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">累计收支结余趋势</h3>
          <div class="h-48"><Line v-if="cumulativeTrendData.labels?.length" :data="cumulativeTrendData" :options="lineChartOptions" /></div>
          <div v-if="!cumulativeTrendData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">储蓄率趋势</h3>
          <div class="h-48"><Line v-if="savingsRateData.labels?.length" :data="savingsRateData" :options="lineChartOptions" /></div>
          <div v-if="!savingsRateData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">必要支出占比趋势</h3>
          <div class="h-48"><Line v-if="necessaryRatioData.labels?.length" :data="necessaryRatioData" :options="lineChartOptions" /></div>
          <div v-if="!necessaryRatioData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">紧急储备覆盖率趋势</h3>
          <div class="h-48"><Line v-if="emergencyReserveData.labels?.length" :data="emergencyReserveData" :options="lineChartOptions" /></div>
          <div v-if="!emergencyReserveData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm mb-6">
        <h3 class="font-semibold mb-2 text-sm">净资产增长率趋势</h3>
        <div class="h-48"><Line v-if="netWorthGrowthData.labels?.length" :data="netWorthGrowthData" :options="lineChartOptions" /></div>
        <div v-if="!netWorthGrowthData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
      </div>
    </template>

    <!-- Income Tab -->
    <template v-if="activeTab === 'income'">
      <div class="bg-white rounded-lg p-4 shadow-sm mb-6">
        <h3 class="font-semibold mb-2 text-sm">收入类别趋势</h3>
        <div class="h-64"><Line v-if="incomeCategoryTrendData.labels?.length" :data="incomeCategoryTrendData" :options="lineChartOptions" /></div>
        <div v-if="!incomeCategoryTrendData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm mb-6">
        <h3 class="font-semibold mb-2 text-sm">收入类别占比趋势</h3>
        <div class="h-64"><Bar v-if="incomeCategoryProportionData.labels?.length" :data="incomeCategoryProportionData" :options="stackedPercentBarOptions" /></div>
        <div v-if="!incomeCategoryProportionData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">收入分类</h3>
          <div class="h-48"><Doughnut v-if="incCats.labels.length" :data="incCats" :options="legendRight" /></div>
          <div v-if="!incCats.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">收入月度趋势</h3>
          <div class="h-48"><Bar v-if="incTrend.labels.length" :data="incTrend" :options="legendTop" /></div>
          <div v-if="!incTrend.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h3 class="font-semibold mb-3 text-sm">收入分类明细</h3>
        <div v-if="incomeCatsRaw.length" class="space-y-2">
          <div v-for="cat in incomeCatsRaw" :key="cat.category_id" class="flex items-center justify-between py-2 border-b border-border-default last:border-0">
            <div class="flex items-center gap-2"><div class="w-3 h-3 rounded" :style="{ backgroundColor: cat.category_color }"></div><span class="text-sm">{{ cat.category_name }}</span></div>
            <div class="text-sm"><span class="font-medium text-income-color">{{ sym }}{{ fmt(cat.total) }}</span> · <span class="text-text-muted">{{ cat.count }}笔</span></div>
          </div>
        </div>
        <div v-else class="text-center text-text-muted py-6">暂无数据</div>
      </div>
    </template>

    <!-- Expense Tab -->
    <template v-if="activeTab === 'expense'">
      <div class="bg-white rounded-lg p-4 shadow-sm mb-6">
        <h3 class="font-semibold mb-2 text-sm">支出类别趋势</h3>
        <div class="h-64"><Line v-if="expenseCategoryTrendData.labels?.length" :data="expenseCategoryTrendData" :options="lineChartOptions" /></div>
        <div v-if="!expenseCategoryTrendData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm mb-6">
        <h3 class="font-semibold mb-2 text-sm">支出类别占比趋势</h3>
        <div class="h-64"><Bar v-if="expenseCategoryProportionData.labels?.length" :data="expenseCategoryProportionData" :options="stackedPercentBarOptions" /></div>
        <div v-if="!expenseCategoryProportionData.labels?.length" class="text-center text-text-muted py-4">暂无数据</div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">支出分类</h3>
          <div class="h-48"><Doughnut v-if="expCats.labels.length" :data="expCats" :options="legendRight" /></div>
          <div v-if="!expCats.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">支出月度趋势</h3>
          <div class="h-48"><Bar v-if="expTrend.labels.length" :data="expTrend" :options="legendTop" /></div>
          <div v-if="!expTrend.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">每日支出</h3>
          <div class="h-48"><Line v-if="dailyData.labels.length" :data="dailyExpenseOnly" :options="legendTop" /></div>
          <div v-if="!dailyData.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
        <div class="bg-white rounded-lg p-4 shadow-sm">
          <h3 class="font-semibold mb-2 text-sm">星期消费模式</h3>
          <div class="h-48"><Bar v-if="weekdayData.labels.length" :data="weekdayData" :options="legendTop" /></div>
          <div v-if="!weekdayData.labels.length" class="text-center text-text-muted py-4">暂无数据</div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h3 class="font-semibold mb-3 text-sm">支出分类明细</h3>
        <div v-if="expenseCatsRaw.length" class="space-y-2">
          <div v-for="cat in expenseCatsRaw" :key="cat.category_id" class="flex items-center justify-between py-2 border-b border-border-default last:border-0">
            <div class="flex items-center gap-2"><div class="w-3 h-3 rounded" :style="{ backgroundColor: cat.category_color }"></div><span class="text-sm">{{ cat.category_name }}</span></div>
            <div class="text-sm"><span class="font-medium text-expense-color">{{ sym }}{{ fmt(cat.total) }}</span> · <span class="text-text-muted">{{ cat.count }}笔</span></div>
          </div>
        </div>
        <div v-else class="text-center text-text-muted py-6">暂无数据</div>
      </div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Bar, Doughnut, Line } from 'vue-chartjs'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement, PointElement, LineElement, Filler)

const legendRight = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' as const, labels: { boxWidth: 12, font: { size: 11 } } } } }
const legendTop = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 11 } } } } }

const api = useApi()
const settingsStore = useSettingsStore()
const sym = computed(() => settingsStore.settings.currency_symbol)
const tabs = [{ key: 'overview', label: '总览' }, { key: 'income', label: '收入统计' }, { key: 'expense', label: '支出统计' }]
const activeTab = ref('overview')
const range = ref('1m')
const startDate = ref('')
const endDate = ref('')
const expenseCatsRaw = ref<{ category_id: string; category_name: string; category_color: string; total: number; count: number }[]>([])
const incomeCatsRaw = ref<{ category_id: string; category_name: string; category_color: string; total: number; count: number }[]>([])
const dailySpending = ref<{ date: string; income: number; expense: number }[]>([])
const weekdayPattern = ref<{ weekday: number; label: string; avg_expense: number; avg_income: number; count: number }[]>([])
const trends = ref<{ month: string; income: number; expense: number }[]>([])

// New data for additional overview charts
const cumulativeTrend = ref<{ month: string; cumulative_income: number; cumulative_expense: number; cumulative_balance: number }[]>([])
const savingsRateTrend = ref<{ month: string; savings_rate: number }[]>([])
const necessaryRatioTrend = ref<{ month: string; necessary_ratio: number }[]>([])
const emergencyReserveTrend = ref<{ month: string; coverage_months: number }[]>([])
const netWorthGrowthTrend = ref<{ month: string; growth_rate: number }[]>([])

// Income and Expense category trends
const incomeCategoryTrend = ref<{ month: string; category_name: string; category_color: string; total: number }[]>([])
const expenseVolatility = ref<{ month: string; total_expense: number; std_dev: number; cv: number }[]>([])
const expenseCategoryTrend = ref<{ month: string; category_name: string; category_color: string; total: number }[]>([])

// Overview totals from backend (authoritative) — used for coreStats to avoid recompute mismatches
const overviewStats = ref({ total_income_month: 0, total_expense_month: 0, net_balance: 0, savings_rate: 0 })

function fmt(n: number): string { return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

const coreStats = computed(() => {
  // Use overview endpoint totals (authoritative) — not sum of by-category rows (misses uncategorized txns)
  const totalIncome = overviewStats.value.total_income_month
  const totalExpense = overviewStats.value.total_expense_month
  const totalBalance = overviewStats.value.net_balance
  const savingsRate = overviewStats.value.savings_rate
  const monthCount = Math.max(trends.value.length, 1)
  const avgMonthlyIncome = totalIncome / monthCount
  const avgMonthlyExpense = totalExpense / monthCount
  return { totalIncome, totalExpense, totalBalance, avgMonthlyIncome, avgMonthlyExpense, savingsRate }
})

const expCats = computed(() => ({ labels: expenseCatsRaw.value.map(c => c.category_name), datasets: [{ data: expenseCatsRaw.value.map(c => c.total), backgroundColor: expenseCatsRaw.value.map(c => c.category_color) }] }))
const incCats = computed(() => ({ labels: incomeCatsRaw.value.map(c => c.category_name), datasets: [{ data: incomeCatsRaw.value.map(c => c.total), backgroundColor: incomeCatsRaw.value.map(c => c.category_color) }] }))
const dailyData = computed(() => ({ labels: dailySpending.value.map(d => d.date.slice(5)), datasets: [{ label: '收入', data: dailySpending.value.map(d => d.income), borderColor: '#4CAF50', tension: 0.3 }, { label: '支出', data: dailySpending.value.map(d => d.expense), borderColor: '#F44336', tension: 0.3 }] }))
const dailyExpenseOnly = computed(() => ({ labels: dailySpending.value.map(d => d.date.slice(5)), datasets: [{ label: '支出', data: dailySpending.value.map(d => d.expense), borderColor: '#F44336', backgroundColor: 'rgba(244,67,54,0.1)', tension: 0.3, fill: true }] }))
const weekdayData = computed(() => ({ labels: weekdayPattern.value.map(w => w.label), datasets: [{ label: '平均支出', data: weekdayPattern.value.map(w => w.avg_expense), backgroundColor: '#F44336' }, { label: '平均收入', data: weekdayPattern.value.map(w => w.avg_income), backgroundColor: '#4CAF50' }] }))
const trend = computed(() => ({ labels: trends.value.map(t => t.month), datasets: [{ label: '收入', data: trends.value.map(t => t.income), backgroundColor: '#4CAF50' }, { label: '支出', data: trends.value.map(t => t.expense), backgroundColor: '#F44336' }] }))
const incTrend = computed(() => ({ labels: trends.value.map(t => t.month), datasets: [{ label: '收入', data: trends.value.map(t => t.income), backgroundColor: '#4CAF50' }] }))
const expTrend = computed(() => ({ labels: trends.value.map(t => t.month), datasets: [{ label: '支出', data: trends.value.map(t => t.expense), backgroundColor: '#F44336' }] }))

// Computed properties for new overview charts
const cumulativeTrendData = computed(() => ({
  labels: cumulativeTrend.value.map(d => d.month),
  datasets: [
    { label: '累计收入', data: cumulativeTrend.value.map(d => d.cumulative_income), borderColor: '#F44336', tension: 0.3 },
    { label: '累计支出', data: cumulativeTrend.value.map(d => d.cumulative_expense), borderColor: '#4CAF50', tension: 0.3 },
    { label: '累计结余', data: cumulativeTrend.value.map(d => d.cumulative_balance), borderColor: '#000000', tension: 0.3 }
  ]
}))

const savingsRateData = computed(() => ({
  labels: savingsRateTrend.value.map(d => d.month),
  datasets: [{
    label: '储蓄率',
    data: savingsRateTrend.value.map(d => d.savings_rate),
    borderColor: '#4CAF50',
    backgroundColor: savingsRateTrend.value.map(d => d.savings_rate >= 0 ? 'rgba(76,175,80,0.2)' : 'rgba(244,67,54,0.2)'),
    fill: true,
    tension: 0.3
  }]
}))

const necessaryRatioData = computed(() => ({
  labels: necessaryRatioTrend.value.map(d => d.month),
  datasets: [{ label: '必要支出占比', data: necessaryRatioTrend.value.map(d => d.necessary_ratio), borderColor: '#2196F3', tension: 0.3, fill: false }]
}))

const emergencyReserveData = computed(() => {
  const slicedData = emergencyReserveTrend.value.slice(3)
  const labels = slicedData.map(d => d.month)
  const data = slicedData.map(d => d.coverage_months)
  return {
    labels,
    datasets: [
      { label: '覆盖月数', data, borderColor: '#2196F3', backgroundColor: 'rgba(33,150,243,0.1)', fill: true, tension: 0.3 }
    ]
  }
})

const netWorthGrowthData = computed(() => ({
  labels: netWorthGrowthTrend.value.map(d => d.month),
  datasets: [{
    label: '净资产增长率',
    data: netWorthGrowthTrend.value.map(d => d.growth_rate),
    borderColor: netWorthGrowthTrend.value.map(d => d.growth_rate >= 0 ? '#4CAF50' : '#F44336'),
    tension: 0.3,
    fill: false
  }]
}))

// Income category trend chart
const incomeCategoryTrendData = computed(() => {
  const months = [...new Set(incomeCategoryTrend.value.map(d => d.month))]
  const categories = [...new Set(incomeCategoryTrend.value.map(d => d.category_name))]
  const colors = [...new Set(incomeCategoryTrend.value.map(d => d.category_color))]
  const datasets = categories.map((cat, idx) => ({
    label: cat,
    data: months.map(m => {
      const item = incomeCategoryTrend.value.find(d => d.month === m && d.category_name === cat)
      return item?.total || 0
    }),
    borderColor: colors[idx % colors.length],
    backgroundColor: colors[idx % colors.length],
    tension: 0.3
  }))
  return { labels: months, datasets }
})

// Income category proportion stacked area chart
const incomeCategoryProportionData = computed(() => {
  const months = [...new Set(incomeCategoryTrend.value.map(d => d.month))]
  const categories = [...new Set(incomeCategoryTrend.value.map(d => d.category_name))]
  const colors = [...new Set(incomeCategoryTrend.value.map(d => d.category_color))]
  const monthTotals: Record<string, number> = {}
  months.forEach(m => {
    monthTotals[m] = incomeCategoryTrend.value.filter(d => d.month === m).reduce((s, d) => s + d.total, 0)
  })
  const datasets = categories.map((cat, idx) => ({
    label: cat,
    data: months.map(m => {
      const item = incomeCategoryTrend.value.find(d => d.month === m && d.category_name === cat)
      const total = monthTotals[m] || 1
      return total > 0 ? ((item?.total || 0) / total) * 100 : 0
    }),
    backgroundColor: colors[idx % colors.length] + 'CC',
  }))
  return { labels: months, datasets }
})

// Expense volatility chart
const expenseVolatilityData = computed(() => ({
  labels: expenseVolatility.value.map(d => d.month),
  datasets: [{
    label: '支出',
    data: expenseVolatility.value.map(d => d.total_expense),
    backgroundColor: '#F44336'
  }]
}))

const expenseVolatilityOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 11 } } } },
  scales: {
    y: { title: { display: true, text: '支出金额' } },
    y1: { position: 'right' as const, title: { display: true, text: '变异系数' }, grid: { drawOnChartArea: false } }
  }
}

// Expense category trend chart
const expenseCategoryTrendData = computed(() => {
  const months = [...new Set(expenseCategoryTrend.value.map(d => d.month))]
  const categories = [...new Set(expenseCategoryTrend.value.map(d => d.category_name))]
  const colors = [...new Set(expenseCategoryTrend.value.map(d => d.category_color))]
  const datasets = categories.map((cat, idx) => ({
    label: cat,
    data: months.map(m => {
      const item = expenseCategoryTrend.value.find(d => d.month === m && d.category_name === cat)
      return item?.total || 0
    }),
    borderColor: colors[idx % colors.length],
    backgroundColor: colors[idx % colors.length],
    tension: 0.3
  }))
  return { labels: months, datasets }
})

// Expense category proportion stacked area chart
const expenseCategoryProportionData = computed(() => {
  const months = [...new Set(expenseCategoryTrend.value.map(d => d.month))]
  const categories = [...new Set(expenseCategoryTrend.value.map(d => d.category_name))]
  const colors = [...new Set(expenseCategoryTrend.value.map(d => d.category_color))]
  const monthTotals: Record<string, number> = {}
  months.forEach(m => {
    monthTotals[m] = expenseCategoryTrend.value.filter(d => d.month === m).reduce((s, d) => s + d.total, 0)
  })
  const datasets = categories.map((cat, idx) => ({
    label: cat,
    data: months.map(m => {
      const item = expenseCategoryTrend.value.find(d => d.month === m && d.category_name === cat)
      const total = monthTotals[m] || 1
      return total > 0 ? ((item?.total || 0) / total) * 100 : 0
    }),
    backgroundColor: colors[idx % colors.length] + 'CC',
  }))
  return { labels: months, datasets }
})

// Chart options for new charts - using explicit formatting
const chartOptionsBase = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 11 } } },
    tooltip: { mode: 'index' as const, intersect: false }
  },
  scales: {
    x: { ticks: { font: { size: 10 }, maxRotation: 0 } },
    y: { ticks: { font: { size: 10 } } }
  }
}

const lineChartOptions = { ...chartOptionsBase }
const barChartOptions = { ...chartOptionsBase }
const stackedPercentBarOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 11 } } },
    tooltip: {
      mode: 'index' as const,
      callbacks: {
        label: (ctx: any) => {
          const val = ctx.parsed?.y ?? ctx.raw
          return `${ctx.dataset.label}: ${typeof val === 'number' ? val.toFixed(1) : val}%`
        }
      }
    }
  },
  scales: {
    x: { stacked: true, ticks: { font: { size: 10 }, maxRotation: 0 } },
    y: { stacked: true, min: 0, max: 100, ticks: { font: { size: 10 } }, title: { display: true, text: '占比 %' } }
  }
}

// Emergency reserve chart with reference zones - using same base
const emergencyReserveOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 11 } } }
  },
  scales: {
    x: { ticks: { font: { size: 10 }, maxRotation: 0 } },
    y: { ticks: { font: { size: 10 }, min: 0 } }
  }
}

function getQuickRangeParams(q: string): { startDate: string; endDate: string } {
  const now = new Date()
  const end = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  const d = new Date()
  if (q === '1m') d.setMonth(d.getMonth() - 1)
  else if (q === '3m') d.setMonth(d.getMonth() - 3)
  else d.setFullYear(d.getFullYear() - 1)
  const start = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { startDate: start, endDate: end }
}

function setQuickRange(q: string) { range.value = q; const params = getQuickRangeParams(q); startDate.value = params.startDate; endDate.value = params.endDate; loadData() }

async function loadData() {
  // Derive year/month from startDate for /statistics/overview (authoritative totals)
  const [y, m] = startDate.value.split('-').map(Number)
  try {
    const [ec, ic, ds, wp, tr, cum, sar, nrr, ert, nwg, ict, ev, ect, ov] = await Promise.all([
      api.get('/statistics/by-category', { params: { type_filter: 'expense', start_date: startDate.value, end_date: endDate.value } }),
      api.get('/statistics/by-category', { params: { type_filter: 'income', start_date: startDate.value, end_date: endDate.value } }),
      api.get('/statistics/daily-spending', { params: { start_date: startDate.value, end_date: endDate.value } }),
      api.get('/statistics/weekday-pattern', { params: { start_date: startDate.value, end_date: endDate.value } }),
      api.get('/statistics/monthly-trend'),
      api.get('/statistics/cumulative-trend', { params: { months: 12 } }),
      api.get('/statistics/savings-rate-trend', { params: { months: 12 } }),
      api.get('/statistics/necessary-ratio-trend', { params: { months: 12 } }),
      api.get('/statistics/emergency-reserve-trend', { params: { months: 12 } }),
      api.get('/statistics/net-worth-growth-trend', { params: { months: 12 } }),
      api.get('/statistics/category-trend', { params: { type_filter: 'income', months: 12 } }),
      api.get('/statistics/expense-volatility', { params: { months: 12 } }),
      api.get('/statistics/category-trend', { params: { type_filter: 'expense', months: 12 } }),
      api.get('/statistics/overview', { params: { year: y, month: m } }),
    ])
    expenseCatsRaw.value = ec.data; incomeCatsRaw.value = ic.data; dailySpending.value = ds.data
    weekdayPattern.value = wp.data; trends.value = tr.data
    cumulativeTrend.value = cum.data
    savingsRateTrend.value = sar.data
    necessaryRatioTrend.value = nrr.data
    emergencyReserveTrend.value = ert.data
    netWorthGrowthTrend.value = nwg.data
    incomeCategoryTrend.value = ict.data
    expenseVolatility.value = ev.data
    expenseCategoryTrend.value = ect.data
    overviewStats.value = { total_income_month: ov.data.total_income_month, total_expense_month: ov.data.total_expense_month, net_balance: ov.data.net_balance, savings_rate: ov.data.savings_rate }
  } catch (e) { console.error(e) }
}

onMounted(() => { setQuickRange('1m') })
</script>
