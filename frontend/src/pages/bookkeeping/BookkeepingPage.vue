<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-4">
        <button @click="showImportModal = true" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary flex items-center gap-1 text-sm">
          <Upload :size="16" /> 导入
        </button>
        <div class="flex items-center gap-2">
          <button @click="shiftYear(-1)" title="上一年" class="px-2 py-1.5 border border-border-default rounded-md hover:bg-bg-tertiary text-sm">◀</button>
          <span class="font-bold text-sm px-1 whitespace-nowrap">{{ year }}年</span>
          <button @click="shiftYear(1)" title="下一年" class="px-2 py-1.5 border border-border-default rounded-md hover:bg-bg-tertiary text-sm">▶</button>
          <div class="grid grid-cols-6 gap-1">
            <button v-for="m in 12" :key="m" @click="selectMonth(m)"
                    :class="m === month ? 'bg-accent-primary text-white font-bold' : 'hover:bg-bg-tertiary'"
                    class="px-2 py-1 rounded-md text-sm">{{ m }}月</button>
          </div>
          <button v-if="year !== now.year() || month !== now.month() + 1" @click="goCurrentMonth"
                  class="text-xs text-text-secondary hover:text-accent-primary whitespace-nowrap">回到当前月</button>
        </div>
      </div>
      <button @click="showModal = true; resetForm()" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover flex items-center gap-1">
        <Plus :size="16" /> 添加记账
      </button>
    </div>

    <div class="grid grid-cols-5 gap-4 mb-6">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">收入</div>
        <div class="text-xl font-bold text-income-color">{{ sym }}{{ monthStats.income.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">支出</div>
        <div class="text-xl font-bold text-expense-color">{{ sym }}{{ monthStats.expense.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">结余</div>
        <div class="text-xl font-bold" :class="monthStats.net >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ monthStats.net.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">当月储蓄率</div>
        <div class="text-xl font-bold text-accent-primary">{{ monthStats.savingsRate.toFixed(1) }}%</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">当月必要支出占比</div>
        <div class="text-xl font-bold text-expense-color">{{ monthStats.necessaryExpenseRatio.toFixed(1) }}%</div>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm mb-6">
      <div class="flex items-center justify-between px-4 py-3 border-b border-border-default">
        <h4 class="font-semibold text-sm">账户余额（截至 {{ year }}年{{ String(month).padStart(2, '0') }}月）</h4>
        <button @click="showBalances = !showBalances" class="text-xs text-text-secondary hover:text-accent-primary">
          {{ showBalances ? '收起明细' : '展开明细' }}
        </button>
      </div>
      <div class="px-4 py-3 flex flex-wrap gap-4">
        <div v-for="b in balancesAsOf" :key="b.account_id" class="min-w-[140px]">
          <div class="text-xs text-text-secondary">{{ b.account_name }}</div>
          <div class="text-lg font-bold" :class="b.balance >= 0 ? 'text-income-color' : 'text-expense-color'">
            {{ sym }}{{ b.balance.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}
          </div>
        </div>
        <div v-if="!balancesAsOf.length" class="text-sm text-text-muted">加载中…</div>
      </div>
      <div v-if="showBalances" class="border-t border-border-default overflow-auto">
        <table class="w-full text-xs">
          <thead class="bg-bg-tertiary text-left">
            <tr class="text-text-muted">
              <th class="px-4 py-2 font-medium">账户</th>
              <th class="px-4 py-2 text-right font-medium">期初</th>
              <th class="px-4 py-2 text-right font-medium">收入</th>
              <th class="px-4 py-2 text-right font-medium">支出</th>
              <th class="px-4 py-2 text-right font-medium">转入</th>
              <th class="px-4 py-2 text-right font-medium">转出</th>
              <th class="px-4 py-2 text-right font-medium">余额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="b in balancesAsOf" :key="b.account_id" class="border-t border-border-default">
              <td class="px-4 py-2">{{ b.account_name }}</td>
              <td class="px-4 py-2 text-right font-mono">{{ fmtAmount(b.initial_balance) }}</td>
              <td class="px-4 py-2 text-right font-mono text-income-color">{{ fmtAmount(b.income) }}</td>
              <td class="px-4 py-2 text-right font-mono text-expense-color">{{ fmtAmount(b.expense) }}</td>
              <td class="px-4 py-2 text-right font-mono">{{ fmtAmount(b.transfer_in) }}</td>
              <td class="px-4 py-2 text-right font-mono">{{ fmtAmount(b.transfer_out) }}</td>
              <td class="px-4 py-2 text-right font-mono font-bold" :class="b.balance >= 0 ? 'text-income-color' : 'text-expense-color'">{{ fmtAmount(b.balance) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h4 class="font-semibold mb-3">收入分类</h4>
        <div class="h-44"><Doughnut v-if="incomeCategoryData.labels.length" :data="incomeCategoryData" :options="{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' as const, labels: { boxWidth: 10, font: { size: 11 } } } } }" /></div>
        <div v-if="!incomeCategoryData.labels.length" class="text-center text-text-muted py-6">暂无数据</div>
        <div v-if="incomeSummary.total > 0 || incomeSummary.negative > 0" class="mt-2">
          <div class="flex h-2.5 rounded overflow-hidden bg-bg-tertiary" :title="`正向收入 ${fmtAmount(incomeSummary.positive)} | 净收入 ${fmtAmount(incomeSummary.total)}`">
            <div v-if="incomeSummary.negative > 0" :style="{ width: (incomeSummary.negative / Math.max(incomeSummary.positive, 1) * 100) + '%' }" class="bg-expense-color"></div>
            <div :style="{ width: '100%' }" class="bg-income-color opacity-90 -ml-1"></div>
          </div>
          <div class="flex justify-between text-xs text-text-muted mt-1">
            <span>亏损 <span class="text-expense-color font-medium">{{ fmtAmount(incomeSummary.negative) }}</span></span>
            <span>净收入 <span :class="incomeSummary.total >= 0 ? 'text-income-color' : 'text-expense-color'" class="font-medium">{{ fmtAmount(incomeSummary.total) }}</span></span>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h4 class="font-semibold mb-3">支出分类</h4>
        <div class="h-44"><Doughnut v-if="expenseCategoryData.labels.length" :data="expenseCategoryData" :options="{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' as const, labels: { boxWidth: 10, font: { size: 11 } } } } }" /></div>
        <div v-if="!expenseCategoryData.labels.length" class="text-center text-text-muted py-6">暂无数据</div>
        <div v-if="expenseSummary.total > 0 || expenseSummary.negative > 0" class="mt-2">
          <div class="flex h-2.5 rounded overflow-hidden bg-bg-tertiary" :title="`正向支出 ${fmtAmount(expenseSummary.positive)} | 净支出 ${fmtAmount(expenseSummary.total)}`">
            <div v-if="expenseSummary.negative > 0" :style="{ width: (expenseSummary.negative / Math.max(expenseSummary.positive, 1) * 100) + '%' }" class="bg-income-color"></div>
            <div :style="{ width: '100%' }" class="bg-expense-color opacity-90 -ml-1"></div>
          </div>
          <div class="flex justify-between text-xs text-text-muted mt-1">
            <span>退款 <span class="text-income-color font-medium">{{ fmtAmount(expenseSummary.negative) }}</span></span>
            <span>净支出 <span class="text-expense-color font-medium">{{ fmtAmount(expenseSummary.total) }}</span></span>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm h-56">
        <h4 class="font-semibold mb-3">每日支出</h4>
        <Line v-if="dailySpendingData.labels.length" :data="dailySpendingData" :options="dailySpendingOptions" />
        <div v-else class="text-center text-text-muted py-6">暂无数据</div>
      </div>
    </div>

    <div class="flex items-center gap-4 mb-4">
      <div class="flex items-center gap-2">
        <span class="text-sm text-text-secondary">排序</span>
        <div class="flex border border-border-default rounded-md overflow-hidden">
          <button v-for="opt in sortOptions" :key="opt.value" @click="sortBy = opt.value"
            :class="['px-3 py-1.5 text-sm transition-colors', sortBy === opt.value ? 'bg-accent-primary text-white' : 'bg-white text-text-secondary hover:bg-gray-50']">
            {{ opt.label }}
          </button>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-sm text-text-secondary">分类</span>
        <select v-model="filterCatId" class="px-3 py-1.5 border border-border-default rounded-md text-sm">
          <option value="">全部</option>
          <option value="__refund__">消费退货（负支出）</option>
          <option v-for="cat in allCategories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
        </select>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-sm text-text-secondary">账户</span>
        <select v-model="filterAccId" class="px-3 py-1.5 border border-border-default rounded-md text-sm">
          <option value="">全部</option>
          <option v-for="acc in accounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option>
        </select>
      </div>
    </div>

    <div v-for="section in sections" :key="section.type" class="mb-4">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <button @click="collapsed[section.type] = !collapsed[section.type]" class="flex items-center gap-2">
            <ChevronDown v-if="collapsed[section.type]" :size="16" class="text-text-muted" />
            <ChevronUp v-else :size="16" class="text-text-muted" />
            <div class="w-2 h-2 rounded-full" :class="section.color"></div>
            <h3 class="text-sm font-medium text-text-secondary uppercase">{{ section.label }}</h3>
          </button>
        </div>
        <span class="text-sm font-medium" :class="signColorClass(section.amount, section.type)">{{ amountText(section.amount, section.type) }}</span>
      </div>
      <div v-show="!collapsed[section.type]" class="bg-white rounded-lg shadow-sm divide-y divide-border-default">
        <div v-for="txn in section.items" :key="txn.id" class="flex items-center justify-between px-4 py-3">
          <div class="flex items-center gap-3">
            <div class="text-xs text-text-muted w-14">{{ txn.date.replace(/-/g, '/').slice(5) }}</div>
            <div class="flex items-center gap-2">
              <div v-if="txn.category_color" class="w-2 h-2 rounded-full flex-shrink-0" :style="{ backgroundColor: txn.category_color }"></div>
              <div>
                <div class="text-sm font-medium">{{ txn.description || txn.category_name || txn.type }}</div>
                <div class="text-xs text-text-muted">{{ txn.account_name }}</div>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-3">
            <span class="text-sm font-medium" :class="signColorClass(txn.amount, section.type)">{{ amountText(txn.amount, section.type) }}</span>
            <button @click="editTxn(txn)" class="text-text-muted hover:text-text-primary"><Edit2 :size="14" /></button>
            <button @click="removeTxn(txn.id)" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
          </div>
        </div>
        <div v-if="!section.items.length" class="px-4 py-3 text-sm text-text-muted text-center">暂无记录</div>
      </div>
    </div>

    <BaseModal v-if="showModal" :title="editId ? '编辑记账' : '添加记账'" @close="showModal = false" class="modal-in">
      <div class="space-y-3">
        <div class="flex gap-2">
          <button v-for="t in (['expense', 'income', 'transfer'] as const)" :key="t" @click="form.type = t"
            :class="['flex-1 py-2 text-sm rounded-md border transition-colors', form.type === t ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default text-text-secondary']">
            {{ t === 'expense' ? '支出' : t === 'income' ? '收入' : '转账' }}
          </button>
        </div>
        <div><label class="block text-sm mb-1">日期</label><input v-model="form.date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">金额</label><input v-model.number="form.amount" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="0.00" /></div>
        <div v-if="form.type !== 'transfer'"><label class="block text-sm mb-1">分类</label>
          <select v-model="form.category_id" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">选择分类</option>
            <option v-for="c in catsForType" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </div>
        <div><label class="block text-sm mb-1">{{ form.type === 'transfer' ? '转出账户' : '账户' }}</label>
          <select v-model="form.account_id" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">选择账户</option><option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>
        <div v-if="form.type === 'transfer'"><label class="block text-sm mb-1">转入账户</label>
          <select v-model="form.dest_account_id" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">选择账户</option><option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </div>
        <div><label class="block text-sm mb-1">备注</label><input v-model="form.description" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="简要描述" /></div>
      </div>
      <template #footer>
        <button @click="showModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="saveTxn" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">{{ editId ? '更新' : '添加' }}</button>
      </template>
    </BaseModal>
    <ImportModal v-if="showImportModal" @close="showImportModal = false" @imported="onImported" />

    <!-- 校验模块：月度汇总核对 + 今日余额核对（跟随当前记账月份） -->
    <div class="mt-4">
      <ReconciliationPanel :year="year" :month="month" />
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Doughnut, Line } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend, PointElement, LineElement, CategoryScale, LinearScale, Filler } from 'chart.js'
import { Plus, Edit2, Trash2, ChevronDown, ChevronUp, Upload } from 'lucide-vue-next'
import dayjs from 'dayjs'
import { useAccountsStore } from '@/stores/accounts'
import { useCategoriesStore } from '@/stores/categories'
import { useTransactionsStore } from '@/stores/transactions'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import ImportModal from '@/components/common/ImportModal.vue'
import ReconciliationPanel from '@/components/common/ReconciliationPanel.vue'

ChartJS.register(ArcElement, Tooltip, Legend, PointElement, LineElement, CategoryScale, LinearScale, Filler)

const accStore = useAccountsStore()
const catStore = useCategoriesStore()
const txnStore = useTransactionsStore()
const settingsStore = useSettingsStore()
const api = useApi()
const { show } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)
const accounts = computed(() => accStore.accounts)
const catsForType = computed(() => catStore.categories.filter(c => c.type === form.value.type || form.value.type === 'transfer'))

const expenseCategoryData = ref<{ labels: string[]; datasets: { data: number[]; backgroundColor: string[] }[] }>({ labels: [], datasets: [] })
const incomeCategoryData = ref<{ labels: string[]; datasets: { data: number[]; backgroundColor: string[] }[] }>({ labels: [], datasets: [] })
const incomeSummary = ref({ positive: 0, negative: 0, total: 0 })
const expenseSummary = ref({ positive: 0, negative: 0, total: 0 })
const dailySpendingData = ref<{ labels: string[]; datasets: { label: string; data: number[]; borderColor: string; backgroundColor: string; tension: number; fill: boolean }[] }>({ labels: [], datasets: [] })

const dailySpendingOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { display: false } },
  scales: { x: { ticks: { font: { size: 10 }, maxRotation: 0 }, grid: { display: false } }, y: { ticks: { font: { size: 10 } } } },
  elements: { line: { tension: 0.4 } }
}

const now = dayjs()
const year = ref(now.year()), month = ref(now.month() + 1)

function shiftYear(d: number) {
  year.value += d
  loadMonth()
}
function selectMonth(m: number) {
  month.value = m
  loadMonth()
}
function goCurrentMonth() {
  year.value = now.year()
  month.value = now.month() + 1
  loadMonth()
}

const showModal = ref(false), editId = ref<string | null>(null)
const showImportModal = ref(false)
const form = ref<{ type: 'income' | 'expense' | 'transfer'; date: string; amount: number; account_id: string; dest_account_id: string; category_id: string; description: string }>({ type: 'expense', date: dayjs().format('YYYY-MM-DD'), amount: 0, account_id: '', dest_account_id: '', category_id: '', description: '' })

const collapsed = ref<Record<string, boolean>>({ expense: false, income: false, transfer: false })
const sortBy = ref<'date' | 'amount-asc' | 'amount-desc'>('date')
const filterCatId = ref('')
const filterAccId = ref('')

const sortOptions = [
  { value: 'date' as const, label: '按日期' },
  { value: 'amount-asc' as const, label: '按金额↑' },
  { value: 'amount-desc' as const, label: '按金额↓' },
]

const allCategories = computed(() => {
  const cats = new Map<string, { id: string; name: string }>()
  monthTxns.value.forEach(t => {
    if (t.category_id && t.category_name) cats.set(t.category_id, { id: t.category_id, name: t.category_name })
  })
  return Array.from(cats.values())
})



const monthTxns = computed(() => txnStore.transactions.filter(t => t.date.startsWith(`${year.value}-${String(month.value).padStart(2, '0')}`)))
const monthStats = computed(() => {
  const inc = monthTxns.value.filter(t => t.type === 'income').reduce((s, t) => s + t.amount, 0)
  const exp = monthTxns.value.filter(t => t.type === 'expense').reduce((s, t) => s + t.amount, 0)
  const net = inc - exp
  const savingsRate = inc > 0 ? (net / inc) * 100 : 0
  const necessaryExpenseRatio = monthOverview.value?.necessary_expense_ratio_month ?? 0
  return { income: inc, expense: exp, net, savingsRate, necessaryExpenseRatio }
})

const monthOverview = ref<{ savings_rate?: number; necessary_expense_ratio?: number; necessary_expense_ratio_month?: number } | null>(null)

function applySortAndFilter(items: any[]) {
  let result = [...items]
  if (filterCatId.value === '__refund__') {
    result = result.filter(t => t.type === 'expense' && t.amount < 0)
  } else if (filterCatId.value) {
    result = result.filter(t => t.category_id === filterCatId.value)
  }
  if (filterAccId.value) {
    result = result.filter(t => t.account_id === filterAccId.value)
  }
  if (sortBy.value === 'date') {
    result.sort((a, b) => a.date.localeCompare(b.date))
  } else if (sortBy.value === 'amount-asc') {
    result.sort((a, b) => a.amount - b.amount)
  } else if (sortBy.value === 'amount-desc') {
    result.sort((a, b) => b.amount - a.amount)
  }
  return result
}

// 金额显示（负负得正）：
//   普通消费 amount>0 → -¥60；退款 amount<0 → +¥60（钱回来）
//   普通收入 amount>0 → +¥60；收入冲减 amount<0 → -¥60
//   转账 → ¥xx（无符号）
function amountText(amount: number, type: string): string {
  const num = Math.abs(amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (type === 'expense') return `${amount >= 0 ? '-' : '+'}${sym.value}${num}`
  if (type === 'income') return `${amount >= 0 ? '+' : '-'}${sym.value}${num}`
  return `${sym.value}${num}`
}

// 颜色：显示为正数（钱进）→ 红；显示为负数（钱出）→ 绿；转账 → 蓝
// 与 amountText 的显示符号一致（普通消费绿、退款红、普通收入红、收入冲减绿）
function signColorClass(amount: number, type: string): string {
  if (type === 'transfer') return 'text-transfer-color'
  // expense: amount>=0 显示负(绿)；amount<0 显示正(红)
  // income:  amount>=0 显示正(红)；amount<0 显示负(绿)
  const positiveDisplay = (type === 'expense') ? (amount < 0) : (amount >= 0)
  return positiveDisplay ? 'text-income-color' : 'text-expense-color'
}

const sections = computed(() => {
  const build = (type: 'expense' | 'income' | 'transfer') => {
    const items = applySortAndFilter(monthTxns.value.filter(t => t.type === type))
    return { items, amount: items.reduce((s, t) => s + t.amount, 0) }
  }
  const expense = build('expense')
  const income = build('income')
  const transfer = build('transfer')
  return [
    { type: 'expense', label: '支出', color: 'bg-expense-color', amountClass: 'text-expense-color', ...expense },
    { type: 'income', label: '收入', color: 'bg-income-color', amountClass: 'text-income-color', ...income },
    { type: 'transfer', label: '转账', color: 'bg-transfer-color', amountClass: 'text-transfer-color', ...transfer },
  ]
})

const showBalances = ref(false)
const balancesAsOf = ref<{ account_id: string; account_name: string; initial_balance: number; income: number; expense: number; transfer_in: number; transfer_out: number; balance: number }[]>([])
function fmtAmount(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

interface CategoryStat {
  category_id: string; category_name: string; category_color: string;
  total: number; count: number; positive_total: number; negative_total: number;
}

function aggregateSummary(items: CategoryStat[]) {
  let positive = 0, negative = 0
  for (const it of items) { positive += it.positive_total || 0; negative += it.negative_total || 0 }
  return { positive, negative, total: positive - negative }
}

function buildIncomeDoughnut(items: CategoryStat[]) {
  const labels = items.map(c => c.category_name)
  const colors = items.map(c => c.category_color || '#9B9B9B')
  const data = items.map(c => c.positive_total || 0)
  return { labels, datasets: [{ data, backgroundColor: colors }] }
}

function buildExpenseDoughnut(items: CategoryStat[]) {
  //净额支出 = 正支出 - 退款（后端 negative_total 已是绝对值，case((amount<0, -amount))）；过滤净额 ≤0（避免饼图出 0 值或全额退款脏数据）
  const filtered = items.filter(c => (c.positive_total || 0) - (c.negative_total || 0) > 0)
  const labels = filtered.map(c => c.category_name)
  const colors = filtered.map(c => c.category_color || '#9B9B9B')
  const data = filtered.map(c => (c.positive_total || 0) - (c.negative_total || 0))
  return { labels, datasets: [{ data, backgroundColor: colors }] }
}
async function loadBalances() {
  try {
    const res = await api.get('/accounts/balances-as-of', { params: { year: year.value, month: month.value } })
    balancesAsOf.value = res.data
  } catch (e) { console.error(e) }
}

async function loadMonth() { await txnStore.fetchTransactions({ year: year.value, month: month.value }); await loadMonthStats(); await loadBalances() }

async function loadMonthStats() {
  try {
    const [expCatRes, incCatRes, dailyRes, overviewRes] = await Promise.all([
      api.get('/statistics/by-category', { params: { type_filter: 'expense', year: year.value, month: month.value } }),
      api.get('/statistics/by-category', { params: { type_filter: 'income', year: year.value, month: month.value } }),
      api.get('/statistics/daily-spending', { params: { year: year.value, month: month.value } }),
      api.get('/statistics/overview', { params: { year: year.value, month: month.value } })
    ])
    expenseCategoryData.value = buildExpenseDoughnut(expCatRes.data)
    incomeCategoryData.value = buildIncomeDoughnut(incCatRes.data)
    expenseSummary.value = aggregateSummary(expCatRes.data)
    incomeSummary.value = aggregateSummary(incCatRes.data)
    dailySpendingData.value = {
      labels: dailyRes.data.map((d: { date: string }) => d.date.slice(-2)),
      datasets: [{ label: '支出', data: dailyRes.data.map((d: { expense: number }) => d.expense), borderColor: '#4CAF50', backgroundColor: 'rgba(76, 175, 80, 0.2)', tension: 0.4, fill: true }]
    }
    monthOverview.value = overviewRes.data
  } catch (e) { console.error(e) }
}

function resetForm() { editId.value = null; form.value = { type: 'expense', date: dayjs(`${year.value}-${month.value}-01`).format('YYYY-MM-DD'), amount: 0, account_id: '', dest_account_id: '', category_id: '', description: '' } }
function editTxn(txn: any) { editId.value = txn.id; form.value = { type: txn.type as 'income' | 'expense' | 'transfer', date: txn.date, amount: txn.amount, account_id: txn.account_id, dest_account_id: txn.dest_account_id || '', category_id: txn.category_id || '', description: txn.description }; showModal.value = true }
async function onImported() {
  showImportModal.value = false
  show('导入完成', 'success')
  await loadMonth()
}
async function saveTxn() {
  try {
    if (editId.value) await txnStore.updateTransaction(editId.value, form.value); else await txnStore.createTransaction(form.value)
    showModal.value = false; show('保存成功', 'success'); await loadMonth()
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}
async function removeTxn(id: string) { if (confirm('确定删除？')) { await txnStore.deleteTransaction(id); show('已删除', 'success') } }

watch([year, month], () => { loadMonthStats() })

onMounted(async () => {
  await Promise.all([accStore.fetchAccounts(), catStore.fetchCategories(), loadMonth()])
})
</script>
