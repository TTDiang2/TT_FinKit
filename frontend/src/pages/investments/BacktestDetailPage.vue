<template>
  <div v-if="backtest">
    <div class="flex items-center gap-3 mb-4">
      <button @click="goBack" class="text-text-secondary hover:text-text-primary">← 返回</button>
      <h2 class="text-lg font-semibold">回测详情</h2>
      <span :class="statusClass(backtest.status)" class="px-1.5 py-0.5 text-xs rounded">{{ statusLabel(backtest.status) }}</span>
      <span v-if="backtest.strategy_name" class="text-sm text-text-muted">· {{ backtest.strategy_name }}</span>
    </div>

    <!-- 标的池快照：每次回测创建时冻结的标的来源（用于复现） -->
    <div v-if="backtest.group_names?.length || backtest.universe_count" class="bg-bg-tertiary/40 rounded-lg px-4 py-3 mb-4 text-xs">
      <div class="flex items-center gap-2 flex-wrap text-text-secondary">
        <span class="font-medium text-text-primary">标的池快照：</span>
        <span>{{ backtest.universe_count }} 只标的</span>
        <span v-if="backtest.group_names?.length" class="text-text-muted">·</span>
        <span v-for="g in backtest.group_names" :key="g.id"
          class="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700">
          {{ g.name }}（{{ g.member_count }}）
        </span>
        <button v-if="backtest.universe.length"
          @click="showPool = !showPool" class="ml-auto text-accent-primary hover:underline">
          {{ showPool ? '收起' : `查看 ${backtest.universe.length} 个代码` }}
        </button>
      </div>
      <div v-if="showPool" class="mt-2 max-h-32 overflow-y-auto text-text-muted font-mono text-xs leading-5">
        {{ backtest.universe.join('、') }}
      </div>
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

      <!-- 交易统计与基准对比 -->
      <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">胜率（日）</div>
          <div class="text-xl font-semibold text-text-primary">{{ backtest.results.metrics.win_rate != null ? (backtest.results.metrics.win_rate * 100).toFixed(1) + '%' : '—' }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">盈亏比</div>
          <div class="text-xl font-semibold text-text-primary">{{ backtest.results.metrics.profit_loss_ratio ?? '—' }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">最长水下期</div>
          <div class="text-xl font-semibold text-text-primary">{{ backtest.results.metrics.mdd_duration_days != null ? backtest.results.metrics.mdd_duration_days + ' 交易日' : '—' }}</div>
        </div>
        <div class="bg-white rounded-lg shadow-sm p-4">
          <div class="text-xs text-text-muted mb-1">Beta / 年化Alpha</div>
          <div class="text-xl font-semibold text-text-primary">
            {{ backtest.results.metrics.beta ?? '—' }} / {{ backtest.results.metrics.alpha_ann != null ? (backtest.results.metrics.alpha_ann * 100).toFixed(1) + '%' : '—' }}
          </div>
          <div class="text-xs text-text-muted mt-1">vs {{ backtest.results.benchmark?.name || '沪深300' }}（基准年化 {{ backtest.results.metrics.benchmark_ann_return != null ? (backtest.results.metrics.benchmark_ann_return * 100).toFixed(1) + '%' : '—' }}）</div>
        </div>
      </div>
      <div v-if="backtest.results.metrics.info_ratio != null" class="mb-6 -mt-2 text-xs text-text-muted text-right">信息比率（vs 基准）：{{ backtest.results.metrics.info_ratio }}</div>

      <!-- 净值曲线 (chart.js) + 买卖点标注 + 失效/回撤遮罩 + 基准 -->
      <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
        <div class="flex items-center justify-between mb-3 flex-wrap gap-2">
          <h3 class="text-sm font-medium">
            净值曲线
            <span class="text-xs text-text-muted font-normal">· 红↑=买入 绿↓=卖出 · 红阴影=失效区(&lt;{{ (stagnantMinAnn * 100).toFixed(1) }}%年化) · 橙阴影=深回撤(&gt;{{ (ddThresholdPct).toFixed(0) }}%) · 蓝线={{ backtest.results.benchmark?.name || '基准' }}</span>
          </h3>
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-2">
              <span class="text-xs text-text-muted">失效阈值</span>
              <input type="range" min="0" max="20" step="0.5" :value="stagnantMinAnnPct" @input="stagnantMinAnnPct = parseFloat(($event.target as HTMLInputElement).value)" class="w-28" />
              <span class="text-xs text-text-primary w-10">{{ stagnantMinAnnPct.toFixed(1) }}%</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-text-muted">回撤阈值</span>
              <input type="range" min="1" max="30" step="1" :value="ddThresholdPct" @input="ddThresholdPct = parseFloat(($event.target as HTMLInputElement).value)" class="w-24" />
              <span class="text-xs text-text-primary w-8">{{ ddThresholdPct.toFixed(0) }}%</span>
            </div>
            <div class="flex items-center gap-2 ml-2 border-l border-border-default pl-4">
              <span class="text-xs text-text-muted">预测</span>
              <select v-model="mcHorizon" @change="mcForecast && runMonteCarlo()" class="text-xs border border-border-default rounded px-1 py-0.5">
                <option :value="30">30日</option>
                <option :value="60">60日</option>
                <option :value="120">120日</option>
              </select>
              <button v-if="!mcForecast" @click="mcOn = true; runMonteCarlo()" class="btn-secondary text-xs">模拟未来</button>
              <button v-else @click="runMonteCarlo()" class="btn-secondary text-xs">重跑</button>
              <button v-if="mcForecast" @click="clearMonteCarlo()" class="text-xs text-text-muted hover:text-text-primary">清除</button>
            </div>
          </div>
        </div>
        <div style="height: 340px">
          <Line v-if="navChartData" :data="navChartData" :options="navChartOpts" :plugins="[stagnantPlugin, drawdownPlugin]" />
        </div>
        <div v-if="mcForecast" class="grid grid-cols-4 gap-3 mt-3 text-xs">
          <div class="flex items-center justify-between border border-border-default rounded-lg px-3 py-1.5">
            <span class="text-text-muted">预测 P5（悲观）</span>
            <span class="font-medium text-expense-color">{{ mcForecast.p5f.toFixed(3) }}</span>
          </div>
          <div class="flex items-center justify-between border border-border-default rounded-lg px-3 py-1.5">
            <span class="text-text-muted">预测中位数</span>
            <span class="font-medium text-text-primary">{{ mcForecast.p50f.toFixed(3) }}</span>
          </div>
          <div class="flex items-center justify-between border border-border-default rounded-lg px-3 py-1.5">
            <span class="text-text-muted">预测 P95（乐观）</span>
            <span class="font-medium text-income-color">{{ mcForecast.p95f.toFixed(3) }}</span>
          </div>
          <div class="flex items-center justify-between border border-border-default rounded-lg px-3 py-1.5">
            <span class="text-text-muted">{{ mcHorizon }} 日后亏损概率</span>
            <span class="font-medium">{{ (mcForecast.lossProb * 100).toFixed(1) }}%</span>
          </div>
          <div class="col-span-4 text-xs text-text-muted">
            紫色扇形 = FHS 模拟（EWMA 波动率滤波 + 区块自举，800 路径）· 仅统计展示，非投资建议
          </div>
        </div>
      </div>

      <!-- 分析图表区 -->
      <BacktestCharts :backtest="backtest" :factor-names="factorNameMap" />

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
      <div class="flex items-center justify-between mb-2">
        <span class="text-blue-700 font-medium">回测进行中…</span>
        <span class="text-xs text-blue-600">心跳 {{ heartbeatAgo }}s 前</span>
      </div>
      <div class="w-full bg-blue-100 rounded-full h-2.5 mb-2 overflow-hidden">
        <div class="bg-accent-primary h-2.5 transition-all" :style="{width: (backtest.progress || 0) + '%'}"></div>
      </div>
      <div class="text-xs text-text-secondary">
        进度 {{ backtest.progress || 0 }}% · {{ backtest.universe_count || backtest.universe.length }} 只标的
      </div>
    </div>
  </div>
  <div v-else class="text-center py-8 text-text-muted">加载中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'
import BacktestCharts from './BacktestCharts.vue'
import type { BacktestResponse, CustomFactorStat, BenchmarkSeries } from '@/types'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const router = useRouter()
const route = useRoute()
const api = useApi()
const backtest = ref<BacktestResponse | null>(null)
const evalData = ref<{ thresholds: Record<string, number>; evaluations: any[] } | null>(null)
const showPool = ref(false)
const heartbeatAgo = ref(-1)
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!backtest.value) return
    if (backtest.value.status === 'done' || backtest.value.status === 'failed') {
      stopPolling()
      return
    }
    try {
      const { data } = await api.get<BacktestResponse>(`/backtests/${backtest.value.id}?parts=core`)
      backtest.value = data
      heartbeatAgo.value = 0
    } catch { /* ignore */ }
  }, 3000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

setInterval(() => { heartbeatAgo.value++ }, 1000)

function goBack() {
  router.push('/investments/strategies?sub=backtest')
}

// NAV chart data: line + benchmark + buy/sell scatter overlay + MC forecast fan
const navChartData = computed(() => {
  const r = backtest.value?.results
  if (!r?.nav_series?.length) return null
  const histLabels = r.nav_series.map(p => p.date)
  const histLen = histLabels.length
  const mc = mcForecast.value
  const labels = mc ? [...histLabels, ...mc.labels] : histLabels
  const pad = mc ? new Array(histLen).fill(null) : []
  const navData = r.nav_series.map(p => p.nav)

  // benchmark aligned by date (null where missing)
  const benchData: (number | null)[] = labels.map(() => null)
  if (r.benchmark?.series?.length) {
    const bmap = new Map(r.benchmark.series.map(p => [p.date, p.nav]))
    // renormalize benchmark to portfolio's first nav for visual comparability
    const firstB = r.benchmark.series[0].nav || 1
    const scale = navData[0] / firstB
    histLabels.forEach((d, i) => {
      const b = bmap.get(d)
      if (b != null) benchData[i] = b * scale
    })
  }

  // Build buy/sell marker arrays aligned to nav_series labels (null = no trade that day)
  const dateIdx: Record<string, number> = {}
  r.nav_series.forEach((p, i) => { dateIdx[p.date] = i })
  const buyData: (number | null)[] = new Array(labels.length).fill(null)
  const sellData: (number | null)[] = new Array(labels.length).fill(null)
  const buyMeta: any[] = new Array(histLen).fill(null)
  const sellMeta: any[] = new Array(histLen).fill(null)
  for (const rec of r.rebalance_records) {
    const idx = dateIdx[rec.date]
    if (idx == null) continue
    const nav = r.nav_series[idx].nav
    const buys = rec.trades.filter(t => t.side === 'buy')
    const sells = rec.trades.filter(t => t.side === 'sell')
    if (buys.length) { buyData[idx] = nav; buyMeta[idx] = buys.map(t => `${t.name || t.symbol} ¥${t.amount.toFixed(0)}`).join(', ') }
    if (sells.length) { sellData[idx] = nav; sellMeta[idx] = sells.map(t => `${t.name || t.symbol} ¥${t.amount.toFixed(0)}`).join(', ') }
  }
  const datasets: any[] = [
    {
      label: '净值',
      data: navData,
      borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)',
      borderWidth: 1.5, tension: 0.25, pointRadius: 0, fill: true,
    },
  ]
  if (benchData.some(v => v != null)) {
    datasets.push({
      label: r.benchmark?.name || '基准',
      data: benchData,
      borderColor: '#94a3b8', borderWidth: 1, borderDash: [5, 3],
      pointRadius: 0, fill: false, tension: 0.25,
    })
  }
  datasets.push(
    {
      label: '买入',
      data: buyData,
      borderColor: 'transparent', backgroundColor: '#F44336',
      pointStyle: 'triangle', pointRadius: 5, pointHoverRadius: 8,
      showLine: false,
      _meta: buyMeta,
    },
    {
      label: '卖出',
      data: sellData,
      borderColor: 'transparent', backgroundColor: '#4CAF50',
      pointStyle: 'triangle', pointRotation: 180, pointRadius: 5, pointHoverRadius: 8,
      showLine: false,
      _meta: sellMeta,
    },
  )
  if (mc) {
    const f = (arr: number[]) => [...pad, ...arr]
    datasets.push(
      {
        label: `预测P95`, data: f(mc.p95),
        borderColor: 'rgba(139,92,246,0.4)', backgroundColor: 'rgba(139,92,246,0.08)',
        borderWidth: 1, pointRadius: 0, fill: '+1', tension: 0.25,
      },
      {
        label: `预测P75`, data: f(mc.p75),
        borderColor: 'transparent', backgroundColor: 'rgba(139,92,246,0.13)',
        borderWidth: 0, pointRadius: 0, fill: '+1', tension: 0.25,
      },
      {
        label: `预测P25`, data: f(mc.p25),
        borderColor: 'transparent', backgroundColor: 'transparent',
        borderWidth: 0, pointRadius: 0, fill: false, tension: 0.25,
      },
      {
        label: '预测中位数', data: f(mc.p50),
        borderColor: '#8b5cf6', borderWidth: 2, borderDash: [6, 3],
        pointRadius: 0, fill: false, tension: 0.25,
      },
      {
        label: `预测P5`, data: f(mc.p5),
        borderColor: 'rgba(139,92,246,0.4)', borderWidth: 1,
        pointRadius: 0, fill: false, tension: 0.25,
      },
    )
  }
  return { labels, datasets }
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

// ---- 回撤遮罩：从峰值回撤超过阈值的"水下期"（经典 underwater 可视化）----
const ddThresholdPct = ref(10)
const drawdownBands = computed(() => {
  const r = backtest.value?.results
  const ns = r?.nav_series
  if (!ns?.length) return []
  const thr = ddThresholdPct.value / 100
  const flags = ns.map(() => false)
  let peak = ns[0].nav
  for (let i = 0; i < ns.length; i++) {
    if (ns[i].nav > peak) peak = ns[i].nav
    if (peak > 0 && ns[i].nav / peak - 1 < -thr) flags[i] = true
  }
  const bands: { startIdx: number; endIdx: number }[] = []
  let s: number | null = null
  for (let j = 0; j < flags.length; j++) {
    if (flags[j] && s === null) s = j
    else if (!flags[j] && s !== null) { bands.push({ startIdx: s, endIdx: j - 1 }); s = null }
  }
  if (s !== null) bands.push({ startIdx: s, endIdx: flags.length - 1 })
  return bands
})

const drawdownPlugin = {
  id: 'drawdownBands',
  afterDatasetsDraw(chart: any) {
    const bands = chart.options.plugins.drawdownBands?.bands
    if (!bands?.length) return
    const { ctx, chartArea, scales } = chart
    const xs = scales.x
    ctx.save()
    ctx.fillStyle = 'rgba(245,158,11,0.15)'
    for (const b of bands) {
      const x0 = xs.getPixelForValue(b.startIdx)
      const x1 = xs.getPixelForValue(b.endIdx)
      ctx.fillRect(Math.min(x0, x1), chartArea.top, Math.abs(x1 - x0), chartArea.bottom - chartArea.top)
    }
    ctx.restore()
  },
}

// ---- 蒙特卡洛 v2：FHS（EWMA 波动率滤波 + 区块自举）叠加在净值曲线未来段 ----
const navRets = computed(() => {
  const ns = backtest.value?.results?.nav_series || []
  const out: number[] = []
  for (let i = 1; i < ns.length; i++) if (ns[i - 1].nav > 0) out.push(ns[i].nav / ns[i - 1].nav - 1)
  return out
})

interface McForecast {
  labels: string[]           // 未来交易日（不含历史）
  p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[]
  lossProb: number
  p5f: number; p50f: number; p95f: number
}
const mcOn = ref(false)
const mcHorizon = ref(60)
const mcForecast = ref<McForecast | null>(null)

function runMonteCarlo() {
  const rs = navRets.value
  const navs = backtest.value?.results?.nav_series || []
  const last = navs[navs.length - 1]
  if (rs.length < 126 || !last) return
  const mu = rs.reduce((a, b) => a + b, 0) / rs.length
  // EWMA 波动率滤波 → 标准化创新 z（保留厚尾，去掉波动率聚集）
  const LAM = 0.94
  const z: number[] = []
  let sig2 = rs.slice(0, 30).reduce((a, r) => a + (r - mu) ** 2, 0) / 30
  let sigT = Math.sqrt(sig2)
  for (const r of rs) {
    sig2 = LAM * sig2 + (1 - LAM) * (r - mu) ** 2
    sigT = Math.sqrt(sig2)
    z.push((r - mu) / (sigT || 1e-9))
  }
  const H = mcHorizon.value, P = 800, BL = 5
  const finals: number[] = []
  const paths: number[][] = []
  for (let p = 0; p < P; p++) {
    // 区块自举（块长 5，保留序列相关性）
    const zs: number[] = []
    while (zs.length < H) {
      const s = Math.floor(Math.random() * Math.max(1, z.length - BL))
      for (let k = 0; k < BL && zs.length < H; k++) zs.push(z[s + k])
    }
    // 前向递推：波动率按 EWMA 动态演化，重放当前波动率状态
    let s2 = sigT ** 2
    let v = last.nav
    const path: number[] = [v]
    for (let d = 0; d < H; d++) {
      const rstar = mu + zs[d] * Math.sqrt(s2)
      v *= (1 + rstar)
      path.push(v)
      s2 = LAM * s2 + (1 - LAM) * (rstar - mu) ** 2
    }
    paths.push(path)
    finals.push(v)
  }
  const q = (arr: number[], pct: number) => {
    const s = [...arr].sort((a, b) => a - b)
    return s[Math.min(s.length - 1, Math.floor(pct * s.length))]
  }
  const lines = [5, 25, 50, 75, 95].map(pct => {
    const line: number[] = []
    for (let d = 0; d <= H; d++) line.push(q(paths.map(pt => pt[d]), pct / 100))
    return line
  })
  // 未来标签：跳过周末的交易日
  const labels: string[] = []
  {
    const dt = new Date(last.date)
    for (let d = 0; d < H; d++) {
      do { dt.setDate(dt.getDate() + 1) } while (dt.getDay() === 0 || dt.getDay() === 6)
      labels.push(dt.toISOString().slice(0, 10))
    }
  }
  mcForecast.value = {
    labels,
    p5: lines[0], p25: lines[1], p50: lines[2], p75: lines[3], p95: lines[4],
    lossProb: finals.filter(v => v < last.nav).length / finals.length,
    p5f: q(finals, 0.05), p50f: q(finals, 0.5), p95f: q(finals, 0.95),
  }
}

function clearMonteCarlo() {
  mcForecast.value = null
  mcOn.value = false
}

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
    drawdownBands: { bands: drawdownBands.value },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const ds = ctx.dataset
          const v = ctx.parsed.y
          if (ds.label === '净值') return `净值: ${v.toFixed(4)}`
          if (v == null) return ''
          const meta = ds._meta?.[ctx.dataIndex]
          if (meta) return `${ds.label}: ${meta}`
          return `${ds.label}: ${v.toFixed(4)}`
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
const factorNameMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const [k, e] of Object.entries(factorEvalMap.value)) map[k] = e.factor_name || k
  return map
})

function icColor(v: number) { return Math.abs(v) > 0.05 ? 'text-income-color' : 'text-text-muted' }
function icirColor(v: number) { return v > 0.5 ? 'text-income-color' : v > 0.3 ? 'text-warning' : 'text-text-muted' }

async function load() {
  const id = route.params.id as string
  // 分段加载：先拉 core（指标+摘要，毫秒级），重载荷并行补齐
  const { data } = await api.get<BacktestResponse>(`/backtests/${id}?parts=core`)
  backtest.value = data
  const partsToLoad = ['nav_series', 'weight_history', 'rebalance_records', 'factor_exposure_series']
  if ((data.results?.available_parts || []).length) {
    try {
      const loaded = await Promise.all(partsToLoad.map(name =>
        api.get(`/backtests/${id}/part/${name}`).then(r => [name, r.data[name]])))
      const patch: Record<string, unknown> = {}
      for (const [name, value] of loaded) patch[name] = value
      if (backtest.value?.results) backtest.value.results = { ...backtest.value.results, ...patch }
    } catch { /* 分段失败时保留 core 渲染 */ }
  }
  // 旧回测（benchmark 字段上线前创建）懒加载基准，让超额收益/滚动Alpha-Beta图可用
  if (data.results && !data.results.benchmark && data.start_date && data.end_date) {
    try {
      const { data: bench } = await api.get<BenchmarkSeries>('/backtests/benchmark', {
        params: { start: data.start_date, end: data.end_date },
      })
      if (bench?.series?.length && backtest.value?.results) {
        backtest.value.results.benchmark = bench
      }
    } catch { /* 基准不可用时不阻断 */ }
  }
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

onMounted(() => { load(); startPolling() })
onUnmounted(stopPolling)
</script>
