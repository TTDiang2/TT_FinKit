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

      <!-- 净值曲线 (chart.js) + 买卖点标注 + 失效区间遮罩 -->
      <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-sm font-medium">
            净值曲线
            <span class="text-xs text-text-muted font-normal">· 红↑=买入 绿↓=卖出 · 红色阴影=策略失效区间(窗口年化&lt;{{ (stagnantMinAnn * 100).toFixed(1) }}%)</span>
          </h3>
          <div class="flex items-center gap-2">
            <span class="text-xs text-text-muted">失效阈值</span>
            <input type="range" min="0" max="20" step="0.5" :value="stagnantMinAnnPct" @input="stagnantMinAnnPct = parseFloat(($event.target as HTMLInputElement).value)" class="w-32" />
            <span class="text-xs text-text-primary w-10">{{ stagnantMinAnnPct.toFixed(1) }}%</span>
          </div>
        </div>
        <div style="height: 340px">
          <Line v-if="navChartData" :data="navChartData" :options="navChartOpts" :plugins="[stagnantPlugin]" />
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

      <!-- 自建因子效果（策略 custom_factors 输出） -->
      <div v-if="customFactorEntries.length" class="bg-white rounded-lg shadow-sm p-4 mb-4">
        <h3 class="text-sm font-medium mb-1">自建因子效果</h3>
        <p class="text-xs text-text-muted mb-3">因子值与组合未来 {{ customFactorEntries[0][1]?.horizon_days ?? 21 }} 交易日收益的时序相关性 · 胜率=方向判断正确比例</p>
        <div class="grid grid-cols-4 gap-3">
          <div v-for="[name, stat] in customFactorEntries" :key="name" class="border border-border-default rounded-lg p-3">
            <div class="text-xs text-text-muted mb-1">{{ name }}</div>
            <div class="space-y-0.5">
              <div class="flex justify-between text-xs"><span class="text-text-muted">IC</span><span :class="Math.abs(stat.ic_mean) > 0.1 ? 'text-income-color' : 'text-text-muted'">{{ stat.ic_mean.toFixed(4) }}</span></div>
              <div class="flex justify-between text-xs"><span class="text-text-muted">Rank IC</span><span>{{ stat.rank_ic.toFixed(4) }}</span></div>
              <div class="flex justify-between text-xs"><span class="text-text-muted">胜率</span><span :class="stat.win_rate >= 0.55 ? 'text-income-color' : 'text-text-primary'">{{ (stat.win_rate * 100).toFixed(0) }}%</span></div>
              <div class="flex justify-between text-xs"><span class="text-text-muted">样本</span><span>{{ stat.n_periods }} 期</span></div>
            </div>
          </div>
        </div>
      </div>

      <!-- 调仓记录 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">调仓记录 <span class="text-xs text-text-muted font-normal">· 阶段=上次调仓至本次 · 累计=回测开始至本次 · settle=赎回款到账自动补买</span></h3>
        <table class="w-full text-xs">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-2 py-1.5 font-medium">日期</th>
              <th class="px-2 py-1.5 font-medium">交易</th>
              <th class="px-2 py-1.5 font-medium" colspan="5" style="border-left: 1px solid rgba(0,0,0,0.08)">阶段（上次调仓至今）</th>
              <th class="px-2 py-1.5 font-medium" colspan="4" style="border-left: 1px solid rgba(0,0,0,0.08)">累计（开测至今）</th>
            </tr>
            <tr class="bg-bg-tertiary/60">
              <th></th><th></th>
              <th class="px-2 py-1 font-medium" style="border-left: 1px solid rgba(0,0,0,0.08)">盈亏</th>
              <th class="px-2 py-1 font-medium">年化</th>
              <th class="px-2 py-1 font-medium">波动</th>
              <th class="px-2 py-1 font-medium">夏普</th>
              <th class="px-2 py-1 font-medium">收益归因</th>
              <th class="px-2 py-1 font-medium" style="border-left: 1px solid rgba(0,0,0,0.08)">盈亏</th>
              <th class="px-2 py-1 font-medium">年化</th>
              <th class="px-2 py-1 font-medium">波动</th>
              <th class="px-2 py-1 font-medium">夏普</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="rec in backtest.results.rebalance_records" :key="rec.date + rec.kind" class="border-t border-border-default align-top">
              <td class="px-2 py-1.5 whitespace-nowrap">
                {{ rec.date }}
                <span v-if="rec.kind === 'settle'" class="ml-1 px-1 py-0.5 rounded bg-blue-50 text-blue-600" style="font-size:10px">settle</span>
              </td>
              <td class="px-2 py-1.5">
                <div v-for="t in rec.trades" :key="t.symbol + t.side" class="mb-0.5">
                  <span :class="t.side === 'buy' ? 'text-income-color' : 'text-expense-color'" class="font-medium">{{ t.side === 'buy' ? '买' : '卖' }}</span>
                  {{ t.name || t.symbol }}<span class="text-text-muted">({{ t.symbol }})</span>
                  ¥{{ t.amount.toFixed(0) }}
                </div>
              </td>
              <template v-if="rec.period_stats">
                <td class="px-2 py-1.5 whitespace-nowrap" :class="rec.period_stats.pnl >= 0 ? 'text-income-color' : 'text-expense-color'" style="border-left: 1px solid rgba(0,0,0,0.06)">¥{{ rec.period_stats.pnl.toFixed(0) }}</td>
                <td class="px-2 py-1.5 whitespace-nowrap" :class="rec.period_stats.ann_return >= 0 ? 'text-income-color' : 'text-expense-color'">{{ fmtPct(rec.period_stats.ann_return) }}</td>
                <td class="px-2 py-1.5 whitespace-nowrap">{{ fmtPct(rec.period_stats.ann_volatility) }}</td>
                <td class="px-2 py-1.5 whitespace-nowrap">{{ rec.period_stats.sharpe != null ? rec.period_stats.sharpe.toFixed(2) : '—' }}</td>
                <td class="px-2 py-1.5">
                  <div v-for="a in (rec.period_stats.attribution || [])" :key="a.symbol" class="mb-0.5 whitespace-nowrap">
                    <span :class="a.contribution >= 0 ? 'text-income-color' : 'text-expense-color'">{{ a.contribution >= 0 ? '+' : '' }}{{ (a.contribution * 100).toFixed(1) }}%</span>
                    {{ a.name || a.symbol }}
                  </div>
                  <div v-for="fa in (rec.period_stats.factor_attribution || [])" :key="'f' + fa.factor" class="mb-0.5 whitespace-nowrap text-text-secondary">
                    <span :class="fa.contribution >= 0 ? 'text-income-color' : 'text-expense-color'">{{ fa.contribution >= 0 ? '+' : '' }}{{ (fa.contribution * 100).toFixed(2) }}%</span>
                    <span class="text-text-muted">β·</span>{{ fa.factor }}
                  </div>
                </td>
              </template>
              <template v-else><td colspan="5" style="border-left: 1px solid rgba(0,0,0,0.06)">—</td></template>
              <template v-if="rec.cumulative_stats">
                <td class="px-2 py-1.5 whitespace-nowrap" :class="rec.cumulative_stats.pnl >= 0 ? 'text-income-color' : 'text-expense-color'" style="border-left: 1px solid rgba(0,0,0,0.06)">¥{{ rec.cumulative_stats.pnl.toFixed(0) }}</td>
                <td class="px-2 py-1.5 whitespace-nowrap" :class="rec.cumulative_stats.ann_return >= 0 ? 'text-income-color' : 'text-expense-color'">{{ fmtPct(rec.cumulative_stats.ann_return) }}</td>
                <td class="px-2 py-1.5 whitespace-nowrap">{{ fmtPct(rec.cumulative_stats.ann_volatility) }}</td>
                <td class="px-2 py-1.5 whitespace-nowrap">{{ rec.cumulative_stats.sharpe != null ? rec.cumulative_stats.sharpe.toFixed(2) : '—' }}</td>
              </template>
              <template v-else><td colspan="4" style="border-left: 1px solid rgba(0,0,0,0.06)">—</td></template>
            </tr>
            <tr v-if="!backtest.results.rebalance_records.length">
              <td colspan="12" class="px-2 py-2 text-center text-text-muted">无调仓记录</td>
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
import type { BacktestResponse, CustomFactorStat } from '@/types'

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
    if (buys.length) { buyData[idx] = nav; buyMeta[idx] = buys.map(t => `${t.name || t.symbol} ¥${t.amount.toFixed(0)}`).join(', ') }
    if (sells.length) { sellData[idx] = nav; sellMeta[idx] = sells.map(t => `${t.name || t.symbol} ¥${t.amount.toFixed(0)}`).join(', ') }
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
        borderColor: 'transparent', backgroundColor: '#ef4444',
        pointStyle: 'triangle', pointRadius: 5, pointHoverRadius: 8,
        showLine: false,
        _meta: buyMeta,
      },
      {
        label: '卖出',
        data: sellData,
        borderColor: 'transparent', backgroundColor: '#10b981',
        pointStyle: 'triangle', pointRotation: 180, pointRadius: 5, pointHoverRadius: 8,
        showLine: false,
        _meta: sellMeta,
      },
    ],
  }
})

// 失效阈值滑动杆（前端实时扫描，无需重新回测）
const stagnantMinAnnPct = ref(5.0)
const stagnantMinAnn = computed(() => stagnantMinAnnPct.value / 100)

function detectStagnantLocal(
  navSeries: { date: string; nav: number }[],
  overallAnn: number,
  windows: number[] = [126, 252],
): { start: string; end: string }[] {
  const n = navSeries.length
  const thr = Math.max(stagnantMinAnn.value, 0.01)
  const mask = new Array(n).fill(false)
  for (const w of windows) {
    const step = Math.max(1, Math.floor(w / 6))
    for (let i = w; i < n; i += step) {
      const base = navSeries[i - w].nav
      if (base <= 0) continue
      const r = navSeries[i].nav / base - 1
      const ann = r > -1 ? Math.pow(1 + r, 252 / w) - 1 : -1
      if (ann < thr) {
        for (let j = Math.max(0, i - w); j <= Math.min(n - 1, i); j++) mask[j] = true
      }
    }
  }
  const periods: { start: string; end: string }[] = []
  let s: number | null = null
  for (let j = 0; j < n; j++) {
    if (mask[j] && s === null) s = j
    else if (!mask[j] && s !== null) { periods.push({ start: navSeries[s].date, end: navSeries[j - 1].date }); s = null }
  }
  if (s !== null) periods.push({ start: navSeries[s].date, end: navSeries[n - 1].date })
  return periods
}

const localStagnantPeriods = computed(() => {
  const r = backtest.value?.results
  if (!r?.nav_series?.length) return []
  return detectStagnantLocal(r.nav_series, r.metrics.ann_return)
})

// 失效区间红色遮罩：merged_periods (date range) → x 轴像素矩形
const stagnantPlugin = {
  id: 'stagnantBands',
  afterDatasetsDraw(chart: any) {
    const bands = chart.options.plugins.stagnantBands?.bands as { startIdx: number; endIdx: number }[] | undefined
    if (!bands?.length) return
    const { ctx, chartArea, scales } = chart
    const xs = scales.x
    ctx.save()
    ctx.fillStyle = 'rgba(239,68,68,0.10)'
    for (const b of bands) {
      const x0 = xs.getPixelForValue(b.startIdx)
      const x1 = xs.getPixelForValue(b.endIdx)
      ctx.fillRect(Math.min(x0, x1), chartArea.top, Math.abs(x1 - x0), chartArea.bottom - chartArea.top)
    }
    ctx.restore()
  },
}



const navChartOpts = computed(() => {
  const r = backtest.value?.results
  const dateIdx: Record<string, number> = {}
  r?.nav_series?.forEach((p, i) => { dateIdx[p.date] = i })
  const bands = localStagnantPeriods.value
    .map((p) => ({ startIdx: dateIdx[p.start], endIdx: dateIdx[p.end] }))
    .filter((b) => b.startIdx != null && b.endIdx != null)
  return {
  responsive: true, maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { labels: { boxWidth: 12, font: { size: 10 } } },
    stagnantBands: { bands },
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
})

// Factor evaluation lookup
const factorEvalMap = computed(() => {
  const map: Record<string, any> = {}
  if (!evalData.value?.evaluations) return map
  for (const e of evalData.value.evaluations) {
    map[e.factor_key] = e
  }
  return map
})

const customFactorEntries = computed(() => {
  const cfa = backtest.value?.results?.custom_factor_analysis
  if (!cfa) return [] as [string, CustomFactorStat][]
  return Object.entries(cfa) as [string, CustomFactorStat][]
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
