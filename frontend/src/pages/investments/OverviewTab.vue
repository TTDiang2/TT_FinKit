<template>
  <div>
    <!-- Toolbar -->
    <div class="flex items-center justify-end gap-2 mb-4">
      <button :disabled="refreshingAll || !activeInvestments.length" @click="refreshAllPrices"
        :class="['px-3 py-2 border border-border-default rounded-md flex items-center gap-1 text-sm', refreshingAll || !activeInvestments.length ? 'text-text-muted' : 'text-text-secondary hover:bg-bg-tertiary']">
        <RefreshCw v-if="!refreshingAll" :size="14" />
        <span>{{ refreshingAll ? '刷新中…' : '刷新所有现价' }}</span>
      </button>
      <button @click="openProductModal()" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover flex items-center gap-1">
        <Plus :size="16" /> 添加投资
      </button>
    </div>

    <!-- Health Panel -->
    <HealthPanel />

    <!-- Investment consistency check -->
    <div v-if="consistency" class="bg-white rounded-lg shadow-sm p-4 mb-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="font-semibold text-sm">投资账户一致性校验</h3>
        <span :class="['text-xs px-2 py-0.5 rounded', consistency.status === 'ok' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800']">
          {{ consistency.status === 'ok' ? '一致' : '有差异' }}
        </span>
      </div>
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
        <div><div class="text-xs text-text-muted">记账 tab 投资账户余额</div><div class="font-medium">{{ sym }}{{ fmt(consistency.total_account_balance) }}</div></div>
        <div><div class="text-xs text-text-muted">投资 tab 总投入</div><div class="font-medium">{{ sym }}{{ fmt(consistency.total_invested) }}</div></div>
        <div><div class="text-xs text-text-muted">当前市值</div><div class="font-medium">{{ sym }}{{ fmt(consistency.total_current) }}</div></div>
        <div><div class="text-xs text-text-muted">闲置现金</div><div class="font-medium" :class="consistency.idle_cash >= 0 ? '' : 'text-expense-color'">{{ sym }}{{ fmt(consistency.idle_cash) }}</div></div>
      </div>
      <div v-if="consistency.idle_cash > 0" class="text-xs text-text-muted mt-1">≈ 券商账户中未投资的现金</div>
      <ul v-if="consistency.warnings.length" class="mt-2 space-y-1">
        <li v-for="(w, i) in consistency.warnings" :key="i" class="text-xs text-expense-color">{{ w }}</li>
      </ul>
    </div>

    <!-- Holdings Table -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden mb-4">
      <div class="p-4 border-b border-border-default flex items-center justify-between">
        <h3 class="font-semibold text-sm">当前持仓 ({{ activeInvestments.length }})</h3>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">名称 / 代码</th>
            <th class="px-3 py-2 font-medium text-right">数量</th>
            <th class="px-3 py-2 font-medium text-right">均价</th>
            <th class="px-3 py-2 font-medium text-right">现价</th>
            <th class="px-3 py-2 font-medium text-right">距成本</th>
            <th class="px-3 py-2 font-medium text-right">市值</th>
            <th class="px-3 py-2 font-medium text-right">盈亏</th>
            <th class="px-3 py-2 font-medium text-right">年化 XIRR</th>
            <th class="px-3 py-2 font-medium text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="inv in activeInvestments" :key="inv.id">
            <tr class="border-t border-border-default hover:bg-bg-secondary cursor-pointer" :title="expandedIds.has(inv.id) ? '点击收起流水' : '点击展开流水'" @click="onRowClick(inv)">
              <td class="px-3 py-2" @click.stop>
                <div class="font-medium cursor-pointer hover:text-accent-primary" @click="openDetail(inv)" title="查看净值曲线与买卖点">{{ inv.name }}</div>
                <div class="text-xs text-text-muted">
                  {{ TYPE_LABELS[inv.investment_type] || inv.investment_type }}
                  <span v-if="inv.symbol"> · {{ inv.exchange }} {{ inv.symbol }}</span>
                  <span v-if="inv.last_price_update"> · 更新于 {{ formatDateShort(inv.last_price_update) }}</span>
                </div>
              </td>
              <td class="px-3 py-2 text-right">{{ inv.quantity }}</td>
              <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(inv.purchase_price) }}</td>
              <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(inv.current_price) }}</td>
              <td class="px-3 py-2 text-right font-medium" :class="costDist(inv) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ costDist(inv) >= 0 ? '+' : '' }}{{ costDist(inv).toFixed(1) }}%</td>
              <td class="px-3 py-2 text-right font-medium">{{ sym }}{{ fmt(inv.total_value) }}</td>
              <td class="px-3 py-2 text-right font-medium" :class="colorClass(inv.profit_loss)">{{ signed(inv.profit_loss) }}</td>
              <td class="px-3 py-2 text-right" :class="colorClassNullable(productMetricMap[inv.id]?.xirr_annualized)">{{ xirrLabel(productMetricMap[inv.id]?.xirr_annualized) }}</td>
              <td class="px-3 py-2 text-center whitespace-nowrap" @click.stop>
                <button @click="openDetail(inv)" title="净值曲线与买卖点" class="text-text-secondary hover:text-accent-primary mr-2"><LineChart :size="14" /></button>
                <button :disabled="refreshingId === inv.id" @click="refreshPrice(inv)" :title="supportsAutoRefresh(inv.exchange) ? '自动刷新现价' : '该市场不支持自动刷新，请手动编辑'" :class="['mr-2', supportsAutoRefresh(inv.exchange) ? 'text-accent-primary hover:text-accent-hover' : 'text-text-muted cursor-not-allowed']">
                  <RefreshCw v-if="refreshingId !== inv.id" :size="14" />
                  <span v-else class="text-xs">…</span>
                </button>
                <button @click="openTxModal(inv)" title="记录流水" class="text-text-secondary hover:text-accent-primary mr-2"><ListPlus :size="14" /></button>
                <button @click="openProductModal(inv)" class="text-text-secondary hover:text-accent-primary mr-2"><Edit2 :size="14" /></button>
                <button @click="removeItem(inv.id)" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
              </td>
            </tr>
            <tr v-if="expandedIds.has(inv.id)" class="bg-bg-secondary">
              <td colspan="9" class="px-4 py-3">
                <div class="text-xs font-medium mb-2 text-text-secondary">流水记录（{{ txMap[inv.id]?.length || 0 }} 条）</div>
                <table class="w-full text-xs">
                  <thead><tr class="text-text-muted"><th class="px-2 py-1 text-left">日期</th><th class="px-2 py-1 text-left">类型</th><th class="px-2 py-1 text-right">数量</th><th class="px-2 py-1 text-right">单价</th><th class="px-2 py-1 text-right">金额</th><th class="px-2 py-1 text-left">备注</th></tr></thead>
                  <tbody>
                    <tr v-for="tx in txMap[inv.id] || []" :key="tx.id" class="border-t border-border-default">
                      <td class="px-2 py-1">{{ tx.event_date }}</td>
                      <td class="px-2 py-1">{{ TX_LABELS[tx.event_type] }}</td>
                      <td class="px-2 py-1 text-right">{{ tx.quantity || '—' }}</td>
                      <td class="px-2 py-1 text-right">{{ sym }}{{ fmt(tx.unit_price) }}</td>
                      <td class="px-2 py-1 text-right">{{ signed(tx.amount) }}</td>
                      <td class="px-2 py-1 text-text-muted">{{ tx.notes }}</td>
                    </tr>
                    <tr v-if="!txMap[inv.id]?.length"><td colspan="6" class="px-2 py-2 text-text-muted text-center">暂无流水</td></tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
          <tr v-if="!activeInvestments.length"><td colspan="9" class="px-4 py-6 text-center text-text-muted">暂无持仓</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Sold positions -->
    <div v-if="soldInvestments.length" class="bg-white rounded-lg shadow-sm overflow-hidden">
      <div class="p-4 border-b border-border-default">
        <h3 class="font-semibold text-sm">已平仓 ({{ soldInvestments.length }})</h3>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr><th class="px-3 py-2 font-medium">名称</th><th class="px-3 py-2 font-medium">类型</th><th class="px-3 py-2 font-medium text-right">盈亏</th><th class="px-3 py-2 font-medium text-center">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="inv in soldInvestments" :key="inv.id" class="border-t border-border-default text-text-muted">
            <td class="px-3 py-2">{{ inv.name }}</td>
            <td class="px-3 py-2">{{ TYPE_LABELS[inv.investment_type] || inv.investment_type }}</td>
            <td class="px-3 py-2 text-right" :class="colorClass(inv.profit_loss)">{{ signed(inv.profit_loss) }}</td>
            <td class="px-3 py-2 text-center"><button @click="removeItem(inv.id)" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Product Add/Edit Modal -->
    <BaseModal v-if="showProductModal" :title="editingProduct ? '编辑投资' : '添加投资'" @close="showProductModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">名称</label><input v-model="productForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如：沪深300ETF" /></div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="productForm.investment_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="stock">股票</option><option value="fund">基金</option><option value="bond">债券</option>
              <option value="crypto">加密货币</option><option value="deposit">存款</option><option value="other">其他</option>
            </select>
          </div>
          <div>
            <label class="block text-sm mb-1">市场</label>
            <select v-model="productForm.exchange" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="">未指定（手动输入价格）</option>
              <option value="SH">沪市A股 / 沪市ETF (SH)</option>
              <option value="SZ">深市A股 / 深市ETF (SZ)</option>
              <option value="HK">港股 (HK)</option>
              <option value="FUND_CN">中国开放式基金</option>
              <option value="US">美股（仅手动输入）</option>
              <option value="CRYPTO">加密货币（仅手动输入）</option>
            </select>
          </div>
        </div>
        <div v-if="productForm.exchange">
          <label class="block text-sm mb-1">代码</label>
          <input v-model="productForm.symbol" class="w-full px-3 py-2 border border-border-default rounded-md" :placeholder="symbolPlaceholder" />
          <div class="text-xs text-text-muted mt-1">{{ symbolHint }}</div>
        </div>
        <div>
          <label class="block text-sm mb-1">底层资产类型</label>
          <select v-model="productForm.underlying_asset_type" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">请选择</option>
            <option v-for="u in UNDERLYING_OPTIONS" :key="u" :value="u">{{ u }}</option>
            <option value="_custom">自定义...</option>
          </select>
        </div>
        <div v-if="productForm.underlying_asset_type === '_custom'">
          <input v-model="productForm.underlying_asset_type_custom" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="输入底层资产类型" />
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-sm mb-1">初始数量</label><input v-model.number="productForm.quantity" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">买入均价</label><input v-model.number="productForm.purchase_price" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">现价</label><input v-model.number="productForm.current_price" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-sm mb-1">买入日期</label><input v-model="productForm.purchase_date" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="yyyy-mm-dd" /></div>
          <div><label class="block text-sm mb-1">卖出日期（可选）</label><input v-model="productForm.sell_date" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="yyyy-mm-dd" /></div>
        </div>
        <div><label class="block text-sm mb-1">备注</label><textarea v-model="productForm.notes" class="w-full px-3 py-2 border border-border-default rounded-md" rows="2" placeholder="可选"></textarea></div>
      </div>
      <template #footer>
        <button @click="showProductModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="saveProduct" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">{{ editingProduct ? '更新' : '添加' }}</button>
      </template>
    </BaseModal>

    <!-- Transaction Add/Edit Modal -->
    <BaseModal v-if="showTxModal" :title="editingTx ? '编辑流水' : '记录流水'" @close="showTxModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">产品</label>
          <div class="px-3 py-2 bg-bg-secondary rounded-md text-sm">{{ txForm.investment_name }}</div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="txForm.event_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="buy">买入</option>
              <option value="sell">卖出</option>
              <option value="dividend">分红 / 派息</option>
              <option value="fee">费用 / 税费</option>
              <option value="adjustment">调整（手动补正）</option>
            </select>
          </div>
          <div>
            <label class="block text-sm mb-1">日期</label>
            <input v-model="txForm.event_date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">{{ quantityFieldLabel }}</label>
            <input v-model.number="txForm.quantity" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
          <div>
            <label class="block text-sm mb-1">{{ priceFieldLabel }}</label>
            <input v-model.number="txForm.unit_price" type="number" step="0.001" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
        </div>
        <div class="text-xs text-text-muted" v-if="txForm.event_type === 'buy' || txForm.event_type === 'sell'">
          金额 = 数量 × 单价（{{ sym }}{{ fmt((txForm.quantity || 0) * (txForm.unit_price || 0)) }}）
        </div>
        <div><label class="block text-sm mb-1">备注</label><textarea v-model="txForm.notes" class="w-full px-3 py-2 border border-border-default rounded-md" rows="2" placeholder="可选"></textarea></div>
      </div>
      <template #footer>
        <button v-if="editingTx" @click="deleteTx" class="px-4 py-2 text-expense-color hover:bg-red-50 rounded-md">删除</button>
        <button @click="showTxModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="saveTx" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">{{ editingTx ? '更新' : '保存' }}</button>
      </template>
    </BaseModal>

    <!-- Per-product detail drawer (NAV curve + buy/sell markers) -->
    <InvestmentDetailDrawer v-if="drawerInvestment" :investment="drawerInvestment" @close="drawerInvestment = null" @updated="onInvestmentUpdated" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, Edit2, Trash2, RefreshCw, ListPlus, LineChart } from 'lucide-vue-next'
import { useInvestmentsStore } from '@/stores/investments'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import InvestmentDetailDrawer from './InvestmentDetailDrawer.vue'
import HealthPanel from './HealthPanel.vue'
import type { Investment, InvestmentTransaction, InvestmentEventType, InvestmentMetrics, InvestmentConsistency } from '@/types'

const store = useInvestmentsStore()
const settingsStore = useSettingsStore()
const api = useApi()
const { show } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)

const TYPE_LABELS: Record<string, string> = { stock: '股票', fund: '基金', bond: '债券', crypto: '加密货币', deposit: '存款', other: '其他' }
const TX_LABELS: Record<InvestmentEventType, string> = { buy: '买入', sell: '卖出', dividend: '分红', fee: '费用', adjustment: '调整' }
const UNDERLYING_OPTIONS = ['债券', '股票', '大宗商品', '黄金', '原油', '货币市场', '混合']
const AUTO_EXCHANGES = ['SH', 'SZ', 'HK', 'FUND_CN']

function fmt(n: number): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function signed(n: number): string { return (n >= 0 ? '+' : '') + sym.value + fmt(Math.abs(n)) }
function xirrLabel(n: number | null | undefined): string { return n === null || n === undefined ? '—' : (n * 100).toFixed(1) + '%' }
function colorClass(n: number): string { return n >= 0 ? 'text-income-color' : 'text-expense-color' }
function colorClassNullable(n: number | null | undefined): string { return n === null || n === undefined ? '' : (n >= 0 ? 'text-income-color' : 'text-expense-color') }
function supportsAutoRefresh(ex: string): boolean { return AUTO_EXCHANGES.includes(ex) }
function costDist(inv: Investment): number { const cb = inv.purchase_price || 0; const cur = inv.current_price || 0; if (cb <= 0) return 0; return ((cur - cb) / cb) * 100 }
function formatDateShort(s: string) { return new Date(s).toLocaleDateString('zh-CN') }

// Aggregate state
const productMetricMap = ref<Record<string, InvestmentMetrics>>({})
const consistency = ref<InvestmentConsistency | null>(null)
const expandedIds = ref<Set<string>>(new Set())
const drawerInvestment = ref<Investment | null>(null)
function openDetail(inv: Investment) { drawerInvestment.value = inv }
async function onInvestmentUpdated() {
  await store.fetchInvestments()
  const current = drawerInvestment.value
  if (current) {
    const fresh = store.investments.find(i => i.id === current.id)
    if (fresh) drawerInvestment.value = fresh
  }
  await loadAggregates()
}

async function loadConsistency() {
  try {
    const res = await api.get('/investments/consistency')
    consistency.value = res.data
  } catch { consistency.value = null }
}
const txMap = ref<Record<string, InvestmentTransaction[]>>({})

const activeInvestments = computed(() => store.investments.filter(i => !i.sell_date))
const soldInvestments = computed(() => store.investments.filter(i => !!i.sell_date))

// Data loading
async function loadAggregates() {
  try {
    const metricsRes = await api.get('/investments/metrics/all')
    const items: { investment_id: string; metrics: InvestmentMetrics }[] = metricsRes.data
    const map: Record<string, InvestmentMetrics> = {}
    for (const it of items) {
      map[it.investment_id] = it.metrics
    }
    productMetricMap.value = map
  } catch (e) {
    console.warn('Failed to load metrics', e)
  }
}

async function loadTxsFor(invId: string, force = false) {
  if (!force && txMap.value[invId]) return
  try { const res = await api.get(`/investments/${invId}/transactions`); txMap.value = { ...txMap.value, [invId]: res.data } }
  catch { txMap.value = { ...txMap.value, [invId]: [] } }
}

async function toggleExpand(invId: string) {
  if (expandedIds.value.has(invId)) { const s = new Set(expandedIds.value); s.delete(invId); expandedIds.value = s }
  else { await loadTxsFor(invId); const s = new Set(expandedIds.value); s.add(invId); expandedIds.value = s }
}

const refreshingId = ref<string | null>(null)
const refreshingAll = ref(false)

async function refreshPrice(inv: Investment) {
  if (!supportsAutoRefresh(inv.exchange)) {
    show('该市场不支持自动刷新，请手动编辑现价', 'warning')
    return
  }
  refreshingId.value = inv.id
  try {
    const res = await api.post(`/investments/${inv.id}/refresh-price`)
    const idx = store.investments.findIndex(i => i.id === inv.id)
    if (idx !== -1) store.investments[idx] = res.data
    show('已更新现价', 'success')
    await loadAggregates()
  } catch (e: any) {
    show(e.response?.data?.detail || '刷新失败', 'error')
  } finally { refreshingId.value = null }
}

async function refreshAllPrices() {
  refreshingAll.value = true
  try {
    const res = await api.post('/investments/refresh-prices/all')
    const results: { id: string; ok: boolean; price?: number; error?: string }[] = res.data
    let updated = 0, failed = 0
    for (const r of results) {
      if (r.ok) {
        // backend returns {id, name, ok, price, source}; reload the list to pick up new current_price
        updated++
      } else {
        failed++
      }
    }
    await store.fetchInvestments()
    show(`已刷新 ${updated} 个，失败 ${failed} 个`, failed ? 'warning' : 'success')
    await loadAggregates()
  } catch (e: any) {
    show(e.response?.data?.detail || '批量刷新失败', 'error')
  } finally { refreshingAll.value = false }
}

// Product modal
const showProductModal = ref(false)
const editingProduct = ref<Investment | null>(null)
const productForm = ref({ name: '', investment_type: 'stock' as Investment['investment_type'], underlying_asset_type: '', underlying_asset_type_custom: '', exchange: '', symbol: '', quantity: 0, purchase_price: 0, current_price: 0, purchase_date: '', sell_date: '', notes: '' })

const symbolPlaceholder = computed(() => {
  switch (productForm.value.exchange) {
    case 'SH': return '如 600519、510300'
    case 'SZ': return '如 000001、159915'
    case 'HK': return '如 00700'
    case 'FUND_CN': return '如 000001、519983'
    case 'US': return '如 AAPL、TSLA'
    case 'CRYPTO': return '如 BTC、ETH'
    default: return '请输入代码'
  }
})
const symbolHint = computed(() => supportsAutoRefresh(productForm.value.exchange) ? '输入代码后可一键刷新现价（来自腾讯财经）' : (productForm.value.exchange ? '该市场目前不支持自动刷新，请手动输入现价' : '指定市场后启用自动刷新（可选）'))

function openProductModal(inv?: Investment) {
  editingProduct.value = inv || null
  if (inv) {
    productForm.value = {
      name: inv.name, investment_type: inv.investment_type,
      underlying_asset_type: inv.underlying_asset_type || '', underlying_asset_type_custom: '',
      exchange: inv.exchange || '', symbol: inv.symbol || '',
      quantity: inv.quantity, purchase_price: inv.purchase_price, current_price: inv.current_price,
      purchase_date: inv.purchase_date, sell_date: inv.sell_date || '', notes: inv.notes || ''
    }
  } else {
    productForm.value = { name: '', investment_type: 'stock', underlying_asset_type: '', underlying_asset_type_custom: '', exchange: '', symbol: '', quantity: 0, purchase_price: 0, current_price: 0, purchase_date: '', sell_date: '', notes: '' }
  }
  showProductModal.value = true
}

async function saveProduct() {
  try {
    const data: any = { ...productForm.value }
    if (data.underlying_asset_type === '_custom' && data.underlying_asset_type_custom) data.underlying_asset_type = data.underlying_asset_type_custom
    else if (data.underlying_asset_type === '_custom') data.underlying_asset_type = ''
    delete data.underlying_asset_type_custom
    if (editingProduct.value) await store.updateInvestment(editingProduct.value.id, data)
    else await store.createInvestment(data)
    showProductModal.value = false
    show('保存成功', 'success')
    await loadAggregates()
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function removeItem(id: string) {
  if (!confirm('确定删除？此操作会同时删除该产品的所有流水。')) return
  try { await store.deleteInvestment(id); show('已删除', 'success'); await loadAggregates() }
  catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

// Transaction modal
const showTxModal = ref(false)
const editingTx = ref<InvestmentTransaction | null>(null)
const txForm = ref<{ investment_id: string; investment_name: string; event_type: InvestmentEventType; event_date: string; quantity: number; unit_price: number; notes: string }>({
  investment_id: '', investment_name: '', event_type: 'buy', event_date: new Date().toISOString().substring(0, 10), quantity: 0, unit_price: 0, notes: ''
})

const quantityFieldLabel = computed(() => txForm.value.event_type === 'buy' || txForm.value.event_type === 'sell' || txForm.value.event_type === 'adjustment' ? '数量' : '（不适用）')
const priceFieldLabel = computed(() => {
  if (txForm.value.event_type === 'dividend') return '分红总金额'
  if (txForm.value.event_type === 'fee') return '费用总金额'
  return '单价'
})

function openTxModal(inv: Investment, tx?: InvestmentTransaction) {
  if (tx) {
    editingTx.value = tx
    txForm.value = { investment_id: inv.id, investment_name: inv.name, event_type: tx.event_type, event_date: tx.event_date, quantity: tx.quantity, unit_price: tx.unit_price, notes: tx.notes || '' }
  } else {
    editingTx.value = null
    txForm.value = { investment_id: inv.id, investment_name: inv.name, event_type: 'buy', event_date: new Date().toISOString().substring(0, 10), quantity: 0, unit_price: 0, notes: '' }
  }
  showTxModal.value = true
}

async function saveTx() {
  try {
    if (editingTx.value) {
      await api.put(`/investments/${txForm.value.investment_id}/transactions/${editingTx.value.id}`, {
        event_type: txForm.value.event_type, event_date: txForm.value.event_date,
        quantity: txForm.value.quantity, unit_price: txForm.value.unit_price, notes: txForm.value.notes
      })
    } else {
      await api.post(`/investments/${txForm.value.investment_id}/transactions`, {
        event_type: txForm.value.event_type, event_date: txForm.value.event_date,
        quantity: txForm.value.quantity, unit_price: txForm.value.unit_price, notes: txForm.value.notes
      })
    }
    showTxModal.value = false
    show('保存成功', 'success')
    await Promise.all([store.fetchInvestments(), loadAggregates(), loadTxsFor(txForm.value.investment_id, true)])
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function deleteTx() {
  if (!editingTx.value || !confirm('确定删除此流水？')) return
  try {
    await api.delete(`/investments/${txForm.value.investment_id}/transactions/${editingTx.value.id}`)
    showTxModal.value = false
    show('已删除', 'success')
    await Promise.all([store.fetchInvestments(), loadAggregates(), loadTxsFor(txForm.value.investment_id, true)])
  } catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

function onRowClick(inv: Investment) { toggleExpand(inv.id) }

onMounted(async () => {
  await store.fetchInvestments()
  await Promise.all([loadAggregates(), loadConsistency()])
})
</script>