<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <div class="flex items-center gap-4">
        <button @click="showImportModal = true" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary flex items-center gap-1 text-sm">
          <Upload :size="16" /> 导入
        </button>
        <select v-model="selectedYearMonth" @change="onMonthChange" class="px-3 py-2 border border-border-default rounded-md text-sm font-bold">
          <option v-for="opt in monthOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
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

    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h4 class="font-semibold mb-3">收入分类</h4>
        <div class="h-44"><Doughnut v-if="incomeCategoryData.labels.length" :data="incomeCategoryData" :options="{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' as const, labels: { boxWidth: 10, font: { size: 11 } } } } }" /></div>
        <div v-if="!incomeCategoryData.labels.length" class="text-center text-text-muted py-6">暂无数据</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h4 class="font-semibold mb-3">支出分类</h4>
        <div class="h-44"><Doughnut v-if="expenseCategoryData.labels.length" :data="expenseCategoryData" :options="{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' as const, labels: { boxWidth: 10, font: { size: 11 } } } } }" /></div>
        <div v-if="!expenseCategoryData.labels.length" class="text-center text-text-muted py-6">暂无数据</div>
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
        <span class="text-sm font-medium" :class="section.amountClass">{{ sym }}{{ section.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
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
            <span class="text-sm font-medium" :class="section.amountClass">{{ section.prefix }}{{ sym }}{{ txn.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span>
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
const selectedYearMonth = ref(`${year.value}/${String(month.value).padStart(2, '0')}`)

const monthOptions = computed(() => {
  const opts: { value: string; label: string }[] = []
  for (let i = -24; i <= 0; i++) {
    const d = now.add(i, 'month')
    opts.push({ value: `${d.year()}/${String(d.month() + 1).padStart(2, '0')}`, label: `${d.year()}年${String(d.month() + 1).padStart(2, '0')}月` })
  }
  return opts
})

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

function onMonthChange() {
  const [y, m] = selectedYearMonth.value.split('/').map(Number)
  year.value = y; month.value = m; loadMonth()
}

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
  if (filterCatId.value) {
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

const sections = computed(() => [
  { type: 'expense', label: '支出', color: 'bg-expense-color', amountClass: 'text-expense-color', prefix: '-', amount: monthStats.value.expense, items: applySortAndFilter(monthTxns.value.filter(t => t.type === 'expense')) },
  { type: 'income', label: '收入', color: 'bg-income-color', amountClass: 'text-income-color', prefix: '+', amount: monthStats.value.income, items: applySortAndFilter(monthTxns.value.filter(t => t.type === 'income')) },
  { type: 'transfer', label: '转账', color: 'bg-transfer-color', amountClass: 'text-transfer-color', prefix: '', amount: monthTxns.value.filter(t => t.type === 'transfer').reduce((s, t) => s + t.amount, 0), items: applySortAndFilter(monthTxns.value.filter(t => t.type === 'transfer')) },
])

async function loadMonth() { await txnStore.fetchTransactions({ year: year.value, month: month.value }); await loadMonthStats() }

async function loadMonthStats() {
  try {
    const [expCatRes, incCatRes, dailyRes, overviewRes] = await Promise.all([
      api.get('/statistics/by-category', { params: { type_filter: 'expense', year: year.value, month: month.value } }),
      api.get('/statistics/by-category', { params: { type_filter: 'income', year: year.value, month: month.value } }),
      api.get('/statistics/daily-spending', { params: { year: year.value, month: month.value } }),
      api.get('/statistics/overview', { params: { year: year.value, month: month.value } })
    ])
    expenseCategoryData.value = {
      labels: expCatRes.data.map((c: { category_name: string }) => c.category_name),
      datasets: [{ data: expCatRes.data.map((c: { total: number }) => c.total), backgroundColor: expCatRes.data.map((c: { category_color: string }) => c.category_color) }]
    }
    incomeCategoryData.value = {
      labels: incCatRes.data.map((c: { category_name: string }) => c.category_name),
      datasets: [{ data: incCatRes.data.map((c: { total: number }) => c.total), backgroundColor: incCatRes.data.map((c: { category_color: string }) => c.category_color) }]
    }
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