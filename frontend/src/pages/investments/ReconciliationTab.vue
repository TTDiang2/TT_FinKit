<template>
  <div class="space-y-4">
    <!-- 恒等式卡片 -->
    <div class="bg-white rounded-lg shadow-sm p-4">
      <div class="flex items-center justify-between mb-1">
        <h3 class="font-semibold text-sm">投资账户勾稽恒等式</h3>
        <span :class="['text-xs px-2 py-0.5 rounded', data?.identity.right_side.passed ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800']">
          {{ data?.identity.right_side.passed ? '通过' : '不通过' }}
        </span>
      </div>
      <p class="text-xs text-text-muted mb-3">记账余额 = 入金 − 出金 + 落袋盈亏(含分红) − 分红 + 浮动盈亏 − 当月盈亏；通过标准：差额绝对值 ≤ 0.01</p>

      <div v-if="data" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- 左侧：记账余额 -->
        <div class="rounded-lg bg-bg-tertiary p-4">
          <div class="text-xs text-text-muted">{{ data.identity.left_side.label }}</div>
          <div class="text-2xl font-bold font-mono mt-1">{{ sym }}{{ fmt(data.identity.left_side.value) }}</div>
          <div class="text-xs text-text-muted mt-2">来自记账 tab 投资账户（期初 + 收入 − 支出 + 转入 − 转出）</div>
        </div>

        <!-- 右侧：恒等式展开 -->
        <div>
          <div v-for="(item, i) in data.identity.right_side.items" :key="i"
               :class="['flex items-center justify-between py-1 text-sm font-mono', item.operator === '' ? 'pl-6 text-text-secondary' : '']">
            <span class="text-text-secondary">{{ item.operator === '+' ? '+' : item.operator === '-' ? '−' : '' }} {{ item.label }}</span>
            <span :class="item.operator === '' ? '' : 'font-medium'">{{ signed(item.value) }}</span>
          </div>
          <div class="flex items-center justify-between pt-2 mt-1 border-t border-border-default font-mono">
            <span class="font-medium text-sm">= 恒等式右侧</span>
            <span class="font-bold">{{ sym }}{{ fmt(data.identity.right_side.total) }}</span>
          </div>
          <div class="flex items-center justify-between pt-1 text-xs text-text-muted font-mono">
            <span>勾稽差额（记账余额 − 右侧）</span>
            <span :class="data.identity.right_side.passed ? 'text-income-color' : 'text-expense-color'">
              {{ signed(data.identity.right_side.diff) }}
            </span>
          </div>
        </div>
      </div>
      <div v-else class="text-sm text-text-muted py-4">{{ error || '加载中…' }}</div>
    </div>

    <!-- 辅助校验卡片 -->
    <div v-if="data" class="bg-white rounded-lg shadow-sm p-4">
      <h3 class="font-semibold text-sm mb-2">辅助校验</h3>
      <div class="grid grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
        <div>
          <div class="text-xs text-text-muted">当前持仓市值</div>
          <div class="font-medium font-mono">{{ sym }}{{ fmt(data.auxiliary.market_value) }}</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">闲置现金</div>
          <div class="font-medium font-mono" :class="data.auxiliary.idle_cash >= 0 ? '' : 'text-expense-color'">{{ sym }}{{ fmt(data.auxiliary.idle_cash) }}</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">{{ data.auxiliary.idle_cash_check.label }}</div>
          <div class="font-medium font-mono" :class="Math.abs(data.auxiliary.idle_cash_check.value) <= 0.01 ? 'text-income-color' : ''">{{ signed(data.auxiliary.idle_cash_check.value) }}</div>
        </div>
      </div>
      <ul v-if="data.auxiliary.warnings.length" class="mt-2 space-y-1">
        <li v-for="(w, i) in data.auxiliary.warnings" :key="i" class="text-xs text-expense-color">{{ w }}</li>
      </ul>
      <p v-else class="text-xs text-text-muted mt-2">无警告，投资 tab 与记账 tab 勾稽一致。</p>
    </div>

    <!-- 账户级勾稽卡片 -->
    <div v-if="data?.account_checks?.length" class="bg-white rounded-lg shadow-sm overflow-hidden">
      <div class="p-4 border-b border-border-default">
        <h3 class="font-semibold text-sm">账户级勾稽</h3>
        <p class="text-xs text-text-muted mt-0.5">每个记账账户：期望余额 = 期初 + 收入 − 支出 + 转入 − 转出（转账计入余额，与校验口径无关）；差额 ≤ 0.01 即通过。</p>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-2 font-medium">账户</th>
              <th class="px-3 py-2 font-medium text-right">期初</th>
              <th class="px-3 py-2 font-medium text-right">收入</th>
              <th class="px-3 py-2 font-medium text-right">支出</th>
              <th class="px-3 py-2 font-medium text-right">转入</th>
              <th class="px-3 py-2 font-medium text-right">转出</th>
              <th class="px-3 py-2 font-medium text-right">期望余额</th>
              <th class="px-3 py-2 font-medium text-right">实际余额</th>
              <th class="px-3 py-2 font-medium text-right">差额</th>
              <th class="px-3 py-2 font-medium text-center">结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in data.account_checks" :key="a.account_id" class="border-t border-border-default text-text-muted">
              <td class="px-3 py-2 font-medium text-text-primary">{{ a.account_name }}<span class="text-xs text-text-muted ml-1">{{ a.account_type === 'cash' ? '现金' : a.account_type === 'investment' ? '投资' : a.account_type === 'custodial' ? '代管' : '' }}</span></td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.initial_balance) }}</td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.income) }}</td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.expense) }}</td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.transfer_in) }}</td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.transfer_out) }}</td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.expected_balance) }}</td>
              <td class="px-3 py-2 text-right font-mono">{{ fmt(a.actual_balance) }}</td>
              <td class="px-3 py-2 text-right font-mono" :class="Math.abs(a.diff) <= 0.01 ? '' : 'text-expense-color'">{{ signed(a.diff) }}</td>
              <td class="px-3 py-2 text-center">
                <span :class="['text-xs px-2 py-0.5 rounded', a.passed ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800']">{{ a.passed ? '通过' : '不通过' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 出入金对应勾稽卡片 -->
    <div v-if="data?.flow_checks" class="bg-white rounded-lg shadow-sm p-4">
      <h3 class="font-semibold text-sm mb-1">出入金对应勾稽</h3>
      <p class="text-xs text-text-muted mb-3">投资 tab 的入金/出金由记账 tab 投资账户的转入/转出转账同步生成（首笔初始余额入金除外）；两边差额应约为 0。</p>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 text-sm">
        <div class="rounded-lg bg-bg-tertiary p-3 space-y-1.5">
          <div class="text-xs text-text-muted font-medium">入金侧</div>
          <div class="flex justify-between font-mono"><span>投资 tab 入金合计</span><span>{{ sym }}{{ fmt(data.flow_checks.deposits.investment_tab_total) }}</span></div>
          <div class="flex justify-between font-mono text-text-secondary"><span>其中：初始余额入金</span><span>{{ sym }}{{ fmt(data.flow_checks.deposits.initial_balance_deposit) }}</span></div>
          <div class="flex justify-between font-mono"><span>记账 tab 转入投资账户合计</span><span>{{ sym }}{{ fmt(data.flow_checks.deposits.bookkeeping_transfer_in) }}</span></div>
          <div class="flex justify-between font-mono border-t border-border-default pt-1" :class="Math.abs(data.flow_checks.deposits.diff) <= 0.01 ? '' : 'text-expense-color'">
            <span>差额（入金 − 初始余额 − 记账转入）</span><span>{{ signed(data.flow_checks.deposits.diff) }}</span>
          </div>
        </div>
        <div class="rounded-lg bg-bg-tertiary p-3 space-y-1.5">
          <div class="text-xs text-text-muted font-medium">出金侧</div>
          <div class="flex justify-between font-mono"><span>投资 tab 出金合计</span><span>{{ sym }}{{ fmt(data.flow_checks.withdrawals.investment_tab_total) }}</span></div>
          <div class="flex justify-between font-mono"><span>记账 tab 从投资账户转出合计</span><span>{{ sym }}{{ fmt(data.flow_checks.withdrawals.bookkeeping_transfer_out) }}</span></div>
          <div class="flex justify-between font-mono border-t border-border-default pt-1" :class="Math.abs(data.flow_checks.withdrawals.diff) <= 0.01 ? '' : 'text-expense-color'">
            <span>差额（出金 − 记账转出）</span><span>{{ signed(data.flow_checks.withdrawals.diff) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 同步状态勾稽卡片 -->
    <div v-if="data?.sync_checks" class="bg-white rounded-lg shadow-sm p-4">
      <h3 class="font-semibold text-sm mb-1">盈亏同步状态</h3>
      <p class="text-xs text-text-muted mb-3">「同步盈亏到记账」按月把投资 tab 月度盈亏写入记账 tab（收入 + 分类=投资，描述含「投资月度盈亏」）；当前月盈亏不入账。</p>
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
        <div>
          <div class="text-xs text-text-muted">已入账月数</div>
          <div class="font-medium font-mono">{{ data.sync_checks.booked_monthly_count }} 个月</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">已入账盈亏合计</div>
          <div class="font-medium font-mono">{{ sym }}{{ fmt(data.sync_checks.booked_monthly_total) }}</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">入账区间</div>
          <div class="font-medium font-mono">{{ data.sync_checks.first_booked_month || '—' }} ~ {{ data.sync_checks.last_booked_month || '—' }}</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">当前月处理</div>
          <div class="font-medium" :class="data.sync_checks.current_month_skipped ? 'text-text-secondary' : 'text-expense-color'">{{ data.sync_checks.current_month_skipped ? '已跳过（不入账）' : '已入账' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'
import type { InvestmentReconciliation } from '@/types'

const api = useApi()
const settingsStore = useSettingsStore()
const sym = computed(() => settingsStore.settings.currency_symbol)

const data = ref<InvestmentReconciliation | null>(null)
const error = ref('')

function fmt(n: number): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function signed(n: number): string { return (n >= 0 ? '+' : '') + sym.value + fmt(Math.abs(n)) }

async function load() {
  error.value = ''
  try {
    const res = await api.get('/investments/reconciliation')
    data.value = res.data
  } catch (e: any) {
    data.value = null
    error.value = e.response?.data?.detail || '加载勾稽数据失败'
  }
}

onMounted(load)
</script>
