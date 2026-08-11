<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold">资产</h1>
      <button @click="showModal = true; resetForm()" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover flex items-center gap-1">
        <Plus :size="16" /> 添加资产
      </button>
    </div>

    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">总资产</div>
        <div class="text-xl font-bold text-income-color">{{ sym }}{{ fmt(totalAssets) }}</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">总负债</div>
        <div class="text-xl font-bold text-expense-color">{{ sym }}{{ fmt(totalLiabilities) }}</div>
      </div>
      <div class="bg-white rounded-lg p-4 shadow-sm">
        <div class="text-sm text-text-secondary">净资产</div>
        <div class="text-xl font-bold" :class="netWorth >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(netWorth) }}</div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
      <div class="bg-white rounded-lg p-5 shadow-sm h-56">
        <h3 class="font-semibold mb-4">净资产趋势</h3>
        <Line v-if="netWorthChartData.labels.length" :data="netWorthChartData" :options="lineOpts" />
        <div v-else class="text-center text-text-muted py-8">暂无数据</div>
      </div>
      <div class="bg-white rounded-lg p-5 shadow-sm h-56">
        <h3 class="font-semibold mb-4">总资产趋势</h3>
        <Bar v-if="compositionChartData.labels.length" :data="compositionChartData" :options="stackedBarOpts" />
        <div v-else class="text-center text-text-muted py-8">暂无数据</div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 space-y-4">
        <div v-for="group in assetGroups" :key="group.type" v-show="group.items.length">
          <div class="flex items-center gap-2 mb-2">
            <div class="w-2 h-2 rounded-full" :style="{ backgroundColor: group.color }"></div>
            <h3 class="text-sm font-medium text-text-secondary">{{ group.label }}</h3>
            <span class="text-sm font-medium" :style="{ color: group.color }">{{ sym }}{{ fmt(group.total) }}</span>
          </div>
          <div class="bg-white rounded-lg shadow-sm divide-y divide-border-default">
            <div v-for="item in group.items" :key="item.id" class="flex items-center justify-between px-4 py-3">
              <div>
                <div class="text-sm font-medium">{{ item.name }}</div>
                <div v-if="!group.isCashAccounts" class="text-xs text-text-muted">{{ item.description || item.asset_type }}</div>
              </div>
              <div class="flex items-center gap-3">
                <span class="text-sm font-medium" :style="{ color: group.color }">{{ sym }}{{ fmt(item.value) }}</span>
                <template v-if="!group.isCashAccounts">
                  <button @click="editItem(item)" class="text-text-muted hover:text-text-primary"><Edit2 :size="14" /></button>
                  <button @click="removeItem(item.id)" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-lg p-5 shadow-sm">
        <h3 class="font-semibold mb-4">资产构成</h3>
        <Doughnut v-if="chartData.labels.length" :data="chartData" :options="{ responsive: true, plugins: { legend: { position: 'bottom' } } }" />
        <div v-else class="text-center text-text-muted py-8">暂无数据</div>
      </div>
    </div>

    <BaseModal v-if="showModal" :title="editId ? '编辑资产' : '添加资产'" @close="showModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">名称</label><input v-model="form.name" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如：自住房" /></div>
        <div><label class="block text-sm mb-1">类型</label>
          <select v-model="form.asset_type" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="fixed_asset">固定资产</option><option value="cash_equivalent">现金等价物</option>
            <option value="investment">投资资产</option><option value="other_asset">其他资产</option>
            <option value="liability">负债</option>
          </select>
        </div>
        <div><label class="block text-sm mb-1">价值</label><input v-model.number="form.value" type="number" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="0.00" /></div>
        <div><label class="block text-sm mb-1">取得日期</label><input v-model="form.acquisition_date" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="yyyy-mm-dd" /></div>
        <div><label class="block text-sm mb-1">说明</label><input v-model="form.description" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="简要描述" /></div>
        <div><label class="block text-sm mb-1">备注</label><textarea v-model="form.notes" class="w-full px-3 py-2 border border-border-default rounded-md" rows="2" placeholder="可选"></textarea></div>
      </div>
      <template #footer>
        <button @click="showModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="saveItem" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">{{ editId ? '更新' : '添加' }}</button>
      </template>
    </BaseModal>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, Edit2, Trash2 } from 'lucide-vue-next'
import { Doughnut, Line, Bar } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip, Legend, PointElement, LineElement, CategoryScale, LinearScale, BarElement, Filler } from 'chart.js'
import { useAssetsStore } from '@/stores/assets'
import { useAccountsStore } from '@/stores/accounts'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import type { Asset, NetWorthTrend, AssetCompositionTrend } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend, PointElement, LineElement, CategoryScale, LinearScale, BarElement, Filler)

interface DisplayItem {
  id: string
  name: string
  value: number
  description?: string
  asset_type?: string
  isCashAccount?: boolean
}

interface DisplayGroup {
  type: string
  label: string
  color: string
  total: number
  isCashAccounts: boolean
  items: DisplayItem[]
}

const store = useAssetsStore()
const accStore = useAccountsStore()
const settingsStore = useSettingsStore()
const api = useApi()
const { show: showToast } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)

const netWorthTrendData = ref<NetWorthTrend[]>([])
const assetCompTrendData = ref<AssetCompositionTrend[]>([])

const netWorthChartData = computed(() => ({
  labels: netWorthTrendData.value.map(d => d.month),
  datasets: [{
    label: '净资产',
    data: netWorthTrendData.value.map(d => d.net_worth),
    borderColor: '#FF9800',
    backgroundColor: 'rgba(255, 152, 0, 0.1)',
    tension: 0.3,
    fill: true,
    pointStyle: 'circle' as const
  }]
}))

const compositionChartData = computed(() => ({
  labels: assetCompTrendData.value.map(d => d.month),
  datasets: [
    { label: '货币资金', data: assetCompTrendData.value.map(d => d.cash), backgroundColor: '#4CAF50' },
    { label: '投资账户', data: assetCompTrendData.value.map(d => d.investment_accounts), backgroundColor: '#2196F3' },
    { label: '固定资产', data: assetCompTrendData.value.map(d => d.fixed_assets), backgroundColor: '#333333' },
    { label: '投资资产', data: assetCompTrendData.value.map(d => d.investment_assets), backgroundColor: '#9C27B0' },
    { label: '其他资产', data: assetCompTrendData.value.map(d => d.other_assets), backgroundColor: '#FF9800' },
  ]
}))

const lineOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { position: 'top' as const, labels: { usePointStyle: true } } },
  scales: { x: { ticks: { font: { size: 10 }, maxRotation: 0 } }, y: { ticks: { font: { size: 10 } } } }
}

const stackedBarOpts = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: { mode: 'index' as const }
  },
  scales: {
    x: { stacked: true, ticks: { font: { size: 10 }, maxRotation: 0 }, grid: { display: false } },
    y: { stacked: true, ticks: { font: { size: 10 } } }
  }
}

const showModal = ref(false)
const editId = ref<string | null>(null)
const form = ref<{ name: string; asset_type: Asset['asset_type']; value: number; acquisition_date: string; description: string; notes: string }>({
  name: '', asset_type: 'fixed_asset', value: 0, acquisition_date: '', description: '', notes: ''
})

const CASH_ACCOUNT_CONFIG = { label: '流动资产（货币资金）', color: '#4CAF50' }
const INVESTMENT_ACCOUNT_CONFIG = { label: '投资资产', color: '#2196F3' }

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  fixed_asset: { label: '固定资产', color: '#333333' },
  cash_equivalent: { label: '流动资产', color: '#4CAF50' },
  investment: { label: '投资资产', color: '#2196F3' },
  other_asset: { label: '其他资产', color: '#9C27B0' },
  liability: { label: '负债', color: '#F44336' },
}

function fmt(n: number): string { return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

// Compute accounts by type
const cashAccounts = computed(() => accStore.accounts.filter(a => a.account_type === 'cash'))
const investmentAccounts = computed(() => accStore.accounts.filter(a => a.account_type === 'investment'))

const totalCashAccounts = computed(() => cashAccounts.value.reduce((s, a) => s + a.current_balance, 0))
const totalInvestmentAccounts = computed(() => investmentAccounts.value.reduce((s, a) => s + a.current_balance, 0))
const totalAssets = computed(() => store.assets.filter(a => a.asset_type !== 'liability').reduce((s, a) => s + a.value, 0) + totalCashAccounts.value + totalInvestmentAccounts.value)
const totalLiabilities = computed(() => store.assets.filter(a => a.asset_type === 'liability').reduce((s, a) => s + a.value, 0))
const netWorth = computed(() => totalAssets.value - totalLiabilities.value)

const cashAccountsGroup = computed<DisplayGroup>(() => ({
  type: 'cash_accounts',
  label: CASH_ACCOUNT_CONFIG.label,
  color: CASH_ACCOUNT_CONFIG.color,
  total: totalCashAccounts.value,
  isCashAccounts: true,
  items: cashAccounts.value.map(a => ({ id: a.id, name: a.name, value: a.current_balance, isCashAccount: true }))
}))

const investmentAccountsGroup = computed<DisplayGroup>(() => ({
  type: 'investment_accounts',
  label: INVESTMENT_ACCOUNT_CONFIG.label,
  color: INVESTMENT_ACCOUNT_CONFIG.color,
  total: totalInvestmentAccounts.value,
  isCashAccounts: false,
  items: investmentAccounts.value.map(a => ({ id: a.id, name: a.name, value: a.current_balance, isCashAccount: false }))
}))

const assetGroups = computed<DisplayGroup[]>(() => [
  cashAccountsGroup.value,
  investmentAccountsGroup.value,
  ...Object.entries(TYPE_CONFIG).map(([type, cfg]): DisplayGroup => {
    const items = store.assets.filter(a => a.asset_type === type).map((a): DisplayItem => ({
      id: a.id, name: a.name, value: a.value, description: a.description, asset_type: a.asset_type
    }))
    return { type, label: cfg.label, color: cfg.color, total: items.reduce((s, a) => s + a.value, 0), isCashAccounts: false, items }
  })
])

const chartData = computed(() => {
  const grouped: Record<string, number> = {}
  if (totalCashAccounts.value > 0) grouped['cash_accounts'] = totalCashAccounts.value
  if (totalInvestmentAccounts.value > 0) grouped['investment_accounts'] = totalInvestmentAccounts.value
  store.assets.filter(a => a.asset_type !== 'liability').forEach(a => { grouped[a.asset_type] = (grouped[a.asset_type] || 0) + a.value })
  const entries = Object.entries(grouped).filter(([, v]) => v > 0)
  const total = entries.reduce((s, [, v]) => s + v, 0)
  return {
    labels: entries.map(([k]) => {
      let label = ''
      if (k === 'cash_accounts') label = CASH_ACCOUNT_CONFIG.label
      else if (k === 'investment_accounts') label = INVESTMENT_ACCOUNT_CONFIG.label
      else label = TYPE_CONFIG[k]?.label || k
      // Add percentage to label
      const pct = total > 0 ? ((entries.find(e => e[0] === k)?.[1] || 0) / total * 100).toFixed(1) : '0.0'
      return `${label} (${pct}%)`
    }),
    datasets: [{ data: entries.map(([, v]) => v), backgroundColor: entries.map(([k]) => {
      if (k === 'cash_accounts') return CASH_ACCOUNT_CONFIG.color
      if (k === 'investment_accounts') return INVESTMENT_ACCOUNT_CONFIG.color
      return TYPE_CONFIG[k]?.color || '#999'
    }) }]
  }
})

function resetForm() {
  editId.value = null
  form.value = { name: '', asset_type: 'fixed_asset', value: 0, acquisition_date: '', description: '', notes: '' }
}
function editItem(item: DisplayItem) {
  const asset = store.assets.find(a => a.id === item.id)
  if (!asset) return
  editId.value = asset.id
  form.value = { name: asset.name, asset_type: asset.asset_type, value: asset.value, acquisition_date: asset.acquisition_date || '', description: asset.description || '', notes: asset.notes || '' }
  showModal.value = true
}
async function saveItem() {
  try {
    if (editId.value) await store.updateAsset(editId.value, form.value)
    else await store.createAsset(form.value)
    showModal.value = false
    showToast('保存成功', 'success')
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '保存失败'
    showToast(msg, 'error')
  }
}
async function removeItem(id: string) {
  if (!confirm('确定删除？')) return
  await store.deleteAsset(id)
  showToast('已删除', 'success')
}

onMounted(async () => {
  await Promise.all([store.fetchAssets(), accStore.fetchAccounts()])
  try {
    const [nw, ac] = await Promise.all([
      api.get('/statistics/net-worth-trend', { params: { months: 12 } }),
      api.get('/statistics/asset-composition-trend', { params: { months: 12 } }),
    ])
    netWorthTrendData.value = nw.data
    assetCompTrendData.value = ac.data
  } catch (e) { console.error(e) }
})
</script>
