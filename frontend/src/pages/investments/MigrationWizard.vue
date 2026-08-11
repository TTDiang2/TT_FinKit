<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[60] flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="emit('close')"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 flex flex-col modal-in" style="max-height:85vh">
        <!-- header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border-default shrink-0">
          <div>
            <h3 class="font-semibold text-md">补录投资记录</h3>
            <p class="text-xs text-text-muted mt-0.5">{{ investment.name }} — 输入历史投入金额，自动按 iFinD 历史净值反推份额</p>
          </div>
          <button @click="emit('close')" class="text-text-muted hover:text-text-primary text-2xl leading-none">×</button>
        </div>

        <!-- body -->
        <div class="flex-1 overflow-auto px-5 py-4">
          <!-- 基金代码 -->
          <div v-if="!investment.symbol" class="mb-4">
            <label class="block text-sm font-medium mb-1">基金代码 <span class="text-expense-color">*</span></label>
            <input v-model="symbol" placeholder="6 位数字，如 000217" class="w-full px-3 py-2 border border-border-default rounded-md text-sm font-mono" />
            <p class="text-xs text-text-muted mt-1">iFinD 用此代码拉历史单位净值（场外开放式基金）</p>
          </div>
          <div v-else class="mb-4 text-sm text-text-secondary">
            基金代码：<b class="font-mono">{{ investment.symbol }}</b>
          </div>

          <!-- 投资记录输入 -->
          <label class="block text-sm font-medium mb-2">投资记录（何时投了多少）</label>
          <div class="border border-border-default rounded-md overflow-hidden mb-2">
            <table class="w-full text-sm">
              <thead class="bg-bg-tertiary">
                <tr class="text-left text-text-secondary">
                  <th class="px-3 py-2 w-44">投资日期</th>
                  <th class="px-3 py-2 text-right">投入金额（元）</th>
                  <th class="px-2 py-2 w-10"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in rows" :key="i" class="border-t border-border-default">
                  <td class="px-3 py-1.5"><input type="date" v-model="row.date" class="w-full px-2 py-1 border border-border-default rounded text-sm" /></td>
                  <td class="px-3 py-1.5"><input type="number" step="0.01" v-model.number="row.amount" class="w-full px-2 py-1 border border-border-default rounded text-sm text-right font-mono" placeholder="0.00" /></td>
                  <td class="px-2 py-1.5 text-center"><button @click="removeRow(i)" :disabled="rows.length === 1" class="text-text-muted hover:text-expense-color disabled:opacity-30">✕</button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <button @click="addRow" class="text-sm text-accent-primary hover:underline">+ 添加一行</button>

          <!-- 预览结果 -->
          <div v-if="preview" class="mt-5">
            <h4 class="text-sm font-medium mb-2 flex items-center gap-2">
              预览结果（反推份额）
              <span v-if="preview.results.length" class="text-xs text-text-muted font-normal">
                共 {{ preview.results.length }} 条，其中 {{ validResults.length }} 条可导入
              </span>
            </h4>
            <div class="border border-border-default rounded-md overflow-hidden bg-bg-secondary">
              <table class="w-full text-sm">
                <thead class="bg-bg-tertiary">
                  <tr class="text-left text-text-secondary">
                    <th class="px-3 py-2">日期</th>
                    <th class="px-3 py-2 text-right">金额</th>
                    <th class="px-3 py-2 text-right">单位净值</th>
                    <th class="px-3 py-2 text-right">反推份额</th>
                    <th class="px-3 py-2 text-center">状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(r, i) in preview.results" :key="i" class="border-t border-border-default" :class="r.status !== 'ok' ? 'bg-red-50' : ''">
                    <td class="px-3 py-1.5 whitespace-nowrap">{{ r.date }}</td>
                    <td class="px-3 py-1.5 text-right font-mono">{{ r.amount.toFixed(2) }}</td>
                    <td class="px-3 py-1.5 text-right font-mono">{{ r.nav != null ? r.nav.toFixed(4) : '—' }}</td>
                    <td class="px-3 py-1.5 text-right font-mono">{{ r.shares != null ? r.shares.toFixed(2) : '—' }}</td>
                    <td class="px-3 py-1.5 text-center whitespace-nowrap">
                      <span v-if="r.status === 'ok'" class="text-income-color">✓ 可导入</span>
                      <span v-else-if="r.status === 'no_nav'" class="text-warning-color">该日无净值</span>
                      <span v-else class="text-expense-color">无效</span>
                    </td>
                  </tr>
                </tbody>
                <tfoot v-if="validResults.length > 0">
                  <tr class="border-t-2 border-border-default bg-bg-tertiary font-medium">
                    <td class="px-3 py-2">合计</td>
                    <td class="px-3 py-2 text-right font-mono">{{ totalAmount.toFixed(2) }}</td>
                    <td class="px-3 py-2 text-right text-text-muted text-xs">均 {{ avgCost.toFixed(4) }}</td>
                    <td class="px-3 py-2 text-right font-mono">{{ totalShares.toFixed(2) }}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <p v-if="validResults.length < preview.results.length" class="text-xs text-warning-color mt-2">
              ⚠ {{ preview.results.length - validResults.length }} 条无净值（投资日早于基金成立日或非交易日），入库时将跳过
            </p>
          </div>
        </div>

        <!-- footer -->
        <div class="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-default bg-bg-secondary rounded-b-lg shrink-0">
          <button @click="emit('close')" class="px-3 py-1.5 text-sm border border-border-default rounded-md hover:bg-bg-tertiary">取消</button>
          <button @click="doPreview" :disabled="loading || !canPreview"
                  class="px-4 py-1.5 text-sm bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed">
            {{ loading ? '反推中...' : (preview ? '重新预览' : '预览（反推份额）') }}
          </button>
          <button v-if="preview && validResults.length > 0" @click="doCommit" :disabled="committing"
                  class="px-4 py-1.5 text-sm bg-income-color text-white rounded-md hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed">
            {{ committing ? '入库中...' : `确认入库 ${validResults.length} 条` }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { Investment } from '@/types'

const api = useApi()
const { show } = useToast()
const props = defineProps<{ investment: Investment }>()
const emit = defineEmits<{ close: []; done: [] }>()

interface MigrationRow { date: string; amount: number }
interface MigrationResult {
  date: string
  amount: number
  nav: number | null
  shares: number | null
  status: string  // ok / no_nav / invalid
}

const symbol = ref(props.investment.symbol || '')
const rows = reactive<MigrationRow[]>([{ date: '', amount: 0 }])
const preview = ref<{ results: MigrationResult[]; preview: boolean } | null>(null)
const loading = ref(false)
const committing = ref(false)

function addRow() { rows.push({ date: '', amount: 0 }) }
function removeRow(i: number) { if (rows.length > 1) rows.splice(i, 1) }

const validRows = computed(() => rows.filter(r => r.date && r.amount > 0))
const canPreview = computed(() =>
  validRows.value.length > 0 && !!(props.investment.symbol || symbol.value.trim())
)
const validResults = computed(() => preview.value?.results.filter(r => r.status === 'ok') ?? [])
const totalAmount = computed(() => validResults.value.reduce((s, r) => s + r.amount, 0))
const totalShares = computed(() => validResults.value.reduce((s, r) => s + (r.shares ?? 0), 0))
const avgCost = computed(() => (totalShares.value > 0 ? totalAmount.value / totalShares.value : 0))

async function doPreview() {
  if (!canPreview.value) return
  loading.value = true
  preview.value = null
  try {
    const res = await api.post(`/investments/${props.investment.id}/migrate-entry`, {
      entries: validRows.value.map(r => ({ date: r.date, amount: r.amount })),
      commit: false,
      symbol: symbol.value.trim(),
    })
    preview.value = res.data
    if (res.data.results.length === 0) {
      show('没有有效的投资记录', 'warning')
    }
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      || (e as Error).message || '预览失败'
    show(msg, 'error')
  } finally {
    loading.value = false
  }
}

async function doCommit() {
  if (validResults.value.length === 0) return
  committing.value = true
  try {
    const res = await api.post(`/investments/${props.investment.id}/migrate-entry`, {
      entries: validResults.value.map(r => ({
        date: r.date, amount: r.amount, nav: r.nav, shares: r.shares,
      })),
      commit: true,
      symbol: symbol.value.trim(),
    })
    show(`成功入库 ${res.data.committed} 条投资记录`, 'success')
    emit('done')
    emit('close')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
      || (e as Error).message || '入库失败'
    show(msg, 'error')
  } finally {
    committing.value = false
  }
}
</script>
