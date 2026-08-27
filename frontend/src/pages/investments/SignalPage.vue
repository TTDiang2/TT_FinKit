<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">信号</h2>
      <button @click="runSignal" :disabled="running" class="btn-primary disabled:opacity-50">
        <Zap :size="14" /> {{ running ? '生成中...' : '运行策略生成信号' }}
      </button>
    </div>

    <!-- 当前信号 -->
    <div v-if="currentSignal" class="bg-white rounded-lg shadow-sm p-6 mb-6">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-medium">当前信号</h3>
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

      <!-- 调仓清单 -->
      <div class="mb-4" v-if="currentSignal">
        <div class="flex items-center justify-between mb-2">
          <h4 class="text-sm font-medium">调仓清单（{{ tradePlan?.run_date || '—' }} 信号 vs 当前持仓）</h4>
          <button @click="loadTradePlan" :disabled="planLoading" class="text-xs px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary disabled:opacity-50">
            {{ planLoading ? '计算中…' : (tradePlan ? '刷新清单' : '生成调仓清单') }}
          </button>
        </div>
        <div v-if="tradePlan" class="mb-1 text-xs text-text-muted">
          持仓总市值 {{ fmtMoney(tradePlan.total_value) }} · 小额差额（&lt;100元或&lt;1%）自动保持不动
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
        <div v-else class="py-3 text-center text-xs text-text-muted border border-dashed border-border-default rounded">点击「生成调仓清单」对比目标权重与当前持仓</div>
      </div>

      <!-- 目标权重表 -->
      <div class="mb-4">
        <h4 class="text-sm font-medium mb-2">目标权重</h4>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-1.5 font-medium">标的</th>
              <th class="px-3 py-1.5 font-medium text-right">目标权重</th>
              <th class="px-3 py-1.5 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(weight, assetId) in currentSignal.target_weights" :key="assetId"
              class="border-t border-border-default">
              <td class="px-3 py-1.5 font-medium">{{ assetId }}</td>
              <td class="px-3 py-1.5 text-right">{{ (weight * 100).toFixed(1) }}%</td>
              <td class="px-3 py-1.5 text-right">
                <button class="text-xs text-accent-primary hover:underline">加为持仓</button>
              </td>
            </tr>
          </tbody>
        </table>
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
            <th class="px-3 py-2 font-medium text-center">下一调仓日</th>
            <th class="px-3 py-2 font-medium">关联回测</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="sig in signals" :key="sig.id" class="border-t border-border-default">
            <td class="px-3 py-2">{{ sig.run_date }}</td>
            <td class="px-3 py-2 text-text-secondary">{{ sig.as_of_date }}</td>
            <td class="px-3 py-2 text-center text-text-secondary">{{ sig.next_rebalance_date || '-' }}</td>
            <td class="px-3 py-2 text-xs text-text-muted">{{ sig.backtest_id ? sig.backtest_id.slice(0, 8) + '...' : '-' }}</td>
          </tr>
          <tr v-if="!signals.length">
            <td colspan="4" class="px-4 py-6 text-center text-text-muted">暂无历史信号</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { AxiosError } from 'axios'
import { Zap } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import type { SignalResponse, SignalRunResult } from '@/types'

const api = useApi()
const currentSignal = ref<SignalResponse | null>(null)
const signals = ref<SignalResponse[]>([])
const running = ref(false)
const runError = ref('')

interface TradePlanRow {
  symbol: string; name: string; current_weight: number; target_weight: number;
  action: 'buy' | 'sell' | 'hold'; amount: number;
  est_fee_pct: number | null; est_fee_amount: number;
  t_plus: string | null; arrive_date: string | null; warnings: string[];
}
interface TradePlan {
  signal_id: string | null; run_date: string | null; next_rebalance_date: string | null;
  total_value: number; rows: TradePlanRow[];
}
const tradePlan = ref<TradePlan | null>(null)
const planLoading = ref(false)

function fmtMoney(v: number): string {
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) + ' 元'
}

async function loadTradePlan() {
  planLoading.value = true
  try {
    const res = await api.get<TradePlan>('/signals/trade-plan')
    tradePlan.value = res.data
  } catch { tradePlan.value = null } finally { planLoading.value = false }
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
  await loadSignals()
  if (currentSignal.value) await loadTradePlan()
})
</script>
