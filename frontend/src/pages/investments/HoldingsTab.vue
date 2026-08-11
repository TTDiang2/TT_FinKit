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

    <!-- 8 Stat cards -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
      <StatCard label="总投入" :value="fmt(portfolioMetrics.total_invested)" :color-class="''" />
      <StatCard label="当前市值" :value="fmt(portfolioMetrics.current_value)" :color-class="''" />
      <StatCard label="总盈亏" :value="signed(portfolioMetrics.total_pnl)" :color-class="colorClass(portfolioMetrics.total_pnl)" />
      <StatCard label="总收益率" :value="pct(portfolioMetrics.total_return_pct)" :color-class="colorClass(portfolioMetrics.total_pnl)" />
      <StatCard label="总年化 XIRR" :value="xirrLabel(portfolioMetrics.xirr_annualized)" :color-class="colorClassNullable(portfolioMetrics.xirr_annualized)" />
      <StatCard label="近 1 年年化" :value="xirrLabel(portfolioMetrics.last_1y_xirr)" :color-class="colorClassNullable(portfolioMetrics.last_1y_xirr)" />
      <StatCard label="近 1 月年化" :value="xirrLabel(portfolioMetrics.last_1m_xirr)" :color-class="colorClassNullable(portfolioMetrics.last_1m_xirr)" />
      <StatCard label="累计分红" :value="fmt(portfolioMetrics.total_dividends)" :color-class="portfolioMetrics.total_dividends > 0 ? 'text-income-color' : ''" />
    </div>

    <!-- Charts Row 1: Allocation + Per-product returns -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h3 class="font-semibold mb-2 text-sm">资产配置（按底层资产）</h3>
        <div class="h-56 flex items-center justify-center">
          <Doughnut v-if="allocationChart.labels.length" :data="allocationChart" :options="doughnutOpts" />
          <div v-else class="text-text-muted text-sm">暂无数据</div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <h3 class="font-semibold mb-2 text-sm">各产品年化对比</h3>
        <div class="h-56">
          <Bar v-if="perProductChart.labels.length" :data="perProductChart" :options="barHorizontalOpts" />
          <div v-else class="text-text-muted text-sm flex items-center justify-center h-full">暂无数据</div>
        </div>
      </div>
    </div>

    <!-- Charts Row 2: Value curve -->
    <div class="bg-white rounded-lg p-4 shadow-sm mb-4">
      <h3 class="font-semibold mb-2 text-sm">价值曲线（月度，投入 vs 市值）</h3>
      <div class="h-56">
        <Line v-if="valueCurveChart.labels?.length" :data="valueCurveChart" :options="lineDualOpts" />
        <div v-else class="text-text-muted text-sm flex items-center justify-center h-full">暂无快照数据（页面加载一段时间后会自动生成）</div>
      </div>
    </div>

    <!-- Charts Row 3: Cash flow -->
    <div class="bg-white rounded-lg p-4 shadow-sm mb-4">
      <h3 class="font-semibold mb-2 text-sm">现金流（月度堆叠，正数=买入/分红，负数=卖出/费用）</h3>
      <div class="h-56">
        <Bar v-if="cashFlowChart.labels?.length" :data="cashFlowChart" :options="barStackedOpts" />
        <div v-else class="text-text-muted text-sm flex items-center justify-center h-full">暂无流水记录</div>
      </div>
    </div>

    <!-- Active Holdings Table -->
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
            <tr class="border-t border-border-default hover:bg-bg-secondary">
              <td class="px-3 py-2">
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
              <td class="px-3 py-2 text-center whitespace-nowrap">
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
    <InvestmentDetailDrawer v-if="drawerInvestment" :investment="drawerInvestment" @close="drawerInvestment = null" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Plus, Edit2, Trash2, RefreshCw, ListPlus, LineChart } from 'lucide-vue-next'
import { Doughnut, Bar, Line } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend, BarElement, LineElement, PointElement, CategoryScale, LinearScale } from 'chart.js'
import { useInvestmentsStore } from '@/stores/investments'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import InvestmentDetailDrawer from './InvestmentDetailDrawer.vue'
import StatCard from '@/components/common/StatCard.vue'
import type { Investment, InvestmentTransaction, InvestmentEventType, InvestmentMetrics } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend, BarElement, LineElement, PointElement, CategoryScale, LinearScale)

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
function pct(n: number): string { return (n ?? 0).toFixed(2) + '%' }
function xirrLabel(n: number | null | undefined): string { return n === null || n === undefined ? '—' : (n * 100).toFixed(1) + '%' }
function colorClass(n: number): string { return n >= 0 ? 'text-income-color' : 'text-expense-color' }
function colorClassNullable(n: number | null | undefined): string { return n === null || n === undefined ? '' : (n >= 0 ? 'text-income-color' : 'text-expense-color') }
function supportsAutoRefresh(ex: string): boolean { return AUTO_EXCHANGES.includes(ex) }
function costDist(inv: Investment): number { const cb = inv.purchase_price || 0; const cur = inv.current_price || 0; if (cb <= 0) return 0; return ((cur - cb) / cb) * 100 }
function formatDateShort(s: string) { return new Date(s).toLocaleDateString('zh-CN') }

// Aggregate state
const productMetricMap = ref<Record<string, InvestmentMetrics>>({})
const portfolioMetrics = ref<InvestmentMetrics>({
  total_invested: 0, total_redeemed: 0, total_dividends: 0, total_fees: 0,
  current_value: 0, total_pnl: 0, total_return_pct: 0,
  xirr_annualized: null, last_1y_xirr: null, last_1m_xirr: null,
  days_held: 0, last_event_date: null
})
const allTransactions = ref<InvestmentTransaction[]>([])
const allSnapshots = ref<{ investment_id: string; snapshot_date: string; unit_price: number; quantity_held: number; total_value: number }[]>([])
const expandedIds = ref<Set<string>>(new Set())
const drawerInvestment = ref<Investment | null>(null)
function openDetail(inv: Investment) { drawerInvestment.value = inv }
const txMap = ref<Record<string, InvestmentTransaction[]>>({})

const activeInvestments = computed(() => store.investments.filter(i => !i.sell_date))
const soldInvestments = computed(() => store.investments.filter(i => !!i.sell_date))

// Charts
const allocationChart = computed(() => {
  const grouped: Record<string, number> = {}
  activeInvestments.value.forEach(i => { const k = i.underlying_asset_type || '未分类'; grouped[k] = (grouped[k] || 0) + (i.current_price * i.quantity) })
  const entries = Object.entries(grouped).filter(([, v]) => v > 0)
  const colors = ['#4CAF50', '#F44336', '#2196F3', '#FF9800', '#9C27B0', '#00BCD4', '#795548', '#607D8B']
  return { labels: entries.map(([k]) => k), datasets: [{ data: entries.map(([, v]) => v), backgroundColor: entries.map((_, i) => colors[i % colors.length]) }] }
})

const perProductChart = computed(() => {
  const items = activeInvestments.value.map(inv => ({ name: inv.name, xirr: productMetricMap.value[inv.id]?.xirr_annualized ?? null })).filter(x => x.xirr !== null)
  return {
    labels: items.map(x => x.name),
    datasets: [{
      label: 'XIRR',
      data: items.map(x => Number(((x.xirr as number) * 100).toFixed(1))),
      backgroundColor: items.map(x => (x.xirr as number) >= 0 ? '#4CAF50' : '#F44336')
    }]
  }
})

const valueCurveChart = computed(() => {
  const byDate: Record<string, { invested: number; value: number }> = {}
  // Track running totals across all products' transactions
  const txsByDate = [...allTransactions.value].sort((a, b) => a.event_date.localeCompare(b.event_date))
  for (const tx of txsByDate) {
    const m = tx.event_date.substring(0, 7)
    if (!byDate[m]) byDate[m] = { invested: 0, value: 0 }
    if (tx.event_type === 'buy' || tx.event_type === 'adjustment') byDate[m].invested += tx.amount
    else if (tx.event_type === 'sell') byDate[m].invested -= Math.abs(tx.amount)
  }
  // Snapshots: aggregate total_value by month
  for (const snap of allSnapshots.value) {
    const m = snap.snapshot_date.substring(0, 7)
    if (!byDate[m]) byDate[m] = { invested: 0, value: 0 }
    byDate[m].value += snap.total_value
  }
  // Also fold in current value at "today" month
  const now = new Date().toISOString().substring(0, 7)
  if (!byDate[now]) byDate[now] = { invested: 0, value: 0 }
  byDate[now].value = activeInvestments.value.reduce((s, i) => s + i.current_price * i.quantity, 0)
  const months = Object.keys(byDate).sort()
  return {
    labels: months,
    datasets: [
      { label: '累计投入', data: months.map(m => byDate[m].invested), borderColor: '#2196F3', backgroundColor: '#2196F320', tension: 0.2 },
      { label: '市值', data: months.map(m => byDate[m].value), borderColor: '#4CAF50', backgroundColor: '#4CAF5020', tension: 0.2 }
    ]
  }
})

const cashFlowChart = computed(() => {
  const byMonth: Record<string, { buy: number; sell: number; dividend: number; fee: number }> = {}
  for (const tx of allTransactions.value) {
    const m = tx.event_date.substring(0, 7)
    if (!byMonth[m]) byMonth[m] = { buy: 0, sell: 0, dividend: 0, fee: 0 }
    if (tx.event_type === 'buy') byMonth[m].buy += tx.amount
    else if (tx.event_type === 'sell') byMonth[m].sell += Math.abs(tx.amount)
    else if (tx.event_type === 'dividend') byMonth[m].dividend += Math.abs(tx.amount)
    else if (tx.event_type === 'fee') byMonth[m].fee += Math.abs(tx.amount)
  }
  const months = Object.keys(byMonth).sort()
  return {
    labels: months,
    datasets: [
      { label: '买入', data: months.map(m => byMonth[m].buy), backgroundColor: '#4CAF50' },
      { label: '卖出', data: months.map(m => -byMonth[m].sell), backgroundColor: '#F44336' },
      { label: '分红', data: months.map(m => byMonth[m].dividend), backgroundColor: '#FF9800' },
      { label: '费用', data: months.map(m => -byMonth[m].fee), backgroundColor: '#9C27B0' }
    ]
  }
})

const doughnutOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' as const, labels: { boxWidth: 12, font: { size: 11 } } } } }
const barHorizontalOpts = { responsive: true, maintainAspectRatio: false, indexAxis: 'y' as const, plugins: { legend: { display: false } }, scales: { x: { ticks: { callback: (v: any) => v + '%' } } } }
const lineDualOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' as const } } }
const barStackedOpts = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' as const } }, scales: { x: { stacked: true }, y: { stacked: true } } }

// Data loading
async function loadAggregates() {
  try {
    const metricsRes = await api.get('/investments/metrics/all')
    const items: { investment_id: string; metrics: InvestmentMetrics }[] = metricsRes.data
    const map: Record<string, InvestmentMetrics> = {}
    let pm: InvestmentMetrics = {
      total_invested: 0, total_redeemed: 0, total_dividends: 0, total_fees: 0,
      current_value: 0, total_pnl: 0, total_return_pct: 0,
      xirr_annualized: null, last_1y_xirr: null, last_1m_xirr: null,
      days_held: 0, last_event_date: null
    }
    for (const it of items) {
      map[it.investment_id] = it.metrics
      pm.total_invested += it.metrics.total_invested
      pm.total_redeemed += it.metrics.total_redeemed
      pm.total_dividends += it.metrics.total_dividends
      pm.total_fees += it.metrics.total_fees
      pm.current_value += it.metrics.current_value
      pm.total_pnl += it.metrics.total_pnl
    }
    pm.total_return_pct = pm.total_invested > 0 ? (pm.total_pnl / pm.total_invested) * 100 : 0
    productMetricMap.value = map
    portfolioMetrics.value = pm
  } catch (e) {
    console.warn('Failed to load metrics', e)
  }
  // Load all transactions and snapshots in parallel
  const txPromises = activeInvestments.value.map(inv => api.get(`/investments/${inv.id}/transactions`).then(r => r.data).catch(() => []))
  const snapPromises = activeInvestments.value.map(inv => api.get(`/investments/${inv.id}/snapshots`).then(r => r.data).catch(() => []))
  const [txResults, snapResults] = await Promise.all([Promise.all(txPromises), Promise.all(snapPromises)])
  allTransactions.value = txResults.flat()
  allSnapshots.value = snapResults.flat()
}

async function loadTxsFor(invId: string) {
  if (txMap.value[invId]) return
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
    const results: { id: string; data: Investment | null; error: string | null }[] = res.data
    let updated = 0, failed = 0
    for (const r of results) {
      if (r.data) { const idx = store.investments.findIndex(i => i.id === r.id); if (idx !== -1) store.investments[idx] = r.data; updated++ }
      else failed++
    }
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
    await Promise.all([store.fetchInvestments(), loadAggregates(), loadTxsFor(txForm.value.investment_id)])
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function deleteTx() {
  if (!editingTx.value || !confirm('确定删除此流水？')) return
  try {
    await api.delete(`/investments/${txForm.value.investment_id}/transactions/${editingTx.value.id}`)
    showTxModal.value = false
    show('已删除', 'success')
    await Promise.all([store.fetchInvestments(), loadAggregates(), loadTxsFor(txForm.value.investment_id)])
  } catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

// I need to expand rows by clicking on the row (not just row click in template)
// Let me re-add a click handler at row level
function onRowClick(inv: Investment) { toggleExpand(inv.id) }

onMounted(async () => {
  await store.fetchInvestments()
  await loadAggregates()
})
</script>