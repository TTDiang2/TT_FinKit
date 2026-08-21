<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="emit('close')"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-5xl mx-4 modal-in flex flex-col" style="max-height:85vh">
        <!-- header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-default shrink-0">
          <h3 class="font-semibold text-md">导入交易</h3>
          <button @click="emit('close')" class="text-text-muted hover:text-text-primary transition-colors"><X :size="18" /></button>
        </div>

        <!-- body -->
        <div class="flex-1 overflow-hidden flex flex-col px-5 py-4">
          <!-- step: select -->
          <div v-if="step === 'select'" class="flex-1 flex flex-col items-center justify-center gap-4 py-12">
            <div class="text-text-muted"><FileSpreadsheet :size="48" /></div>
            <p class="text-sm text-text-secondary text-center max-w-md">
              选择由转换脚本生成的 .xlsx 或 .csv 文件。<br />
              解析后会显示预览，可勾选要导入的行。
            </p>
            <label class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover cursor-pointer flex items-center gap-1 text-sm">
              <Upload :size="16" /> 选择文件
              <input type="file" accept=".xlsx,.xls,.csv" class="hidden" @change="onFileChange" />
            </label>
            <p v-if="selectError" class="text-sm text-expense-color">{{ selectError }}</p>
          </div>

          <!-- step: preview -->
          <div v-else-if="step === 'preview'" class="flex-1 flex flex-col overflow-hidden">
            <!-- stats bar -->
            <div class="flex items-center justify-between mb-3 shrink-0">
              <div class="flex items-center gap-4 text-xs">
                <span class="text-text-secondary">共 <b class="text-text-primary">{{ preview!.total }}</b> 条</span>
                <span class="text-expense-color">错误 <b>{{ preview!.error_count }}</b></span>
                <button class="text-warning-color hover:underline" @click="confidenceFilter = 'dup'">疑似重复 <b>{{ preview!.duplicate_count }}</b></button>
                <span class="text-income-color">已选 <b>{{ selectedCount }}</b></span>
              </div>
              <div class="flex items-center gap-2">
                <button @click="selectAllValid" class="text-xs text-text-secondary hover:text-text-primary px-2 py-1 border border-border-default rounded">全选有效</button>
                <button @click="invertSelection" class="text-xs text-text-secondary hover:text-text-primary px-2 py-1 border border-border-default rounded">反选</button>
              </div>
            </div>

            <!-- 置信度筛选 tabs -->
            <div class="flex items-center gap-1 mb-3 shrink-0 text-xs">
              <span class="text-text-secondary mr-1">筛选：</span>
              <button v-for="f in confidenceFilters" :key="f.value" @click="confidenceFilter = f.value"
                :class="['px-2.5 py-1 rounded transition-colors', confidenceFilter === f.value ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-border-default']">
                {{ f.label }} <span class="opacity-70">({{ confidenceCount(f.value) }})</span>
              </button>
            </div>

            <!-- batch operations bar -->
            <div v-if="selectedCount > 0" class="mb-3 p-2 bg-bg-tertiary rounded-md border border-border-default">
              <div class="flex items-center justify-between text-xs">
                <span class="text-text-secondary">已选 {{ selectedCount }} 条</span>
                <div class="flex items-center gap-2">
                  <div class="flex items-center gap-1">
                    <span class="text-text-secondary">批量设方向：</span>
                    <select v-model="batchDirection" class="text-xs border border-border-default rounded px-1 py-0.5">
                      <option value="">选择方向</option>
                      <option value="income">收入</option>
                      <option value="expense">支出</option>
                      <option value="transfer">转账</option>
                    </select>
                    <button @click="applyBatchDirection" class="text-xs px-2 py-0.5 bg-accent-primary text-white rounded hover:bg-accent-hover">应用</button>
                  </div>
                  <div class="flex items-center gap-1">
                    <span class="text-text-secondary">批量设分类：</span>
                    <select v-model="batchCategory" :disabled="!canBatchCategory" class="text-xs border border-border-default rounded px-1 py-0.5">
                      <option value="">选择分类</option>
                      <option v-for="cat in batchCategories" :value="cat" :key="cat">{{ cat }}</option>
                    </select>
                    <button @click="applyBatchCategory" :disabled="!canBatchCategory" class="text-xs px-2 py-0.5 bg-accent-primary text-white rounded hover:bg-accent-hover disabled:opacity-40">应用</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- table -->
            <div class="flex-1 overflow-auto border border-border-default rounded-md">
              <table class="w-full text-xs">
                <thead class="bg-bg-tertiary sticky top-0 z-10">
                  <tr class="text-left text-text-secondary">
                    <th class="px-2 py-2 w-8"><input type="checkbox" :checked="allValidSelected" @change="toggleAll" /></th>
                    <th class="px-2 py-2">日期</th>
                    <th class="px-2 py-2">方向</th>
                    <th class="px-2 py-2 text-right">金额</th>
                    <th class="px-2 py-2">账户</th>
                    <th class="px-2 py-2">分类</th>
                    <th class="px-2 py-2">置信度</th>
                    <th class="px-2 py-2">交易地点/附言</th>
                    <th class="px-2 py-2">对方户名</th>
                    <th class="px-2 py-2">状态</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="r in filteredRows" :key="r.row_index">
                    <tr :class="rowClass(r)" class="border-t border-border-default">
                    <td class="px-2 py-1.5">
                      <input type="checkbox" :checked="selected[r.row_index]" :disabled="!!r.error"
                             @change="toggleRow(r.row_index)" />
                    </td>
                    <td class="px-2 py-1.5 whitespace-nowrap">{{ r.date }}</td>
                    <td class="px-2 py-1.5">
                      <select
                        v-model="rowEdits[r.row_index].direction"
                        @change="onDirectionChange(r.row_index)"
                        :disabled="!!r.error"
                        class="text-xs border border-border-default rounded px-1 py-0.5 w-full"
                      >
                        <option value="income">收入</option>
                        <option value="expense">支出</option>
                        <option value="transfer">转账</option>
                      </select>
                    </td>
                    <td class="px-2 py-1.5 text-right whitespace-nowrap font-mono" :class="amountClass(effectiveDirection(r), r.amount)">
                      {{ amountText(effectiveDirection(r), r.amount) }}
                    </td>
                    <td class="px-2 py-1.5 whitespace-nowrap">
                      <select
                        v-if="effectiveDirection(r) === 'transfer'"
                        v-model="rowEdits[r.row_index].account"
                        :disabled="!!r.error"
                        class="text-xs border border-border-default rounded px-1 py-0.5 w-full"
                        :title="r.account"
                      >
                        <option v-for="acc in preview?.accounts" :value="acc" :key="acc">{{ acc }}</option>
                      </select>
                      <span v-else class="text-text-secondary">{{ r.account }}</span>
                    </td>
                    <td class="px-2 py-1.5 whitespace-nowrap">
                      <select
                        v-if="effectiveDirection(r) === 'transfer'"
                        v-model="rowEdits[r.row_index].dest_account"
                        :disabled="!!r.error"
                        class="text-xs border border-border-default rounded px-1 py-0.5 w-full"
                      >
                        <option value="">选择对方账户</option>
                        <option v-for="acc in preview?.accounts" :value="acc" :key="acc">{{ acc }}</option>
                      </select>
                      <select
                        v-else
                        v-model="rowEdits[r.row_index].category"
                        :disabled="!!r.error || effectiveDirection(r) === 'transfer'"
                        class="text-xs border border-border-default rounded px-1 py-0.5 w-full"
                      >
                        <option value="">待补</option>
                        <option v-for="cat in effectiveDirection(r) === 'expense' ? preview?.expense_categories : preview?.income_categories" 
                                :value="cat" 
                                :key="cat">
                          {{ cat }}
                        </option>
                      </select>
                    </td>
                    <td class="px-2 py-1.5 whitespace-nowrap">
                      <span :class="confidenceBadgeClass(r.confidence)">{{ confidenceLabel(r.confidence) }}</span>
                    </td>
                    <td class="px-2 py-1.5 max-w-[220px] truncate text-text-secondary" :title="r.location">{{ r.location || r.description }}</td>
                    <td class="px-2 py-1.5 max-w-[140px] truncate text-text-muted" :title="r.counterparty">{{ r.counterparty }}</td>
                    <td class="px-2 py-1.5 whitespace-nowrap">
                      <span v-if="r.error" class="text-expense-color">{{ r.error }}</span>
                      <button v-else-if="r.is_duplicate" @click="toggleDup(r.row_index)"
                              class="text-warning-color underline decoration-dotted underline-offset-2 hover:font-semibold">
                        疑似重复{{ dupOpen[r.row_index] ? ' ▾' : ' ▸' }}
                      </button>
                      <span v-else-if="!rowEdits[r.row_index]?.category && rowEdits[r.row_index]?.direction !== 'transfer'" class="text-warning-color">待补分类</span>
                      <span v-else-if="rowEdits[r.row_index]?.direction === 'transfer' && !rowEdits[r.row_index]?.dest_account" class="text-warning-color">待填对方账户</span>
                      <span v-else class="text-income-color">可导入</span>
                    </td>
                  </tr>
                    <tr v-if="dupOpen[r.row_index]" class="bg-yellow-50/60 border-t border-border-default">
                      <td colspan="10" class="px-4 py-2">
                        <div class="text-xs text-text-secondary mb-1">可能与以下现有记录重复：</div>
                        <div v-for="(d, i) in r.duplicate_with" :key="i" class="text-xs font-mono text-text-secondary py-0.5">
                          {{ d.date }} {{ dirLabel(d.type) }} {{ formatMoney(d.amount) }} · {{ d.account }}<span v-if="d.description"> · {{ d.description }}</span>
                        </div>
                        <div v-if="!r.duplicate_with?.length" class="text-xs text-text-muted">无候选详情</div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </div>

          <!-- step: result -->
          <div v-else class="flex-1 flex flex-col items-center justify-center gap-4 py-12">
            <CheckCircle2 :size="48" :class="result!.skipped > 0 ? 'text-warning-color' : 'text-income-color'" />
            <div class="text-center">
              <p class="text-lg font-semibold">导入完成</p>
              <p class="text-sm text-text-secondary mt-1">
                新增 <b class="text-income-color">{{ result!.inserted }}</b> 条，
                跳过 <b>{{ result!.skipped }}</b> 条
              </p>
            </div>
            <div v-if="result!.errors.length" class="w-full max-w-md max-h-32 overflow-auto bg-bg-tertiary rounded-md p-3 text-xs text-text-secondary border border-border-default">
              <div v-for="(e, i) in result!.errors.slice(0, 20)" :key="i" class="font-mono">{{ e }}</div>
              <div v-if="result!.errors.length > 20" class="text-text-muted mt-1">...共 {{ result!.errors.length }} 条</div>
            </div>
          </div>
        </div>

        <!-- footer -->
        <div class="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-default bg-bg-secondary rounded-b-lg shrink-0">
          <button v-if="step === 'preview'" @click="resetToSelect" class="px-3 py-1.5 text-sm border border-border-default rounded-md hover:bg-bg-tertiary">重新选择</button>
          <button @click="emit('close')" class="px-3 py-1.5 text-sm border border-border-default rounded-md hover:bg-bg-tertiary">{{ step === 'result' ? '关闭' : '取消' }}</button>
          <button v-if="step === 'preview'" @click="doImport" :disabled="selectedCount === 0 || importing"
                  class="px-4 py-1.5 text-sm bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed">
            {{ importing ? '导入中...' : `导入选中的 ${selectedCount} 条` }}
          </button>
          <button v-if="step === 'result'" @click="emit('imported'); emit('close')"
                  class="px-4 py-1.5 text-sm bg-accent-primary text-white rounded-md hover:bg-accent-hover">完成</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { Upload, FileSpreadsheet, CheckCircle2, X } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/stores/settings'

const api = useApi()
const { show } = useToast()
const settingsStore = useSettingsStore()
const emit = defineEmits<{ (e: 'close'): void; (e: 'imported'): void }>()

interface PreviewRow {
  row_index: number
  date: string
  direction: 'income' | 'expense' | 'transfer'
  amount: number
  account: string
  dest_account: string
  category: string
  tags: string
  description: string
  remark: string
  source_memo: string
  counterparty: string
  location: string
  confidence: string
  error: string
  is_duplicate: boolean
  duplicate_with: Array<{
    date: string
    amount: number
    type: string
    account: string
    description: string
    location: string
  }>
}
interface PreviewResponse {
  rows: PreviewRow[]
  total: number
  error_count: number
  duplicate_count: number
  accounts: string[]
  expense_categories: string[]
  income_categories: string[]
}
interface ImportResult {
  inserted: number
  skipped: number
  errors: string[]
}

const step = ref<'select' | 'preview' | 'result'>('select')
const selectError = ref('')
const preview = ref<PreviewResponse | null>(null)
const result = ref<ImportResult | null>(null)
const selected = reactive<Record<number, boolean>>({})
const importing = ref(false)
const confidenceFilter = ref<'all' | 'high' | 'medium' | 'none' | 'dup'>('all')
const confidenceFilters = [
  { value: 'all' as const, label: '全部' },
  { value: 'high' as const, label: '高置信度' },
  { value: 'medium' as const, label: '需检查' },
  { value: 'none' as const, label: '未识别' },
  { value: 'dup' as const, label: '疑似重复' },
]
const dupOpen = reactive<Record<number, boolean>>({})
const rowEdits = reactive<Record<number, { direction: string; category: string; dest_account: string; account: string }>>({})
function effectiveDirection(r: PreviewRow): string {
  return rowEdits[r.row_index]?.direction || r.direction
}
const batchDirection = ref('')
const batchCategory = ref('')
const batchCategories = computed(() => {
  if (!preview.value) return []
  const selectedRows = preview.value.rows.filter(r => !r.error && selected[r.row_index])
  if (selectedRows.length === 0) return []
  
  const dirs = selectedRows.map(r => effectiveDirection(r))
  if (dirs.every(d => d === dirs[0])) {
    return dirs[0] === 'expense' ? preview.value.expense_categories : 
           dirs[0] === 'income' ? preview.value.income_categories : []
  }
  return []
})
const canBatchCategory = computed(() => {
  if (!preview.value) return false
  const selectedRows = preview.value.rows.filter(r => !r.error && selected[r.row_index])
  if (selectedRows.length === 0) return false
  
  const dirs = selectedRows.map(r => effectiveDirection(r))
  return dirs.every(d => d === dirs[0])
})

const selectedRows = computed(() => {
  if (!preview.value) return []
  return preview.value.rows.filter(r => !r.error && selected[r.row_index])
})
const selectedCount = computed(() => selectedRows.value.length)
const allValidSelected = computed(() => {
  if (!preview.value) return false
  const valid = preview.value.rows.filter(r => !r.error)
  return valid.length > 0 && valid.every(r => selected[r.row_index])
})

// 按置信度筛选显示
const filteredRows = computed(() => {
  if (!preview.value) return []
  if (confidenceFilter.value === 'all') return preview.value.rows
  return preview.value.rows.filter(r => {
    if (confidenceFilter.value === 'dup') return r.is_duplicate
    if (confidenceFilter.value === 'high') return r.confidence === 'high'
    if (confidenceFilter.value === 'medium') return r.confidence === 'medium' || r.confidence === 'low'
    if (confidenceFilter.value === 'none') return r.confidence === 'none' || !r.confidence
    return true
  })
})

function confidenceCount(filter: string): number {
  if (!preview.value) return 0
  if (filter === 'all') return preview.value.rows.length
  return preview.value.rows.filter(r => {
    if (filter === 'dup') return r.is_duplicate
    if (filter === 'high') return r.confidence === 'high'
    if (filter === 'medium') return r.confidence === 'medium' || r.confidence === 'low'
    if (filter === 'none') return r.confidence === 'none' || !r.confidence
    return true
  }).length
}

function confidenceLabel(c: string): string {
  if (c === 'high') return '高'
  if (c === 'medium') return '中'
  if (c === 'low') return '低'
  if (c === 'none') return '未识别'
  return '-'
}

function confidenceBadgeClass(c: string): string {
  if (c === 'high') return 'px-1.5 py-0.5 rounded text-xs bg-green-100 text-green-800'
  if (c === 'medium' || c === 'low') return 'px-1.5 py-0.5 rounded text-xs bg-yellow-100 text-yellow-800'
  if (c === 'none') return 'px-1.5 py-0.5 rounded text-xs bg-orange-100 text-orange-800'
  return 'px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600'
}

function rowClass(r: PreviewRow): string {
  if (r.error) return 'bg-red-50'
  if (r.is_duplicate) return 'bg-yellow-50'
  return ''
}
function dirLabel(d: string): string {
  return d === 'income' ? '收入' : d === 'expense' ? '支出' : '转账'
}
function dirBadgeClass(d: string): string {
  return d === 'income' ? 'bg-success-bg text-income-color'
    : d === 'expense' ? 'bg-error-bg text-expense-color'
    : 'bg-info-bg text-transfer-color'
}
function amountClass(d: string, amount?: number): string {
  // 颜色仅由方向语义决定：收入=钱进(红)；支出=钱出(绿)，负数支出(退款)=钱回(红)；转账=蓝
  if (d === 'transfer') return 'text-transfer-color'
  const a = amount ?? 0
  if (d === 'income') return 'text-income-color'
  return a < 0 ? 'text-income-color' : 'text-expense-color'
}
function onDirectionChange(rowIndex: number) {
  rowEdits[rowIndex].category = ''
  const pair = defaultTransferPair(rowEdits[rowIndex].account || preview.value?.rows.find(r => r.row_index === rowIndex)?.account || '')
  rowEdits[rowIndex].account = pair[0]
  rowEdits[rowIndex].dest_account = pair[1]
}
// 转账默认方向：工资账户 → 消费账户（与后端 _default_transfer_pair 一致）
function defaultTransferPair(account: string): [string, string] {
  const accs = preview.value?.accounts || []
  const others = accs.filter(a => a !== account)
  if (!others.length) return [account, '']
  const salary = accs.find(a => a.includes('工资'))
  const consumer = accs.find(a => a.includes('消费'))
  if (account.includes('工资')) return [account, consumer || others[0]]
  if (account.includes('消费') && salary) return [salary, account]
  return [account, others[0]]
}
function applyBatchDirection() {
  if (!batchDirection.value) return
  for (const r of preview.value!.rows) {
    if (!r.error && selected[r.row_index]) {
      rowEdits[r.row_index].direction = batchDirection.value
      rowEdits[r.row_index].category = ''
      const pair = defaultTransferPair(rowEdits[r.row_index].account || r.account)
      rowEdits[r.row_index].account = pair[0]
      rowEdits[r.row_index].dest_account = pair[1]
    }
  }
  batchDirection.value = ''
}
function applyBatchCategory() {
  if (!batchCategory.value || !canBatchCategory.value) return
  for (const r of preview.value!.rows) {
    if (!r.error && selected[r.row_index]) {
      rowEdits[r.row_index].category = batchCategory.value
    }
  }
  batchCategory.value = ''
}
function toggleDup(idx: number) {
  dupOpen[idx] = !dupOpen[idx]
}
function formatMoney(n: number): string {
  return `${settingsStore.settings.currency_symbol}${n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
// 金额显示：收入恒显示 +（钱进）；支出正数显示 -（钱出）、负数支出（退款）显示 +（钱回）；转账无符号。
// 切换方向不改变数字：退款改判收入时仍显示 +¥xx（用户 2026-08 要求）
function amountText(d: string, amount: number): string {
  const sym = settingsStore.settings.currency_symbol
  const num = Math.abs(amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (d === 'income') return `+${sym}${num}`
  if (d === 'expense') return `${amount >= 0 ? '-' : '+'}${sym}${num}`
  return `${sym}${num}`
}

async function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  selectError.value = ''
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await api.post<PreviewResponse>('/transactions/parse-import', fd)
    preview.value = res.data
    for (const r of res.data.rows) {
      // 疑似重复行默认仍勾选，由用户决定；确认导入时再提示
      selected[r.row_index] = !r.error
      rowEdits[r.row_index] = {
        direction: r.direction,
        category: r.category || '',
        dest_account: r.direction === 'transfer' ? r.dest_account || '' : '',
        account: r.account,
      }
      if (r.direction === 'transfer' && !rowEdits[r.row_index].dest_account) {
        const pair = defaultTransferPair(r.account)
        rowEdits[r.row_index].account = pair[0]
        rowEdits[r.row_index].dest_account = pair[1]
      }
    }
    step.value = 'preview'
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
      || '解析失败，请检查文件格式'
    selectError.value = msg
    show(msg, 'error')
  }
  target.value = ''
}

function toggleRow(idx: number) {
  selected[idx] = !selected[idx]
}
function toggleAll() {
  if (!preview.value) return
  const next = !allValidSelected.value
  for (const r of preview.value.rows) {
    if (!r.error) selected[r.row_index] = next
  }
}
function selectAllValid() {
  if (!preview.value) return
  for (const r of preview.value.rows) {
    if (!r.error) selected[r.row_index] = true
  }
}
function invertSelection() {
  if (!preview.value) return
  for (const r of preview.value.rows) {
    if (!r.error) selected[r.row_index] = !selected[r.row_index]
  }
}

function resetToSelect() {
  step.value = 'select'
  preview.value = null
  result.value = null
  for (const k of Object.keys(selected)) delete selected[Number(k)]
  for (const k of Object.keys(dupOpen)) delete dupOpen[Number(k)]
  selectError.value = ''
}

async function doImport() {
  if (!preview.value || selectedCount.value === 0) return
  const dupSelected = selectedRows.value.filter(r => r.is_duplicate).length
  if (dupSelected > 0) {
    const ok = confirm(
      `有 ${dupSelected} 条与现有记录疑似重复（同日、同账户、同金额、同类型）。` +
      `可能是正常的同额交易，也可能是重复导入。确认仍然导入吗？`
    )
    if (!ok) return
  }
  importing.value = true
  try {
        const payload = {
          rows: selectedRows.value.map(r => {
            const edit = rowEdits[r.row_index] || { direction: r.direction, category: r.category, dest_account: r.dest_account, account: r.account }
            return {
              date: r.date,
              direction: edit.direction,
              amount: r.amount,
              account: edit.direction === 'transfer' ? (edit.account || r.account) : r.account,
              dest_account: edit.direction === 'transfer' ? (edit.dest_account || r.dest_account || '') : '',
              category: edit.direction === 'transfer' ? '' : edit.category,
              tags: r.tags,
              description: r.description,
              remark: r.remark,
              location: r.location || '',
            }
          })
        }
    const res = await api.post<ImportResult>('/transactions/import', payload)
    result.value = res.data
    step.value = 'result'
  } catch (err: unknown) {
    const msg = (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || '导入失败'
    show(msg, 'error')
  } finally {
    importing.value = false
  }
}
</script>
