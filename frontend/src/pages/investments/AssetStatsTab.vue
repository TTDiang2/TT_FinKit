<template>
  <div>
    <!-- Filters -->
    <div class="flex items-center gap-3 mb-4 flex-wrap">
      <div class="text-sm text-text-secondary">分类</div>
      <select v-model="categoryFilter" class="px-3 py-1.5 text-sm border border-border-default rounded-md">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <div class="text-sm text-text-secondary">状态</div>
      <select v-model="statusFilter" class="px-3 py-1.5 text-sm border border-border-default rounded-md">
        <option value="all">全部</option>
        <option value="watchlist">自选</option>
        <option value="pooled">入池</option>
      </select>
      <div class="text-sm text-text-secondary ml-2">周期</div>
      <div class="flex gap-1.5">
        <button v-for="p in PERIODS" :key="p.days" @click="changePeriod(p.days)"
          :class="['px-3 py-1.5 text-xs rounded-md border', periodDays === p.days ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default hover:bg-bg-tertiary']">
          {{ p.label }}
        </button>
      </div>
      <div class="text-xs text-text-muted ml-auto">{{ selectedSymbols.length }} 个标的已选（共 {{ filteredSelector.length }} 可选）</div>
    </div>

    <!-- 标的选择面板：只按组合选（用户拍板 2026-09-02） -->
    <div class="bg-white rounded-lg shadow-sm p-3 mb-4">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-sm font-medium shrink-0">标的组合</span>
        <select v-model="groupPick" @change="applyGroupPick" class="px-3 py-1.5 text-sm border border-border-default rounded-md min-w-56">
          <option value="">请选择组合…</option>
          <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.asset_ids.length }}）</option>
        </select>
        <span class="text-xs text-text-muted">
          已选 {{ selectedSymbols.length }} 只标的（在组合内且有数据）
        </span>
        <span v-if="snapshotPending" class="text-xs text-warning ml-auto">后台统计计算中，自动刷新…</span>
      </div>
    </div>

    <div v-if="loading" class="text-sm text-text-muted py-12 text-center">统计计算中…</div>
    <div v-else-if="!selectedSymbols.length" class="text-sm text-text-muted py-12 text-center">请先在上方选择一个标的组合</div>
    <div v-else-if="!filteredAssets.length" class="text-sm text-text-muted py-12 text-center">
      {{ snapshotPending ? '统计后台计算中（首次约 30-60 秒），自动刷新中…' : '所选范围内没有标的' }}
    </div>
    <template v-else>
      <div class="grid grid-cols-1 gap-6">
        <!-- 1. 归一化净值曲线 -->
        <Card title="归一化净值曲线" :subtitle="`起点 1.0 · 点击图例可单独查看标的`">
          <div style="height: 320px"><Line :data="navCurveData" :options="lineOpts" /></div>
        </Card>

        <!-- 2. 有效前沿 -->
        <Card title="有效前沿（蒙特卡洛 2 万组随机权重）" :subtitle="`历史 ${windowYears} 年日均收益年化 · 橙色线 = 有效前沿（同风险最高收益）`">
          <div v-if="!riskEligibleAssets.length" class="text-sm text-text-muted py-8 text-center">合格标的不足，无法计算有效前沿</div>
          <div v-else style="height: 320px"><Scatter :data="frontierData" :options="scatterOpts" /></div>
        </Card>

        <!-- 3. CAPM -->
        <Card title="CAPM：β vs 年化收益" :subtitle="`β 来自因子暴露（月度回归），低 R² 标灰 · 基准可切换`">
          <div class="flex items-center gap-2 mb-2">
            <span class="text-xs text-text-muted">基准因子</span>
            <select v-model="capmFactor" class="px-2 py-1 text-xs border border-border-default rounded-md">
              <option value="equity">沪深300 (equity)</option>
              <option value="gold">黄金 (gold)</option>
              <option value="bond">债券 (bond)</option>
              <option value="overseas_equity">纳指 (overseas_equity)</option>
            </select>
          </div>
          <div v-if="!capmCount" class="text-sm text-text-muted py-8 text-center">当前基准下没有可用 β 数据（需先计算因子暴露，可在「因子」页重算）</div>
          <div v-else style="height: 300px"><Scatter :data="capmData" :options="scatterOpts" /></div>
        </Card>

        <!-- 4. 相关性热图 -->
        <Card title="相关性矩阵（日收益 Pearson）" :subtitle="`共同交易日对齐 · 排除货币基金/近零波动 · 表头悬停看名称`">
          <div v-if="corrLabels.length < 2" class="text-sm text-text-muted py-8 text-center">合格标的不足 2 个，无法计算相关性</div>
          <div v-else class="overflow-x-auto">
            <table class="text-xs">
              <thead>
                <tr>
                  <th class="p-1.5"></th>
                  <th v-for="l in corrLabels" :key="l" class="p-1.5 font-medium text-text-secondary" :title="symbolNameMap[l] ?? l">{{ l }}<span class="block font-normal text-text-muted">{{ symbolNameMap[l] ?? '' }}</span></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in corrMatrix" :key="i">
                  <td class="p-1.5 font-medium text-text-secondary" :title="symbolNameMap[corrLabels[i]] ?? corrLabels[i]">{{ corrLabels[i] }}<span class="block font-normal text-text-muted">{{ symbolNameMap[corrLabels[i]] ?? '' }}</span></td>
                  <td v-for="(v, j) in row" :key="j" class="p-1.5 text-center font-mono rounded"
                    :style="{ backgroundColor: heatColor(v), color: Math.abs(v) > 0.6 ? '#fff' : '#1a1a1a' }">
                    {{ v.toFixed(2) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        <!-- 5. VaR / CVaR -->
        <Card title="1 日 VaR95 / CVaR95（历史模拟）" :subtitle="`日收益分布第 5 百分位与尾部均值 · 负值越大风险越高`">
          <div v-if="!riskEligibleAssets.length" class="text-sm text-text-muted py-8 text-center">合格标的不足，无法计算 VaR</div>
          <div v-else style="height: 300px"><Bar :data="varData" :options="barOpts" /></div>
        </Card>

        <!-- 6. 水下回撤 -->
        <Card title="水下回撤曲线" :subtitle="`相对历史峰值回撤 % · 0 轴 = 新高`">
          <div v-if="!mddData.datasets.length" class="text-sm text-text-muted py-8 text-center">没有可用的回撤数据</div>
          <div v-else style="height: 300px"><Line :data="mddData" :options="mddLineOpts" /></div>
        </Card>

        <!-- 7. MDD-收益散点 -->
        <Card title="最大回撤 vs 年化收益" :subtitle="`左上 = 高收益低回撤（越往左越好）· 点悬停看标的`">
          <div v-if="!riskEligibleAssets.length" class="text-sm text-text-muted py-8 text-center">合格标的不足，无法计算</div>
          <div v-else style="height: 300px"><Scatter :data="mddScatterData" :options="scatterOpts" /></div>
        </Card>

        <!-- 8. 滚动 30 天收益 -->
        <Card title="滚动 30 天收益" :subtitle="`最近 30 个交易日的累计收益滚动值（数据不足时窗口自动缩短）`">
          <div v-if="!rollingData.datasets.length" class="text-sm text-text-muted py-8 text-center">没有足够的日收益数据（至少需要约 1 个月）</div>
          <div v-else style="height: 300px"><Line :data="rollingData" :options="lineOpts" /></div>
        </Card>

        <!-- 9. 费率对比 -->
        <Card title="费率对比（管理+托管+销售服务费 %/年）" :subtitle="`悬停看申购费与赎回费规则`">
          <div v-if="!feeData.datasets[0]?.data.length" class="text-sm text-text-muted py-8 text-center">没有费率数据</div>
          <div v-else style="height: 280px"><Bar :data="feeData" :options="feeBarOpts" /></div>
        </Card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineComponent, h, watch } from 'vue'
import { Line, Bar, Scatter } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'

ChartJS.register(LineElement, PointElement, BarElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const api = useApi()

const PERIODS = [
  { label: '1月', days: 30 }, { label: '3月', days: 90 }, { label: '6月', days: 180 },
  { label: '1年', days: 365 }, { label: '3年', days: 1095 },
]
const periodDays = ref(365)
const categoryFilter = ref('')
const statusFilter = ref('all')
const capmFactor = ref('equity')

// Card wrapper component (local)
const Card = defineComponent({
  props: { title: String, subtitle: String },
  setup(props, { slots }) {
    return () => h('div', { class: 'bg-white rounded-lg shadow-sm p-4' }, [
      h('div', { class: 'mb-3' }, [
        h('h3', { class: 'font-medium text-sm' }, props.title),
        props.subtitle ? h('div', { class: 'text-xs text-text-muted mt-0.5' }, props.subtitle) : null,
      ]),
      slots.default ? h('div', {}, slots.default()) : null,
    ])
  },
})

interface SnapshotAsset {
  symbol: string; name: string; asset_type: string; category: string; status: string;
  eligible: boolean; excluded_reasons: string[];
  returns: Record<string, number>; nav_normalized: Record<string, number>;
  ann_return: number; ann_volatility: number; sharpe: number | null;
  max_drawdown: number; var95: number; cvar95: number;
  mdd_series: { date: string; drawdown: number }[];
  rolling_30d: { date: string; ret: number | null }[];
  beta: Record<string, number>; beta_r2: Record<string, number>;
  total_annual_cost: number; purchase_fee: number | null; redeem_fee_note: string;
  benchmark: { symbol: string | null; name: string | null };
}
interface Snapshot {
  window: { begin: string; end: string; days: number };
  assets: SnapshotAsset[];
  correlation: { labels: string[]; matrix: number[][] };
  frontier: { assets: { symbol: string; mu: number; sigma: number }[]; samples: { mu: number; sigma: number }[] };
}

const snapshot = ref<Snapshot | null>(null)
const loading = ref(false)

interface SelectorItem {
  id: string; symbol: string; name: string; status: string; category: string;
  fund_kind: string; asset_class: string; region: string; is_money_market: boolean;
  has_data: boolean; sharpe_1y: number | null;
}
const selectorItems = ref<SelectorItem[]>([])
const selectedIds = ref<Set<string>>(new Set())

const categories = computed(() => [...new Set(selectorItems.value.map(a => a.category).filter(Boolean))] as string[])

// 选中标的的 symbol 列表（驱动后端聚合）
const selectedSymbols = computed(() =>
  selectorItems.value.filter(a => selectedIds.value.has(a.id)).map(a => a.symbol))

// 过滤面板用：在 selector 列表内按 category/status 筛选 + 按夏普1Y降序
const filteredSelector = computed(() => {
  const list = selectorItems.value.filter(a =>
    (!categoryFilter.value || a.category === categoryFilter.value) &&
    (statusFilter.value === 'all' || a.status === statusFilter.value))
  return [...list].sort((a, b) => (b.sharpe_1y ?? -99) - (a.sharpe_1y ?? -99))
})

// Assets in snapshot that are also selected (驱动图表)
const filteredAssets = computed(() =>
  (snapshot.value?.assets ?? [])
    .filter(a => selectedSymbols.value.includes(a.symbol))
    .filter(a => Object.keys(a.nav_normalized).length > 0 || Object.keys(a.returns).length > 0))

// Assets eligible for risk charts (has enough data + not money-market/flat)
const riskEligibleAssets = computed(() => filteredAssets.value.filter(a => a.eligible))

const windowYears = computed(() => (periodDays.value / 365).toFixed(1))

async function load() {
  if (!selectedSymbols.value.length) {
    snapshot.value = null
    return
  }
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      days: periodDays.value,
      assets: selectedSymbols.value.join(','),
    }
    const res = await api.get('/research/stats/snapshot', { params })
    if ((res.data as any)?.pending) {
      // 后台重算中（子进程 32s+）：8 秒后自动重试，最多 40 次（~5 分钟）
      pendingTries.value += 1
      if (pendingTries.value <= 40) {
        setTimeout(() => { if (!loading.value) load() }, 8000)
      }
    } else {
      pendingTries.value = 0
    }
    snapshot.value = res.data
  } catch (e) {
    console.warn('stats snapshot failed', e)
    snapshot.value = null
  } finally {
    loading.value = false
  }
}

const pendingTries = ref(0)

function toggleSelect(id: string) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  selectedIds.value = s
}

function selectTop10() {
  const top = filteredSelector.value.filter(a => a.has_data && a.sharpe_1y != null).slice(0, 10)
  selectedIds.value = new Set(top.map(a => a.id))
}

interface GroupItem { id: string; name: string; asset_ids: string[] }
const groups = ref<GroupItem[]>([])
const groupPick = ref('')

function applyGroupPick() {
  const g = groups.value.find(x => x.id === groupPick.value)
  if (!g) return
  const memberSet = new Set(g.asset_ids)
  // 组合成员全部选中（不再依赖 has_data 前置过滤，snapshot 端点会自行剔除无数据标的）
  selectedIds.value = new Set(
    selectorItems.value.filter(a => memberSet.has(a.id)).map(a => a.id))
}

const snapshotPending = computed(() => !!(snapshot.value as any)?.pending)

function selectAllFiltered() {
  selectedIds.value = new Set(filteredSelector.value.map(a => a.id))
}

function clearSelection() {
  selectedIds.value = new Set()
}

async function changePeriod(days: number) {
  if (periodDays.value === days) return
  periodDays.value = days
  await load()
}

// Colors
const PALETTE = ['#6366f1', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#3b82f6']
function colorFor(i: number): string { return PALETTE[i % PALETTE.length] }

// 1. NAV curves
const navCurveData = computed(() => {
  const assets = filteredAssets.value.filter(a => Object.keys(a.nav_normalized).length)
  const labels = assets.length ? [...new Set(assets.flatMap(a => Object.keys(a.nav_normalized)))].sort() : []
  return {
    labels,
    datasets: assets.map((a, i) => ({
      label: `${a.symbol} ${a.name}`,
      data: labels.map(d => a.nav_normalized[d] ?? null),
      borderColor: colorFor(i), backgroundColor: colorFor(i), borderWidth: 1.5,
      tension: 0.25, pointRadius: 0, fill: false, spanGaps: true,
    })),
  }
})

// 2. Efficient frontier — sample cloud + asset points + Pareto frontier line
const frontierData = computed(() => {
  const f = snapshot.value?.frontier
  if (!f) return { datasets: [] }
  const nameMap = Object.fromEntries(filteredAssets.value.map(a => [a.symbol, a.name]))
  const colors = filteredAssets.value.map((a, i) => {
    const idx = f.assets.findIndex(x => x.symbol === a.symbol)
    return { symbol: a.symbol, color: idx >= 0 ? colorFor(i) : '#999' }
  })
  const colorMap = Object.fromEntries(colors.map(c => [c.symbol, c.color]))
  const included = filteredAssets.value.filter(a => f.assets.some(x => x.symbol === a.symbol))
  // Pareto frontier: for each sigma bucket keep the max mu (upper envelope)
  const frontierLine = computeParetoFrontier(f.samples)
  return {
    datasets: [
      {
        label: '随机组合', data: f.samples.map(s => ({ x: s.sigma, y: s.mu })),
        backgroundColor: 'rgba(100,116,139,0.25)', pointRadius: 1.2, pointHoverRadius: 3,
      },
      {
        label: '有效前沿', data: frontierLine,
        borderColor: '#f59e0b', backgroundColor: 'transparent', borderWidth: 2,
        pointRadius: 0, fill: false, tension: 0.2, showLine: true,
      },
      {
        label: '标的', data: included.map(a => {
          const p = f.assets.find(x => x.symbol === a.symbol)!
          return { x: p.sigma, y: p.mu, symbol: a.symbol, name: nameMap[a.symbol] ?? a.symbol }
        }),
        backgroundColor: included.map(a => colorMap[a.symbol] ?? '#333'),
        pointRadius: 6, pointHoverRadius: 8, pointStyle: 'rectRot',
      },
    ],
  }
})

// Upper-envelope of (sigma, mu) samples → the frontier polyline
function computeParetoFrontier(samples: { mu: number; sigma: number }[]): { x: number; y: number }[] {
  if (samples.length < 2) return []
  const sorted = [...samples].sort((a, b) => a.sigma - b.sigma)
  const pts: { x: number; y: number }[] = []
  let maxMu = -Infinity
  for (const s of sorted) {
    if (s.mu > maxMu) {
      maxMu = s.mu
      pts.push({ x: s.sigma, y: s.mu })
    }
  }
  // smooth by merging near-duplicate sigma buckets
  const out: { x: number; y: number }[] = []
  for (const p of pts) {
    if (out.length && Math.abs(out[out.length - 1].x - p.x) < 1e-5 && p.y <= out[out.length - 1].y) continue
    out.push(p)
  }
  return out
}

// 3. CAPM
const capmCount = computed(() => filteredAssets.value.filter(a => a.eligible && a.beta[capmFactor.value] != null).length)
const capmData = computed(() => {
  const nameMap = Object.fromEntries(filteredAssets.value.map(a => [a.symbol, a.name]))
  const assets = filteredAssets.value.filter(a => a.eligible && a.beta[capmFactor.value] != null)
  return {
    datasets: [{
      label: '标的', data: assets.map(a => ({ x: a.beta[capmFactor.value], y: a.ann_return, symbol: a.symbol, name: nameMap[a.symbol] ?? a.symbol })),
      backgroundColor: assets.map(a => {
        const r2 = a.beta_r2[capmFactor.value]
        return r2 != null && r2 < 0.3 ? 'rgba(156,163,175,0.6)' : '#6366f1'
      }),
      pointRadius: 6, pointHoverRadius: 8,
    }],
  }
})

// 4. Correlation
const symbolNameMap = computed(() => Object.fromEntries(filteredAssets.value.map(a => [a.symbol, a.name])))
const corrLabels = computed(() => {
  const included = filteredAssets.value.map(a => a.symbol)
  return (snapshot.value?.correlation.labels ?? []).filter(l => included.includes(l))
})
const corrMatrix = computed(() => {
  const labels = snapshot.value?.correlation.labels ?? []
  const matrix = snapshot.value?.correlation.matrix ?? []
  const idxs = corrLabels.value.map(l => labels.indexOf(l)).filter(i => i >= 0)
  return idxs.map(i => idxs.map(j => matrix[i]?.[j] ?? 0))
})
function heatColor(v: number): string {
  const a = Math.min(Math.abs(v), 1)
  if (v >= 0) return `rgba(16,185,129,${0.08 + a * 0.8})`   // green positive
  return `rgba(239,68,68,${0.08 + a * 0.8})`                 // red negative
}

// 5. VaR/CVaR
const varData = computed(() => {
  const assets = riskEligibleAssets.value
  return {
    labels: assets.map(a => `${a.symbol} ${a.name}`),
    datasets: [
      { label: 'VaR95', data: assets.map(a => a.var95), backgroundColor: 'rgba(239,68,68,0.75)', borderColor: '#dc2626', borderWidth: 1, maxBarThickness: 40 },
      { label: 'CVaR95', data: assets.map(a => a.cvar95), backgroundColor: 'rgba(153,27,27,0.75)', borderColor: '#7f1d1d', borderWidth: 1, maxBarThickness: 40 },
    ],
  }
})

// 6. Underwater drawdown
const mddData = computed(() => {
  const assets = filteredAssets.value.filter(a => a.mdd_series.length)
  const labels = assets.length ? [...new Set(assets.flatMap(a => a.mdd_series.map(m => m.date)))].sort() : []
  return {
    labels,
    datasets: assets.map((a, i) => ({
      label: `${a.symbol} ${a.name}`, data: labels.map(d => a.mdd_series.find(m => m.date === d)?.drawdown ?? null),
      borderColor: colorFor(i), borderWidth: 1.2, pointRadius: 0, fill: false, spanGaps: true, tension: 0.2,
    })),
  }
})

// 7. MDD scatter
const mddScatterData = computed(() => {
  const nameMap = Object.fromEntries(filteredAssets.value.map(a => [a.symbol, a.name]))
  const assets = riskEligibleAssets.value
  return {
    datasets: [{
      label: '标的', data: assets.map(a => ({ x: a.max_drawdown, y: a.ann_return, symbol: a.symbol, name: nameMap[a.symbol] ?? a.symbol })),
      backgroundColor: '#6366f1', pointRadius: 6, pointHoverRadius: 8,
    }],
  }
})

// 8. Rolling 30d
const rollingData = computed(() => {
  const assets = filteredAssets.value.filter(a => a.rolling_30d.length)
  const labels = assets.length ? [...new Set(assets.flatMap(a => a.rolling_30d.map(r => r.date)))].sort() : []
  return {
    labels,
    datasets: assets.map((a, i) => ({
      label: `${a.symbol} ${a.name}`, data: labels.map(d => a.rolling_30d.find(r => r.date === d)?.ret ?? null),
      borderColor: colorFor(i), borderWidth: 1.4, pointRadius: 0, fill: false, spanGaps: true, tension: 0.2,
    })),
  }
})

// 9. Fee comparison
const feeData = computed(() => {
  const assets = filteredAssets.value.filter(a => a.total_annual_cost > 0 || a.purchase_fee != null)
  return {
    labels: assets.map(a => `${a.symbol} ${a.name}`),
    datasets: [{
      label: '年度成本 %', data: assets.map(a => a.total_annual_cost),
      backgroundColor: 'rgba(99,102,241,0.8)', borderColor: '#4338ca', borderWidth: 1, maxBarThickness: 40,
    }],
  }
})

// Chart options
const lineOpts = {
  responsive: true, maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const v = ctx.parsed.y as number
          const label = ctx.dataset.label ?? ''
          return `${label}: ${(v * 100).toFixed(1)}%`
        },
      },
    },
  },
  scales: {
    x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 }, grid: { display: false } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => (v * 100).toFixed(0) + '%' }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

const mddLineOpts = {
  responsive: true, maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: { callbacks: { label: (ctx: any) => `${ctx.dataset.label}: ${((ctx.parsed.y as number) * 100).toFixed(1)}%` } },
  },
  scales: {
    x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => (v * 100).toFixed(0) + '%' }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

const scatterOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const d = ctx.raw
          if (d.symbol) return `${d.name ?? d.symbol} (${d.symbol}): 收益 ${(d.y * 100).toFixed(1)}% · 风险 ${(d.x * 100).toFixed(1)}%`
          return `组合: ${(d.y * 100).toFixed(1)}% / ${(d.x * 100).toFixed(1)}%`
        },
      },
    },
  },
  scales: {
    x: { ticks: { font: { size: 10 }, callback: (v: any) => (v * 100).toFixed(0) + '%' }, grid: { color: 'rgba(0,0,0,0.05)' } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => (v * 100).toFixed(0) + '%' }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

const barOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: { callbacks: { label: (ctx: any) => `${ctx.dataset.label}: ${((ctx.parsed.y as number) * 100).toFixed(2)}%` } },
  },
  scales: {
    x: { ticks: { font: { size: 10 } }, grid: { display: false } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => (v * 100).toFixed(0) + '%' }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

const feeBarOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const a = filteredAssets.value[ctx.dataIndex]
          const base = `年度成本 ${(ctx.parsed.y as number).toFixed(2)}%`
          if (!a) return base
          const parts = [`${a.symbol} ${a.name}`, base]
          if (a.purchase_fee != null) parts.push(`申购费 ${a.purchase_fee}%`)
          if (a.redeem_fee_note) parts.push(`赎回 ${a.redeem_fee_note}`)
          return parts
        },
      },
    },
  },
  scales: {
    x: { ticks: { font: { size: 10 } }, grid: { display: false } },
    y: { ticks: { font: { size: 10 }, callback: (v: any) => v + '%' }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

// 轻量加载标的列表（无价格载荷），默认选 Top10 夏普1Y
async function loadAssets() {
  try {
    const res = await api.get('/research/assets/selector')
    selectorItems.value = (res.data as { items: SelectorItem[] }).items
    selectTop10()
  } catch { selectorItems.value = [] }
  try {
    const g = await api.get('/research/assets/groups')
    groups.value = g.data as GroupItem[]
  } catch { groups.value = [] }
}

// watch filters → reload snapshot
watch([categoryFilter, statusFilter], () => { load() })
// 选择变化 → 重新聚合
watch(selectedIds, () => { load() })

// init
loadAssets().then(load)
</script>
