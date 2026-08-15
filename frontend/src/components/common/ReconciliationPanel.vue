<template>
  <div class="bg-white rounded-lg shadow-sm overflow-hidden">
    <div class="p-4 border-b border-border-default">
      <h3 class="font-semibold text-sm">校验</h3>
      <p class="text-xs text-text-muted mt-0.5">用银行 APP 月度汇总核对簿记（第 1 层），再用今日余额兜底（第 3 层）</p>
    </div>

    <div class="p-4 space-y-4">
      <!-- 账户选择 -->
      <div class="flex flex-wrap items-center gap-3">
        <select v-model="accountId" @change="onAccountChange" class="px-3 py-2 border border-border-default rounded-md text-sm">
          <option value="">选择账户…</option>
          <option v-for="a in cashAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
        </select>
        <span class="text-sm text-text-secondary">校验月份：{{ props.year }}年{{ String(props.month).padStart(2, '0') }}月（跟随上方记账月份）</span>
        <button v-if="accountId" @click="onAccountChange" class="text-xs text-text-secondary hover:text-accent-primary">重新加载</button>
      </div>

      <!-- 未选账户引导 -->
      <div v-if="!accountId" class="border border-dashed border-border-default rounded-md p-4 text-sm text-text-muted">
        ① 选择账户（工资账户 / 消费账户）<br />
        ② 选月份后，对照银行 APP 该月的"总支出 / 总收入"，填入下方"银行实际"并点核对<br />
        ③ 再往下用"今日余额核对"做最终兜底
      </div>

      <!-- 第 1 层：月度汇总核对 -->
      <div v-if="accountId" class="border border-border-default rounded-md p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">月度汇总核对</span>
          <span v-if="summary?.bank_statement_mode === 'composite'" class="text-xs text-amber-600">已按银行口径换算（转账+退款+利息 / 毛支出）</span>
        </div>
        <div v-if="summaryLoading" class="text-sm text-text-muted">加载中…</div>
        <div v-else-if="summaryError" class="text-sm text-expense-color">{{ summaryError }}</div>
        <div v-else-if="summary" class="space-y-2">
          <div class="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div class="text-xs text-text-muted mb-1">系统期望收入</div>
              <div class="font-medium">{{ sym }}{{ fmt(summary.bank_expected.income) }}</div>
            </div>
            <div>
              <div class="text-xs text-text-muted mb-1">系统期望支出</div>
              <div class="font-medium">{{ sym }}{{ fmt(summary.bank_expected.expense) }}</div>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="block text-xs text-text-muted mb-1">银行实际收入</label>
              <input v-model.number="bankIncome" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md text-sm" /></div>
            <div><label class="block text-xs text-text-muted mb-1">银行实际支出</label>
              <input v-model.number="bankExpense" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md text-sm" /></div>
          </div>
          <div class="flex items-center gap-3">
            <button @click="checkMonthly" :disabled="summaryChecking || bankIncome === null || bankIncome === undefined || bankExpense === null || bankExpense === undefined"
              class="px-4 py-2 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover disabled:opacity-40">
              {{ summaryChecking ? '核对中…' : '核对' }}
            </button>
            <span v-if="checkResult !== null" :class="checkResult === 0 ? 'text-income-color text-sm' : 'text-expense-color text-sm'">
              {{ checkResult === 0 ? '✓ 一致' : `✗ 收入差 ${signed(resultIncomeDiff)} / 支出差 ${signed(resultExpenseDiff)}` }}
            </span>
          </div>
        </div>
      </div>

      <!-- 第 3 层：今日余额核对 -->
      <div v-if="accountId" class="border border-border-default rounded-md p-3">
        <span class="text-sm font-medium">今日余额核对</span>
        <div v-if="balanceLoading" class="text-sm text-text-muted mt-1">加载中…</div>
        <div v-else-if="balanceCheck" class="mt-2 space-y-2">
          <div class="text-sm">系统期望余额：<span class="font-medium">{{ sym }}{{ fmt(balanceCheck.expected_balance) }}</span>
            <span v-if="!balanceCheck.can_check" class="text-xs text-amber-600 ml-2">{{ balanceCheck.hint }}</span>
          </div>
          <div class="flex items-center gap-3">
            <input v-model.number="actualBalance" type="number" step="0.01" placeholder="银行 APP 当前余额"
              class="w-56 px-3 py-2 border border-border-default rounded-md text-sm" :disabled="!balanceCheck.can_check" />
            <button @click="checkBalance" :disabled="balanceChecking || !balanceCheck.can_check || actualBalance === null || actualBalance === undefined"
              class="px-4 py-2 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover disabled:opacity-40">
              {{ balanceChecking ? '核对中…' : '核对' }}
            </button>
            <span v-if="balanceResult !== null" :class="balanceResult === 0 ? 'text-income-color text-sm' : 'text-expense-color text-sm'">
              {{ balanceResult === 0 ? '✓ 一致' : `✗ 差 ${signed(balanceResult)}` }}
            </span>
          </div>
        </div>
      </div>

      <!-- 校验历史 -->
      <div v-if="accountId">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm font-medium">校验历史</span>
          <button @click="loadHistory" class="text-xs text-text-secondary hover:text-accent-primary">刷新</button>
        </div>
        <div v-if="historyLoading" class="text-sm text-text-muted">加载中…</div>
        <table v-else class="w-full text-xs">
          <thead><tr class="text-text-muted"><th class="px-2 py-1 text-left">月份</th><th class="px-2 py-1 text-right">银行收入</th><th class="px-2 py-1 text-right">银行支出</th><th class="px-2 py-1 text-right">差异</th><th class="px-2 py-1 text-center">状态</th><th class="px-2 py-1 text-right">时间</th><th class="px-2 py-1 text-center">操作</th></tr></thead>
          <tbody>
            <tr v-for="r in history" :key="r.id" class="border-t border-border-default">
              <td class="px-2 py-1">{{ r.month === 0 ? '余额核对' : `${r.year}-${String(r.month).padStart(2, '0')}` }}</td>
              <td class="px-2 py-1 text-right">{{ r.month === 0 ? '—' : fmt(r.bank_income) }}</td>
              <td class="px-2 py-1 text-right">{{ r.month === 0 ? '—' : fmt(r.bank_expense) }}</td>
              <td class="px-2 py-1 text-right">
                <span v-if="r.month === 0">{{ signed(r.balance_diff) }}</span>
                <span v-else>{{ signed(r.income_diff) }} / {{ signed(r.expense_diff) }}</span>
              </td>
              <td class="px-2 py-1 text-center">
                <span :class="r.status === 'matched' ? 'text-income-color' : 'text-expense-color'">{{ r.status === 'matched' ? '通过' : '有差异' }}</span>
              </td>
              <td class="px-2 py-1 text-right text-text-muted">{{ formatDate(r.checked_at) }}</td>
              <td class="px-2 py-1 text-center"><button @click="deleteRecord(r.id)" class="text-text-muted hover:text-expense-color">删除</button></td>
            </tr>
            <tr v-if="!history.length"><td colspan="7" class="px-2 py-3 text-center text-text-muted">暂无校验记录</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useAccountsStore } from '@/stores/accounts'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { AccountSummary, ExpectedBalance, ReconciliationRecord } from '@/types'

const props = defineProps<{ year: number; month: number }>()

const accStore = useAccountsStore()
const settingsStore = useSettingsStore()
const api = useApi()
const { show } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)

const now = new Date()
const accountId = ref('')

const cashAccounts = computed(() => accStore.accounts.filter(a => a.account_type !== 'investment'))

const summary = ref<AccountSummary | null>(null)
const summaryLoading = ref(false)
const summaryError = ref('')
const bankIncome = ref<number | null>(null)
const bankExpense = ref<number | null>(null)
const summaryChecking = ref(false)
const checkResult = ref<number | null>(null)
const resultIncomeDiff = ref(0)
const resultExpenseDiff = ref(0)

const balanceCheck = ref<ExpectedBalance | null>(null)
const balanceLoading = ref(false)
const actualBalance = ref<number | null>(null)
const balanceChecking = ref(false)
const balanceResult = ref<number | null>(null)

const history = ref<ReconciliationRecord[]>([])
const historyLoading = ref(false)

function fmt(n: number | null | undefined): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function signed(n: number | null | undefined): string { const v = n ?? 0; return (v >= 0 ? '+' : '') + sym.value + fmt(Math.abs(v)) }
function formatDate(s: string) { return new Date(s).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' }) }

async function onAccountChange() {
  bankIncome.value = null
  bankExpense.value = null
  actualBalance.value = null
  checkResult.value = null
  balanceResult.value = null
  summary.value = null
  summaryError.value = ''
  balanceCheck.value = null
  if (!accountId.value) return
  await Promise.all([loadSummary(), loadBalanceCheck(), loadHistory()])
}

async function loadSummary() {
  if (!accountId.value) return
  summaryLoading.value = true
  summaryError.value = ''
  try {
    const res = await api.get('/reconciliation/account-summary', { params: { account_id: accountId.value, year: props.year, month: props.month } })
    summary.value = res.data
  } catch (e: any) {
    summaryError.value = e.response?.data?.detail || '加载汇总失败，请检查后端是否已重启'
  }
  finally { summaryLoading.value = false }
}

async function loadBalanceCheck() {
  if (!accountId.value) return
  balanceLoading.value = true
  try {
    const res = await api.get('/reconciliation/expected-balance', { params: { account_id: accountId.value } })
    balanceCheck.value = res.data
  } catch (e: any) { show(e.response?.data?.detail || '加载余额失败', 'error') }
  finally { balanceLoading.value = false }
}

async function checkMonthly() {
  if (!accountId.value || bankIncome.value === null || bankExpense.value === null) return
  summaryChecking.value = true
  try {
    await api.post('/reconciliation/records', {
      account_id: accountId.value, year: props.year, month: props.month,
      bank_income: bankIncome.value, bank_expense: bankExpense.value,
    })
    const res = await api.get('/reconciliation/account-summary', { params: { account_id: accountId.value, year: props.year, month: props.month } })
    const fresh = res.data as AccountSummary
    summary.value = fresh
    resultIncomeDiff.value = (bankIncome.value ?? 0) - fresh.bank_expected.income
    resultExpenseDiff.value = (bankExpense.value ?? 0) - fresh.bank_expected.expense
    checkResult.value = Math.abs(resultIncomeDiff.value) < 0.005 && Math.abs(resultExpenseDiff.value) < 0.005 ? 0 : 1
    show(checkResult.value === 0 ? '校验通过' : '存在差异，请检查流水', checkResult.value === 0 ? 'success' : 'warning')
    await loadHistory()
  } catch (e: any) { show(e.response?.data?.detail || '保存校验记录失败', 'error') }
  finally { summaryChecking.value = false }
}

async function checkBalance() {
  if (!accountId.value || actualBalance.value === null) return
  balanceChecking.value = true
  try {
    await api.post('/reconciliation/records', {
      account_id: accountId.value, year: now.getFullYear(), month: 0,
      balance_check_actual: actualBalance.value,
    })
    const res = await api.get('/reconciliation/expected-balance', { params: { account_id: accountId.value } })
    const fresh = res.data as ExpectedBalance
    balanceCheck.value = fresh
    balanceResult.value = (actualBalance.value ?? 0) - fresh.expected_balance
    show(Math.abs(balanceResult.value) < 0.005 ? '余额一致' : '余额有差异', Math.abs(balanceResult.value) < 0.005 ? 'success' : 'warning')
    await loadHistory()
  } catch (e: any) { show(e.response?.data?.detail || '保存余额校验失败', 'error') }
  finally { balanceChecking.value = false }
}

async function loadHistory() {
  if (!accountId.value) return
  historyLoading.value = true
  try {
    const res = await api.get('/reconciliation/records', { params: { account_id: accountId.value } })
    history.value = res.data
  } catch { history.value = [] }
  finally { historyLoading.value = false }
}

async function deleteRecord(id: string) {
  if (!confirm('确定删除此校验记录？')) return
  try { await api.delete(`/reconciliation/records/${id}`); await loadHistory() }
  catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

// 跟随父组件（记账 tab）切换月份
watch(() => [props.year, props.month], () => {
  if (!accountId.value) return
  loadSummary()
})

onMounted(() => { accStore.fetchAccounts() })
</script>
