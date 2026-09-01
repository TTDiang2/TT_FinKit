<template>
  <div v-if="r" class="space-y-4">
    <!-- 风险与分布统计行 -->
    <div class="grid grid-cols-4 gap-4">
      <div class="bg-white rounded-lg shadow-sm p-4">
        <div class="text-xs text-text-muted mb-1">VaR 95%（日）</div>
        <div class="text-xl font-semibold text-expense-color">{{ fmtPct(r.risk_view?.var_95) }}</div>
        <div class="text-xs text-text-muted mt-1">95% 的交易日亏损不超过此值</div>
      </div>
      <div class="bg-white rounded-lg shadow-sm p-4">
        <div class="text-xs text-text-muted mb-1">CVaR 95（日）</div>
        <div class="text-xl font-semibold text-expense-color">{{ fmtPct(r.risk_view?.cvar_95) }}</div>
        <div class="text-xs text-text-muted mt-1">最差 5% 交易日的平均亏损</div>
      </div>
      <div class="bg-white rounded-lg shadow-sm p-4">
        <div class="text-xs text-text-muted mb-1">偏度（日收益）</div>
        <div class="text-xl font-semibold text-text-primary">{{ skew != null ? skew.toFixed(3) : '—' }}</div>
        <div class="text-xs text-text-muted mt-1">{{ skew != null ? (skew < 0 ? '左偏：极端亏损尾部更长' : '右偏：极端收益尾部更长') : '' }}</div>
      </div>
      <div class="bg-white rounded-lg shadow-sm p-4">
        <div class="text-xs text-text-muted mb-1">超额峰度（日收益）</div>
        <div class="text-xl font-semibold text-text-primary">{{ kurt != null ? kurt.toFixed(3) : '—' }}</div>
        <div class="text-xs text-text-muted mt-1">{{ kurt != null ? (kurt > 0 ? '厚尾：极端日比正态更多' : '薄尾') : '' }}</div>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <!-- 月度收益 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">月度收益 <span class="text-xs text-text-muted font-normal">· 红=涨 绿=跌</span></h3>
        <div style="height: 240px"><Bar v-if="monthlyData" :data="monthlyData" :options="barOpts" /></div>
      </div>

      <!-- 回撤曲线 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">回撤曲线 <span class="text-xs text-text-muted font-normal">· 距历史峰值的水下深度</span></h3>
        <div style="height: 240px"><Line v-if="ddData" :data="ddData" :options="ddOpts" /></div>
      </div>

      <!-- 滚动波动率与夏普 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">滚动波动率 / 滚动夏普 <span class="text-xs text-text-muted font-normal">· 63日窗口 年化</span></h3>
        <div style="height: 240px"><Line v-if="rollingData" :data="rollingData" :options="rollOpts" /></div>
      </div>

      <!-- 超额收益 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">超额收益（相对{{ r.benchmark?.name || '基准' }}） <span class="text-xs text-text-muted font-normal">· 相对强弱线 向上=跑赢</span></h3>
        <div style="height: 240px">
          <Line v-if="excessData" :data="excessData" :options="lineOpts" />
          <div v-else class="h-full flex items-center justify-center text-text-muted text-sm">无基准数据</div>
        </div>
      </div>

      <!-- 日收益分布 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">日收益分布 <span class="text-xs text-text-muted font-normal">· 直方图 vs 正态分布</span></h3>
        <div style="height: 240px"><Bar v-if="histData" :data="histData" :options="histOpts" /></div>
      </div>

      <!-- 资金使用率 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">资金使用率 <span class="text-xs text-text-muted font-normal">· 持仓占总资产比例</span></h3>
        <div style="height: 240px"><Line v-if="utilData" :data="utilData" :options="utilOpts" /></div>
      </div>

      <!-- 持仓变化堆叠面积图 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">
          持仓变化
          <span class="text-xs text-text-muted font-normal">
            · 按权重堆叠 · 权重均值 Top10 标的，其余并入「其他」；「现金/未配置」为空仓部分 · 悬停看各期明细
          </span>
        </h3>
        <div style="height: 300px"><Line v-if="weightsAreaData" :data="weightsAreaData" :options="weightsAreaOpts" /></div>
      </div>

      <!-- 归因瀑布图 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">
          收益归因瀑布
          <span class="text-xs text-text-muted font-normal">
            · 各标的累计贡献（每日权重×每日收益近似）·
            <template v-if="waterfallStats">
              净值总收益 {{ fmtPct(waterfallStats.totalRet) }} / 归因合计 {{ fmtPct(waterfallStats.attrSum) }}
              （差额为费用与换仓残差）
            </template>
          </span>
        </h3>
        <div style="height: 240px"><Bar v-if="waterfallData" :data="waterfallData" :options="wfOpts" /></div>
      </div>

      <!-- 滚动 Alpha/Beta -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">滚动 Alpha / Beta <span class="text-xs text-text-muted font-normal">· 63日 vs {{ r.benchmark?.name || '基准' }}</span></h3>
        <div style="height: 240px">
          <Line v-if="abData" :data="abData" :options="abOpts" />
          <div v-else class="h-full flex items-center justify-center text-text-muted text-sm">无基准数据</div>
        </div>
      </div>

      <!-- 组合因子暴露 -->
      <div class="bg-white rounded-lg shadow-sm p-4">
        <h3 class="text-sm font-medium mb-3">
          组合因子暴露
          <span class="text-xs text-text-muted font-normal">
            · β=组合权重对各因子的敏感度 ·
            <template v-if="expoSeriesData">每日时序（前 4 大因子，图例为因子均值）</template>
            <template v-else>全程平均加权 β（时间均值）</template>
            · 暴露高说明该因子是组合波动的主要来源
          </span>
        </h3>
        <div style="height: 260px">
          <Line v-if="expoSeriesData" :data="expoSeriesData" :options="expoSeriesOpts" />
          <Bar v-else-if="expoData" :data="expoData" :options="expoOpts" />
          <div v-else class="h-full flex items-center justify-center text-text-muted text-sm">无因子暴露数据（旧回测重新运行后自动生成）</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Line, Bar } from 'vue-chartjs'
import {
  Chart as ChartJS, LineElement, BarElement, PointElement, CategoryScale,
  LinearScale, Tooltip, Legend, Filler,
} from 'chart.js'
import type { BacktestResponse } from '@/types'

ChartJS.register(LineElement, BarElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const props = defineProps<{ backtest: BacktestResponse | null; factorNames?: Record<string, string> }>()
const r = computed(() => props.backtest?.results)
const RED = '#F44336'
const GREEN = '#4CAF50'
const BLUE = '#3b82f6'

function fmtPct(v?: number | null) { return v != null ? `${(v * 100).toFixed(2)}%` : '—' }

const navs = computed(() => r.value?.nav_series || [])
const rets = computed(() => {
  const a = navs.value.map(p => p.nav)
  const out: number[] = []
  for (let i = 1; i < a.length; i++) if (a[i - 1] > 0) out.push(a[i] / a[i - 1] - 1)
  return out
})

// ---- 基本统计 ----
const skew = computed(() => {
  const xs = rets.value
  if (xs.length < 20) return null
  const m = xs.reduce((a, b) => a + b, 0) / xs.length
  const s2 = xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length
  const s3 = xs.reduce((a, b) => a + (b - m) ** 3, 0) / xs.length
  return s2 > 0 ? s3 / s2 ** 1.5 : null
})
const kurt = computed(() => {
  const xs = rets.value
  if (xs.length < 20) return null
  const m = xs.reduce((a, b) => a + b, 0) / xs.length
  const s2 = xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length
  const s4 = xs.reduce((a, b) => a + (b - m) ** 4, 0) / xs.length
  return s2 > 0 ? s4 / s2 ** 2 - 3 : null
})

// ---- 月度收益 ----
const monthlyData = computed(() => {
  const ns = navs.value
  if (ns.length < 25) return null
  const byMonth = new Map<string, { first: number; last: number; prevClose?: number }>()
  for (const p of ns) {
    const mk = p.date.slice(0, 7)
    const cur = byMonth.get(mk)
    if (!cur) byMonth.set(mk, { first: p.nav, last: p.nav })
    else cur.last = p.nav
  }
  const keys = [...byMonth.keys()].sort()
  let prev = byMonth.get(keys[0])!.first
  const labels: string[] = []
  const vals: number[] = []
  for (const k of keys) {
    const m = byMonth.get(k)!
    const base = m.first !== undefined && prev ? prev : m.first
    labels.push(k)
    vals.push(m.last / base - 1)
    prev = m.last
  }
  return {
    labels,
    datasets: [{
      data: vals.map(v => +(v * 100).toFixed(2)),
      backgroundColor: vals.map(v => (v >= 0 ? RED : GREEN)),
      borderWidth: 0,
    }],
  }
})

// ---- 回撤曲线 ----
const ddData = computed(() => {
  const ns = navs.value
  if (ns.length < 2) return null
  let peak = ns[0].nav
  const labels: string[] = []
  const vals: number[] = []
  for (const p of ns) {
    if (p.nav > peak) peak = p.nav
    labels.push(p.date)
    vals.push(+(((p.nav / peak) - 1) * 100).toFixed(2))
  }
  return {
    labels,
    datasets: [{
      label: '回撤 %', data: vals, borderColor: GREEN, backgroundColor: 'rgba(76,175,80,0.18)',
      borderWidth: 1, pointRadius: 0, fill: true, tension: 0.2,
    }],
  }
})

// ---- 滚动指标 ----
function rollingStats(window: number) {
  const ns = navs.value
  const out: { date: string; vol: number; sharpe: number }[] = []
  const rfDaily = 0.02 / 252
  for (let i = window; i < ns.length; i++) {
    const seg: number[] = []
    for (let j = i - window + 1; j <= i; j++) {
      if (ns[j - 1].nav > 0) seg.push(ns[j].nav / ns[j - 1].nav - 1)
    }
    if (seg.length < window - 2) continue
    const m = seg.reduce((a, b) => a + b, 0) / seg.length
    const varr = seg.reduce((a, b) => a + (b - m) ** 2, 0) / (seg.length - 1)
    const sd = Math.sqrt(varr)
    out.push({
      date: ns[i].date,
      vol: sd * Math.sqrt(252),
      sharpe: sd > 0 ? (m - rfDaily) / sd * Math.sqrt(252) : 0,
    })
  }
  return out
}
const rollingData = computed(() => {
  const rs = rollingStats(63)
  if (!rs.length) return null
  return {
    labels: rs.map(p => p.date),
    datasets: [
      { label: '滚动波动率%', data: rs.map(p => +(p.vol * 100).toFixed(2)), borderColor: GREEN, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
      { label: '滚动夏普', data: rs.map(p => +p.sharpe.toFixed(2)), borderColor: BLUE, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y1' },
    ],
  }
})

// ---- 超额收益 ----
const excessData = computed(() => {
  const bench = r.value?.benchmark
  const ns = navs.value
  if (!bench?.series?.length || ns.length < 2) return null
  const bmap = new Map(bench.series.map(p => [p.date, p.nav]))
  const labels: string[] = []
  const vals: number[] = []
  let rel = 1
  let prevP: number | null = null
  let prevB: number | null = null
  for (const p of ns) {
    const b = bmap.get(p.date)
    if (b == null) continue
    if (prevP != null && prevB != null && prevP > 0 && prevB > 0) {
      rel *= (p.nav / prevP) / (b / prevB)
    }
    labels.push(p.date)
    vals.push(+rel.toFixed(4))
    prevP = p.nav
    prevB = b
  }
  return {
    labels,
    datasets: [{ label: '相对强弱', data: vals, borderColor: BLUE, backgroundColor: 'rgba(59,130,246,0.08)', borderWidth: 1.5, pointRadius: 0, fill: true }],
  }
})

// ---- 滚动 Alpha/Beta ----
const abData = computed(() => {
  const bench = r.value?.benchmark
  const ns = navs.value
  if (!bench?.series?.length) return null
  const bmap = new Map(bench.series.map(p => [p.date, p.nav]))
  type Row = { date: string; p: number; b: number }
  const rows: Row[] = []
  for (let i = 1; i < ns.length; i++) {
    const b1 = bmap.get(ns[i].date)
    const b0 = bmap.get(ns[i - 1].date)
    if (b1 == null || b0 == null || b0 <= 0 || ns[i - 1].nav <= 0) continue
    rows.push({ date: ns[i].date, p: ns[i].nav / ns[i - 1].nav - 1, b: b1 / b0 - 1 })
  }
  const W = 63
  if (rows.length < W + 5) return null
  const labels: string[] = []
  const betas: number[] = []
  const alphas: number[] = []
  const rfD = 0.02 / 252
  for (let i = W; i < rows.length; i++) {
    const seg = rows.slice(i - W + 1, i + 1)
    const mp = seg.reduce((a, x) => a + x.p, 0) / seg.length
    const mb = seg.reduce((a, x) => a + x.b, 0) / seg.length
    const vp = seg.reduce((a, x) => a + (x.p - mp) ** 2, 0) / seg.length
    const vb = seg.reduce((a, x) => a + (x.b - mb) ** 2, 0) / seg.length
    const cov = seg.reduce((a, x) => a + (x.p - mp) * (x.b - mb), 0) / seg.length
    if (vb <= 0) continue
    const beta = cov / vb
    const alpha = (mp - rfD) - beta * (mb - rfD)
    labels.push(rows[i].date)
    betas.push(+beta.toFixed(3))
    alphas.push(+(alpha * 252 * 100).toFixed(2))
  }
  return {
    labels,
    datasets: [
      { label: 'Beta', data: betas, borderColor: GREEN, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
      { label: '年化Alpha%', data: alphas, borderColor: RED, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y1' },
    ],
  }
})

// ---- 日收益分布 ----
const histData = computed(() => {
  const xs = rets.value
  if (xs.length < 30) return null
  const bins = 27
  const lo = Math.min(...xs), hi = Math.max(...xs)
  const w = (hi - lo) / bins || 1e-9
  const counts = new Array(bins).fill(0)
  for (const x of xs) counts[Math.min(bins - 1, Math.floor((x - lo) / w))]++
  const centers = counts.map((_, i) => lo + w * (i + 0.5))
  const m = xs.reduce((a, b) => a + b, 0) / xs.length
  const sd = Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length) || 1e-9
  const normal = centers.map(c => {
    const pdf = Math.exp(-((c - m) ** 2) / (2 * sd * sd)) / (sd * Math.sqrt(2 * Math.PI))
    return +(pdf * w * xs.length).toFixed(2)
  })
  const label = centers.map(c => (c * 100).toFixed(1) + '%')
  return {
    labels: label,
    datasets: [
      { label: '实际频数', data: counts, backgroundColor: 'rgba(59,130,246,0.55)', borderWidth: 0, order: 2 },
      { type: 'line' as const, label: '正态分布', data: normal, borderColor: RED, borderWidth: 2, pointRadius: 0, fill: false, order: 1 },
    ] as any,
  }
})

// ---- 持仓变化堆叠面积图 ----
const AREA_COLORS = ["#6366f1","#ef4444","#10b981","#f59e0b","#8b5cf6","#06b6d4","#ec4899","#84cc16","#f97316","#3b82f6"]
const weightsAreaData = computed(() => {
  const wh = r.value?.weight_history || []
  if (wh.length < 2) return null
  // 标的按全期平均权重排序取 Top10，其余合并为「其他」
  const sums: Record<string, number> = {}
  for (const p of wh) for (const [sym, w] of Object.entries(p.weights || {})) sums[sym] = (sums[sym] || 0) + (w as number)
  const top = Object.entries(sums).sort((a, b) => b[1] - a[1]).slice(0, 10).map(e => e[0])
  const topSet = new Set(top)
  const labels = wh.map(p => p.date)
  const ds = top.map((sym, i) => ({
    label: dispName(sym),
    data: wh.map(p => +(((p.weights || {})[sym] || 0) * 100).toFixed(2)),
    backgroundColor: AREA_COLORS[i % AREA_COLORS.length],
    borderColor: AREA_COLORS[i % AREA_COLORS.length],
    borderWidth: 0.5, pointRadius: 0, fill: true, tension: 0.15,
  }))
  // 现金/未配置 = 100% - 各标的权重和（可能为负=杠杆，夹 0）
  // Top10 之外的标的权重层——曾漏画此层导致图上仓位虚低 ~30%（2026-09-01）
  ds.push({
    label: "其他标的",
    data: wh.map(p => {
      const all = Object.values(p.weights || {}).reduce((a: number, b) => a + (b as number), 0)
      const topSum = top.reduce((a: number, s2: string) => a + (((p.weights || {})[s2] || 0) as number), 0)
      return +((all - topSum) * 100).toFixed(2)
    }),
    backgroundColor: "rgba(148,163,184,0.45)", borderColor: "#94a3b8", borderWidth: 0.5, pointRadius: 0, fill: true, tension: 0.15,
  })
  ds.push({
    label: "现金/未配置",
    data: wh.map(p => {
      const s2 = Object.values(p.weights || {}).reduce((a: number, b) => a + (b as number), 0)
      return +(Math.max(0, 1 - s2) * 100).toFixed(2)
    }),
    backgroundColor: "rgba(203,213,225,0.4)", borderColor: "#cbd5e1", borderWidth: 0.5, pointRadius: 0, fill: true, tension: 0.15,
  })
  return { labels, datasets: ds }
})

const weightsAreaOpts = {
  responsive: true, maintainAspectRatio: false,
  interaction: { mode: "index" as const, intersect: false },
  plugins: { legend: { position: "bottom" as const, labels: { boxWidth: 10, font: { size: 10 } } } },
  scales: {
    x: { ticks: { maxTicksLimit: 10, font: { size: 10 } } },
    y: { stacked: true, max: 100, ticks: { callback: (v: any) => v + "%" } },
  },
}

// ---- 资金使用率 ----
const utilData = computed(() => {
  const wh = r.value?.weight_history || []
  if (wh.length < 2) return null
  return {
    labels: wh.map(p => p.date),
    datasets: [{
      label: '仓位%', data: wh.map(p => +(Object.values(p.weights || {}).reduce((a: number, b) => a + (b as number), 0) * 100).toFixed(1)),
      borderColor: BLUE, backgroundColor: 'rgba(59,130,246,0.12)', borderWidth: 1.2, pointRadius: 0, fill: true,
    }],
  }
})

// ---- 归因瀑布 ----
const nameBySymbol = computed(() => {
  const map: Record<string, string> = {}
  for (const rec of r.value?.rebalance_records || []) {
    for (const a of rec.period_stats?.attribution || []) {
      if (a.symbol && a.name) map[a.symbol] = a.name
    }
  }
  return map
})
function dispName(sym: string): string {
  const n = nameBySymbol.value[sym] || props.factorNames?.[sym] || sym
  return n.length > 9 ? n.slice(0, 9) + '…' : n
}
const waterfallStats = computed(() => {
  const ns = navs.value
  if (ns.length < 2) return null
  const totalRet = ns[ns.length - 1].nav / ns[0].nav - 1
  const recs = r.value?.rebalance_records || []
  let attrSum = 0
  for (const rec of recs) for (const a of rec.period_stats?.attribution || []) attrSum += a.contribution
  return { totalRet, attrSum }
})
const waterfallData = computed(() => {
  const recs = r.value?.rebalance_records || []
  const agg = new Map<string, number>()
  for (const rec of recs) {
    for (const a of rec.period_stats?.attribution || []) {
      agg.set(a.symbol, (agg.get(a.symbol) || 0) + a.contribution)
    }
  }
  if (!agg.size) return null
  const entries = [...agg.entries()].sort((a, b) => b[1] - a[1])
  const top = entries.slice(0, 5)
  const bottom = entries.slice(-3).filter(e => e[1] < 0 && !top.includes(e))
  const mid = entries.filter(e => !top.includes(e) && !bottom.includes(e))
  const rows = top.map(e => ({ label: dispName(e[0]), v: e[1] }))
  if (mid.length) rows.push({ label: '其他', v: mid.reduce((a, e) => a + e[1], 0) })
  rows.push(...bottom.reverse().map(e => ({ label: dispName(e[0]), v: e[1] })))
  const total = entries.reduce((a, e) => a + e[1], 0)
  rows.push({ label: '归因合计', v: total })
  let cum = 0
  const data: { y: number[]; label: string }[] = []
  const colors: string[] = []
  const labels: string[] = []
  for (const row of rows) {
    labels.push(row.label)
    if (row.label === '合计') {
      data.push({ y: [0, total], label: row.label })
      colors.push('#9333ea')
    } else {
      const from = Math.min(cum, cum + row.v)
      const to = Math.max(cum, cum + row.v)
      data.push({ y: [+(from * 100).toFixed(2), +(to * 100).toFixed(2)], label: row.label })
      colors.push(row.v >= 0 ? RED : GREEN)
      cum += row.v
    }
  }
  return {
    labels,
    datasets: [{ data: data.map(d => d.y) as any, backgroundColor: colors, borderWidth: 0, barPercentage: 0.7 }],
  }
})

// ---- 组合因子暴露 ----
const expoData = computed(() => {
  const pfe = r.value?.portfolio_factor_exposures || []
  if (!pfe.length) return null
  return {
    labels: pfe.map(e => e.factor),
    datasets: [{
      data: pfe.map(e => e.exposure),
      backgroundColor: pfe.map(e => (e.exposure >= 0 ? RED : GREEN)),
      borderWidth: 0,
    }],
  }
})

// ---- chart options ----
const baseScales = {
  x: { ticks: { maxTicksLimit: 10, font: { size: 9 }, maxRotation: 0, autoSkipPadding: 15 }, grid: { display: false } },
  y: { ticks: { font: { size: 9 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
}
const barOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: baseScales }
const ddOpts = { ...barOpts, scales: { ...baseScales, y: { ...baseScales.y, suggestedMin: undefined } } }
const lineOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: baseScales }
const histOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { boxWidth: 12, font: { size: 10 } } } }, scales: baseScales }
const utilOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { ...baseScales, y: { ...baseScales.y, min: 0, max: 100 } } }
const rollOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { labels: { boxWidth: 12, font: { size: 10 } } } },
  scales: {
    ...baseScales,
    y1: { position: 'right' as const, ticks: { font: { size: 9 } }, grid: { display: false } },
  },
}
const abOpts = rollOpts
const wfOpts = {
  responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
  scales: { x: baseScales.x, y: { ticks: { font: { size: 9 }, callback: (v: any) => `${Number(v).toFixed(0)}%` }, grid: { color: 'rgba(0,0,0,0.05)' } } },
}
const expoOpts = {
  responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
  scales: { ...baseScales, x: { ...baseScales.x, indexAxis: undefined } },
  indexAxis: 'y' as const,
}

// 因子暴露时序：取 |均值| 最大的前 4 个因子画每日 β 曲线
const expoSeriesData = computed(() => {
  const series = r.value?.factor_exposure_series || []
  if (series.length < 10) return null
  const sums: Record<string, number> = {}
  for (const pt of series) {
    for (const [k, v] of Object.entries(pt.exposures || {})) {
      sums[k] = (sums[k] || 0) + (v || 0)
    }
  }
  const topKeys = Object.entries(sums)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 4)
    .map(e => e[0])
  if (!topKeys.length) return null
  const palette = ['#f59e0b', '#3b82f6', '#10b981', '#a855f7']
  return {
    labels: series.map(pt => pt.date),
    datasets: topKeys.map((k, i) => ({
      label: `${props.factorNames?.[k] || k}（均值 ${(sums[k] / series.length).toFixed(2)}）`,
      data: series.map(pt => pt.exposures?.[k] ?? null),
      borderColor: palette[i % palette.length],
      backgroundColor: 'transparent',
      borderWidth: 1.2, pointRadius: 0, tension: 0.2,
    })),
  }
})
const expoSeriesOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { labels: { boxWidth: 12, font: { size: 10 } } } },
  scales: {
    x: { ticks: { maxTicksLimit: 10, font: { size: 9 }, maxRotation: 0, autoSkipPadding: 15 }, grid: { display: false } },
    y: { ticks: { font: { size: 9 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}
</script>