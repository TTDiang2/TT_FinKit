<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold">信号</h2>
        <p class="text-xs text-text-muted mt-0.5">
          每月末按信号调仓；临时需要紧急调仓时，直接点「运行策略生成信号」即按最新数据重算
        </p>
      </div>
      <button @click="runSignal" :disabled="running" class="btn-primary disabled:opacity-50">
        <Zap :size="14" /> {{ running ? '生成中...' : '运行策略生成信号' }}
      </button>
    </div>

    <!-- 调仓冷却横幅 -->
    <div v-if="health?.rebalance?.in_cooldown"
      class="flex items-center gap-2 px-4 py-2 mb-4 bg-income-bg border border-income-color/30 rounded text-sm">
      <span>✓</span>
      <span>最近一次调仓：<b>{{ health.rebalance.last_date }}</b>（{{ health.rebalance.source }}），冷却期至
        <b>{{ health.rebalance.cooldown_until }}</b>。除非紧急情况，冷却期内信号变动无需立即执行。</span>
    </div>
    <div v-if="health?.data_freshness?.remind_full_update"
      class="flex items-center gap-2 px-4 py-2 mb-4 bg-yellow-50 border border-yellow-200 rounded text-sm">
      <span>⚠</span>
      <span>入池标的价格已有 <b>{{ health.data_freshness.lag_days }}</b> 天未更新——给信号前建议先去标的页做一次全量数据更新，否则信号基于陈旧净值。</span>
    </div>

    <!-- 当前信号 -->
    <div v-if="currentSignal" class="bg-white rounded-lg shadow-sm p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h3 class="font-medium">
            当前信号
            <span v-if="currentSignal.strategy_name" class="ml-2 text-xs px-2 py-0.5 rounded bg-bg-tertiary text-text-secondary align-middle">
              {{ currentSignal.strategy_name }} · v{{ currentSignal.strategy_version }}
            </span>
          </h3>
        </div>
        <div class="text-xs text-text-muted">
          生成于 {{ currentSignal.run_date }} | 数据截止 {{ currentSignal.as_of_date }}
        </div>
      </div>

      <!-- 风险告警 -->
      <div v-if="currentSignal.risk_status?.warnings?.length" class="mb-4">
        <div v-for="w in currentSignal.risk_status.warnings" :key="w"
          class="flex items-center gap-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700 mb-1">
          <span>⚠</span> {{ w }}
        </div>
      </div>

      <!-- 目标权重（含名称） -->
      <div class="mb-5">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-medium">目标权重（共 {{ weightRows.length }} 只）</h4>
          <span class="text-xs text-text-muted">合计 {{ totalWeightPct }}%</span>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-1.5 font-medium">标的</th>
              <th class="px-3 py-1.5 font-medium text-right">目标权重</th>
              <th class="px-3 py-1.5 font-medium">目标金额（不含加仓）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in weightRows" :key="row.symbol" class="border-t border-border-default">
              <td class="px-3 py-1.5">
                <div class="font-medium">{{ row.name }}</div>
                <div class="text-xs text-text-muted">{{ row.symbol }}</div>
              </td>
              <td class="px-3 py-1.5 text-right font-medium">{{ (row.weight * 100).toFixed(1) }}%</td>
              <td class="px-3 py-1.5 text-xs text-text-secondary">
                {{ tradePlan && totalValue > 0 ? fmtMoney(row.weight * totalValue) : '—' }}
              </td>
            </tr>
            <tr v-if="!weightRows.length">
              <td colspan="3" class="px-3 py-4 text-center text-text-muted">信号目标为空（策略可能判定为空仓/维持现状）</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 月度加仓计算器 + 调仓清单 -->
      <div class="mb-4">
        <div class="flex items-center justify-between mb-2 gap-3 flex-wrap">
          <h4 class="text-sm font-medium">调仓清单（{{ tradePlan?.run_date || '—' }} 信号 vs 当前持仓）</h4>
          <div class="flex items-center gap-2 text-xs">
            <label for="add-cash" class="text-text-secondary whitespace-nowrap">本次新投入</label>
            <input id="add-cash" v-model.number="additionalCash" type="number" min="0" step="100"
              placeholder="如 5000"
              class="w-28 px-2 py-1 border border-border-default rounded text-right font-mono" />
            <span class="text-text-muted">元</span>
            <button @click="loadTradePlan" :disabled="planLoading"
              class="text-xs px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary disabled:opacity-50">
              {{ planLoading ? '计算中…' : (tradePlan ? '刷新清单' : '生成调仓清单') }}
            </button>
          </div>
        </div>

        <!-- 加载失败提示（不再静默吞错） -->
        <div v-if="planError" class="mb-2 px-3 py-2 bg-expense-bg border border-expense-color rounded text-xs text-expense-color">
          调仓清单生成失败：{{ planError }}
        </div>

        <div v-if="tradePlan" class="mb-1 text-xs text-text-muted">
          持仓总市值 {{ fmtMoney(tradePlan.invested_value) }}
          <template v-if="tradePlan.additional_cash > 0"> · 本次新投入 {{ fmtMoney(tradePlan.additional_cash) }}</template>
          · 合计 {{ fmtMoney(tradePlan.total_value) }} · 小额差额（&lt;100元或&lt;1%）自动保持不动
        </div>
        <table v-if="tradePlan" class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-1.5 font-medium">标的</th>
              <th class="px-3 py-1.5 font-medium text-right">当前/目标权重</th>
              <th class="px-3 py-1.5 font-medium text-right">动作</th>
              <th class="px-3 py-1.5 font-medium text-right">金额</th>
              <th class="px-3 py-1.5 font-medium text-right">费用</th>
              <th class="px-3 py-1.5 font-medium text-right">到账</th>
              <th class="px-3 py-1.5 font-medium">提示</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in tradePlan.rows" :key="r.symbol" class="border-t border-border-default">
              <td class="px-3 py-1.5"><div class="font-medium">{{ r.name }}</div><div class="text-xs text-text-muted">{{ r.symbol }}</div></td>
              <td class="px-3 py-1.5 text-right text-xs">
                {{ (r.current_weight * 100).toFixed(1) }}% → <span class="font-medium">{{ (r.target_weight * 100).toFixed(1) }}%</span>
              </td>
              <td class="px-3 py-1.5 text-right">
                <span :class="['px-1.5 py-0.5 text-xs rounded', r.action === 'buy' ? 'bg-income-bg text-income-color' : r.action === 'sell' ? 'bg-expense-bg text-expense-color' : 'bg-bg-tertiary text-text-secondary']">
                  {{ r.action === 'buy' ? '买入' : r.action === 'sell' ? '卖出' : '持有' }}
                </span>
              </td>
              <td class="px-3 py-1.5 text-right font-mono">{{ r.amount ? fmtMoney(r.amount) : '—' }}</td>
              <td class="px-3 py-1.5 text-right text-xs">{{ r.est_fee_pct != null ? `${r.est_fee_pct}% ≈ ${fmtMoney(r.est_fee_amount)}` : '—' }}</td>
              <td class="px-3 py-1.5 text-right text-xs">{{ r.t_plus ? `${r.t_plus} · 约${r.arrive_date}` : '—' }}</td>
              <td class="px-3 py-1.5 text-xs">
                <span v-for="(w, i) in r.warnings" :key="i" :title="w" class="text-warning mr-1">⚠ {{ w }}</span>
                <span v-if="!r.warnings.length" class="text-text-muted">—</span>
              </td>
            </tr>
            <tr v-if="!tradePlan.rows.length"><td colspan="7" class="px-3 py-6 text-center text-text-muted">无数据（先运行信号）</td></tr>
          </tbody>
        </table>
        <div v-else class="py-3 text-center text-xs text-text-muted border border-dashed border-border-default rounded">
          点击「生成调仓清单」对比目标权重与当前持仓；需要把新发的工资一起投入时，先填「本次新投入」金额
        </div>
      </div>

      <!-- 下一调仓日 -->
      <div v-if="currentSignal.next_rebalance_date" class="flex items-center gap-2 px-3 py-2 bg-blue-50 rounded text-sm">
        <span class="text-blue-600">📅</span>
        下一调仓日：<span class="font-medium">{{ currentSignal.next_rebalance_date }}</span>
      </div>
    </div>

    <div v-else class="bg-white rounded-lg shadow-sm p-8 text-center text-text-muted mb-6">
      暂无信号。请先在策略库激活或导入策略，然后运行策略生成信号。
    </div>

    <!-- 错误提示 -->
    <div v-if="runError" class="mb-4 px-4 py-3 bg-expense-bg border border-expense-color rounded text-sm text-expense-color">
      {{ runError }}
    </div>

    <!-- 历史信号 -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <div class="px-4 py-3 bg-bg-tertiary font-medium text-sm">历史信号</div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">运行日期</th>
            <th class="px-3 py-2 font-medium">数据截止日</th>
            <th class="px-3 py-2 font-medium">策略</th>
            <th class="px-3 py-2 font-medium text-center">下一调仓日</th>
            <th class="px-3 py-2 font-medium">关联回测</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sig in signals" :key="sig.id" class="border-t border-border-default">
            <td class="px-3 py-2">{{ sig.run_date }}</td>
            <td class="px-3 py-2 text-text-secondary">{{ sig.as_of_date }}</td>
            <td class="px-3 py-2 text-text-secondary">{{ sig.strategy_name || '—' }}</td>
            <td class="px-3 py-2 text-center text-text-secondary">{{ sig.next_rebalance_date || '-' }}</td>
            <td class="px-3 py-2 text-xs text-text-muted">{{ sig.backtest_id ? sig.backtest_id.slice(0, 8) + '...' : '-' }}</td>
          </tr>
          <tr v-if="!signals.length">
            <td colspan="5" class="px-4 py-6 text-center text-text-muted">暂无历史信号</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { AxiosError } from 'axios'
import { Zap } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import type { SignalResponse, SignalRunResult, TradePlan } from '@/types'

const api = useApi()
const currentSignal = ref<SignalResponse | null>(null)
const signals = ref<SignalResponse[]>([])
const running = ref(false)
const runError = ref('')
const additionalCash = ref<number>(0)
const planError = ref('')

const health = ref<any>(null)
const tradePlan = ref<TradePlan | null>(null)
const planLoading = ref(false)

const weightRows = computed(() => {
  const detail = currentSignal.value?.weights_detail
  if (detail && detail.length) return detail
  const tw = currentSignal.value?.target_weights || {}
  return Object.entries(tw)
    .map(([symbol, weight]) => ({ symbol, name: symbol, weight }))
    .sort((a, b) => b.weight - a.weight)
})

const totalWeightPct = computed(() =>
  weightRows.value.reduce((acc, r) => acc + r.weight, 0).toFixed(1))

const totalValue = computed(() => tradePlan.value?.total_value || 0)

function fmtMoney(v: number): string {
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) + ' 元'
}

async function loadTradePlan() {
  planLoading.value = true
  planError.value = ''
  try {
    const cash = Number(additionalCash.value) || 0
    const res = await api.get<TradePlan>('/signals/trade-plan', {
      params: cash > 0 ? { additional_cash: cash } : {},
    })
    tradePlan.value = res.data
  } catch (e) {
    tradePlan.value = null
    const err = e as AxiosError<{ detail?: string }>
    planError.value = err.response?.data?.detail
      || (err.response ? `HTTP ${err.response.status}` : String(e))
  } finally {
    planLoading.value = false
  }
}

async function loadHealth() {
  try {
    const { data } = await api.get('/monitor/strategy-health')
    health.value = data
  } catch { health.value = null }
}

async function loadSignals() {
  const [current, list] = await Promise.all([
    api.get<SignalResponse | null>('/signals/current').then(r => r.data).catch(() => null),
    api.get<SignalResponse[]>('/signals').then(r => r.data).catch(() => []),
  ])
  currentSignal.value = current
  signals.value = list
}

async function runSignal() {
  running.value = true
  runError.value = ''
  try {
    const result = await api.post<SignalRunResult>('/signals/run', {})
    if (result.data.status === 'ok') {
      await loadSignals()
      await loadTradePlan()
    } else {
      runError.value = result.data.error || '信号生成失败'
    }
  } catch (e) {
    const err = e as AxiosError<{ detail?: string }>
    runError.value = err.response?.data?.detail || String(e)
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadSignals(), loadHealth()])
  if (currentSignal.value) await loadTradePlan()
})
</script>
