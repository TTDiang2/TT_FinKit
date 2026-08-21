<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <div class="flex gap-2">
        <button @click="activeTab = 'watchlist'" :class="['px-4 py-2 text-sm rounded-md transition-colors', activeTab === 'watchlist' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          自选 ({{ watchCount }})
        </button>
        <button @click="activeTab = 'pooled'" :class="['px-4 py-2 text-sm rounded-md transition-colors', activeTab === 'pooled' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">
          入池 ({{ pooledCount }})
        </button>
      </div>
      <div class="flex gap-2">
        <button @click="refreshAll" :disabled="refreshing" class="px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1 disabled:opacity-50">
          <RefreshCw :size="14" :class="refreshing ? 'animate-spin' : ''" /> 刷新行情
        </button>
        <button @click="openAddModal" class="px-4 py-2 text-sm rounded-md bg-accent-primary text-white hover:bg-accent-hover flex items-center gap-1">
          <Plus :size="14" /> 添加自选
        </button>
      </div>
    </div>

    <div class="flex items-center gap-3 mb-4">
      <div class="relative">
        <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input v-model="search" placeholder="搜索名称 / 代码" class="w-72 pl-9 pr-3 py-2 text-sm border border-border-default rounded-md" />
      </div>
      <select v-model="categoryFilter" class="px-3 py-2 text-sm border border-border-default rounded-md">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <div class="text-xs text-text-muted ml-auto">研究标的池 · 入池后自动拉取全量历史净值，为因子暴露 / 回测提供数据地基</div>
    </div>

    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">名称</th>
            <th class="px-3 py-2 font-medium">分类</th>
            <th class="px-3 py-2 font-medium text-right">最新净值</th>
            <th class="px-3 py-2 font-medium text-right">近1月</th>
            <th class="px-3 py-2 font-medium text-right">近1年</th>
            <th class="px-3 py-2 font-medium text-right">年化波动</th>
            <th class="px-3 py-2 font-medium text-right">夏普</th>
            <th class="px-3 py-2 font-medium text-right">最大回撤</th>
            <th class="px-3 py-2 font-medium text-right">数据</th>
            <th class="px-3 py-2 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filteredAssets" :key="a.id" class="border-t border-border-default">
            <td class="px-3 py-2">
              <div class="font-medium text-text-primary">{{ a.name }}<span v-if="a.is_money_market" class="ml-1 text-xs text-text-muted">货币</span></div>
              <div class="text-xs text-text-muted">{{ a.symbol }} · {{ EXCHANGE_LABELS[a.exchange] || a.exchange || '—' }}</div>
            </td>
            <td class="px-3 py-2">
              <button v-if="a.category" @click="categoryFilter = a.category" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary hover:bg-bg-secondary">{{ a.category }}</button>
              <span v-else class="text-text-muted">—</span>
            </td>
            <td class="px-3 py-2 text-right">
              <div>{{ a.indicators.latest_close != null ? fmt4(a.indicators.latest_close) : '—' }}</div>
              <div class="text-xs text-text-muted">{{ a.indicators.last_date || '' }}</div>
            </td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(a.indicators.ret_1m)">{{ pct(a.indicators.ret_1m) }}</td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(a.indicators.ret_1y)">{{ pct(a.indicators.ret_1y) }}</td>
            <td class="px-3 py-2 text-right">{{ pct(a.indicators.ann_volatility) }}</td>
            <td class="px-3 py-2 text-right">{{ a.indicators.sharpe != null ? a.indicators.sharpe.toFixed(2) : '—' }}</td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(a.indicators.max_drawdown)">{{ pct(a.indicators.max_drawdown) }}</td>
            <td class="px-3 py-2 text-right text-xs">
              <div :class="lagClass(a)">{{ a.indicators.points ? `${a.indicators.points} 行` : '无数据' }}</div>
              <div class="text-text-muted">{{ lagText(a) }}</div>
            </td>
            <td class="px-3 py-2 text-right whitespace-nowrap">
              <button @click="openDetail(a)" class="px-1.5 py-0.5 text-xs text-accent-primary hover:underline">详情</button>
              <button v-if="a.status === 'watchlist'" @click="openPoolModal(a)" class="px-1.5 py-0.5 text-xs text-accent-primary hover:underline">入池</button>
              <button @click="syncOne(a)" :disabled="a._syncing" class="px-1.5 py-0.5 text-xs text-accent-primary hover:underline disabled:opacity-50">{{ a._syncing ? '同步中' : '同步' }}</button>
              <button @click="removeAsset(a)" class="px-1.5 py-0.5 text-xs text-expense-color hover:underline">删除</button>
            </td>
          </tr>
          <tr v-if="!loading && !filteredAssets.length">
            <td colspan="10" class="px-4 py-8 text-center text-text-muted">{{ activeTab === 'watchlist' ? '暂无自选标的，点击右上角「添加自选」' : '暂无入池标的，从自选列表点击「入池」' }}</td>
          </tr>
          <tr v-if="loading">
            <td colspan="10" class="px-4 py-8 text-center text-text-muted">加载中…</td>
          </tr>
        </tbody>
      </table>
    </div>

    <BaseModal v-if="showAddModal" title="添加自选" @close="showAddModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-sm mb-1">代码 *</label><input v-model.trim="addForm.symbol" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 161005" /></div>
          <div>
            <label class="block text-sm mb-1">市场</label>
            <select v-model="addForm.exchange" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="FUND_CN">场外基金</option>
              <option value="SH">沪市</option>
              <option value="SZ">深市</option>
              <option value="US">美股</option>
            </select>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="addForm.asset_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="fund">基金</option>
              <option value="stock">股票</option>
              <option value="index">指数</option>
              <option value="gold">黄金</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div><label class="block text-sm mb-1">分类</label><input v-model.trim="addForm.category" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 核心-宽基" /></div>
        </div>
        <div><label class="block text-sm mb-1">名称</label><input v-model.trim="addForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="留空自动补全" /></div>
        <div class="text-xs text-text-muted">名称留空将通过行情源自动补全；货币基金会自动识别并跳过波动率 / 夏普计算</div>
      </div>
      <template #footer>
        <button @click="showAddModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="submitAdd" :disabled="!addForm.symbol || adding" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-50">{{ adding ? '添加中…' : '添加' }}</button>
      </template>
    </BaseModal>

    <BaseModal v-if="poolTarget" :title="`入池：${poolTarget.name}`" @close="poolTarget = null">
      <div class="space-y-3">
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-sm mb-1">管理费 %/年</label><input v-model.number="poolForm.mgmt_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 1.5" /></div>
          <div><label class="block text-sm mb-1">托管费 %/年</label><input v-model.number="poolForm.custody_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.25" /></div>
          <div><label class="block text-sm mb-1">申购费 %</label><input v-model.number="poolForm.purchase_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.15" /></div>
        </div>
        <div><label class="block text-sm mb-1">赎回费规则</label><input v-model.trim="poolForm.redeem_fee_note" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 <7天 1.5%，≥30天 0" /></div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-sm mb-1">起购金额（元）</label><input v-model.number="poolForm.min_purchase" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 10" /></div>
          <div><label class="block text-sm mb-1">赎回到账 T+N</label><input v-model.number="poolForm.redeem_t_days" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 2" /></div>
          <div>
            <label class="block text-sm mb-1">数据质量</label>
            <select v-model="poolForm.data_quality" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="">未标注</option>
              <option value="良好">良好</option>
              <option value="一般">一般</option>
              <option value="差">差</option>
            </select>
          </div>
        </div>
        <div><label class="block text-sm mb-1">流动性备注</label><input v-model.trim="poolForm.liquidity_note" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 QDII 赎回 T+10，额度紧张" /></div>
        <div class="text-xs text-text-muted">入池将触发后台全量历史净值拉取（iFinD / 东财 / akshare 多源降级），完成后可在数据列看到行数</div>
      </div>
      <template #footer>
        <button @click="poolTarget = null" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="submitPool" :disabled="pooling" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-50">{{ pooling ? '入池中…' : '确认入池' }}</button>
      </template>
    </BaseModal>

    <Teleport to="body">
      <div v-if="detail" class="fixed inset-0 z-50">
        <div class="absolute inset-0 bg-black/40" @click="detail = null"></div>
        <div class="absolute right-0 top-0 h-full w-[480px] bg-white shadow-2xl overflow-y-auto">
          <div class="flex items-center justify-between p-4 border-b border-border-default sticky top-0 bg-white z-10">
            <div>
              <h3 class="font-semibold">{{ detail.name }}</h3>
              <div class="text-xs text-text-muted">{{ detail.symbol }} · {{ EXCHANGE_LABELS[detail.exchange] || detail.exchange }} · {{ TYPE_LABELS[detail.asset_type] || detail.asset_type }}</div>
            </div>
            <button @click="detail = null" class="p-1 text-text-secondary hover:text-text-primary"><X :size="16" /></button>
          </div>
          <div class="p-4 space-y-4">
            <div class="flex items-center gap-2 flex-wrap">
              <span :class="['px-2 py-0.5 text-xs rounded-md', detail.status === 'pooled' ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary']">{{ detail.status === 'pooled' ? '已入池' : '自选' }}</span>
              <span v-if="detail.category" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary text-text-secondary">{{ detail.category }}</span>
              <span v-if="detail.is_money_market" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary text-text-secondary">货币基金</span>
              <span v-if="detail.data_quality" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary text-text-secondary">数据质量：{{ detail.data_quality }}</span>
            </div>

            <div class="grid grid-cols-4 gap-2 text-sm">
              <div class="p-2 rounded-md bg-bg-secondary"><div class="text-xs text-text-muted">最新净值</div><div class="font-semibold">{{ detail.indicators.latest_close != null ? fmt4(detail.indicators.latest_close) : '—' }}</div></div>
              <div class="p-2 rounded-md bg-bg-secondary"><div class="text-xs text-text-muted">近1月</div><div class="font-semibold" :class="colorClassNullable(detail.indicators.ret_1m)">{{ pct(detail.indicators.ret_1m) }}</div></div>
              <div class="p-2 rounded-md bg-bg-secondary"><div class="text-xs text-text-muted">近1年</div><div class="font-semibold" :class="colorClassNullable(detail.indicators.ret_1y)">{{ pct(detail.indicators.ret_1y) }}</div></div>
              <div class="p-2 rounded-md bg-bg-secondary"><div class="text-xs text-text-muted">最大回撤</div><div class="font-semibold" :class="colorClassNullable(detail.indicators.max_drawdown)">{{ pct(detail.indicators.max_drawdown) }}</div></div>
            </div>

            <div>
              <h4 class="text-sm font-medium mb-2">净值曲线</h4>
              <div v-if="navLoading" class="text-sm text-text-muted py-8 text-center">加载中…</div>
              <div v-else-if="!navSeries.length" class="text-sm text-text-muted py-8 text-center border border-dashed border-border-default rounded-md">尚未入池，无历史净值数据</div>
              <div v-else>
                <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" class="w-full h-40">
                  <polyline :points="polylinePoints" fill="none" stroke="currentColor" class="text-accent-primary" stroke-width="1.5" />
                </svg>
                <div class="flex justify-between text-xs text-text-muted">
                  <span>{{ navSeries[0]?.date }}</span>
                  <span>高 {{ fmt4(chartMax) }} · 低 {{ fmt4(chartMin) }}</span>
                  <span>{{ navSeries[navSeries.length - 1]?.date }}</span>
                </div>
                <div class="text-xs text-text-muted mt-1">{{ navSeries.length }} 个数据点（{{ navRangeDays }} 天）</div>
              </div>
            </div>

            <div>
              <h4 class="text-sm font-medium mb-2">费率与规则</h4>
              <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <div class="flex justify-between"><span class="text-text-muted">管理费</span><span>{{ detail.mgmt_fee != null ? detail.mgmt_fee + ' %/年' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">托管费</span><span>{{ detail.custody_fee != null ? detail.custody_fee + ' %/年' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">申购费</span><span>{{ detail.purchase_fee != null ? detail.purchase_fee + ' %' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">起购金额</span><span>{{ detail.min_purchase != null ? '¥' + detail.min_purchase : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">赎回到账</span><span>{{ detail.redeem_t_days != null ? 'T+' + detail.redeem_t_days : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">赎回费</span><span class="text-right">{{ detail.redeem_fee_note || '—' }}</span></div>
              </div>
              <div v-if="detail.liquidity_note" class="mt-2 text-xs text-text-muted">流动性：{{ detail.liquidity_note }}</div>
              <div v-if="detail.notes" class="mt-2 text-xs text-text-muted">备注：{{ detail.notes }}</div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Plus, RefreshCw, Search, X } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import type { ResearchAsset, ResearchPricePoint, SyncResult, AssetPriceStatus } from '@/types'

const api = useApi()
const { show } = useToast()

const TYPE_LABELS: Record<string, string> = { fund: '基金', stock: '股票', index: '指数', gold: '黄金', other: '其他' }
const EXCHANGE_LABELS: Record<string, string> = { SH: '沪市', SZ: '深市', FUND_CN: '场外基金', US: '美股', HK: '港股' }

interface AssetRow extends ResearchAsset { _syncing?: boolean }

const assets = ref<AssetRow[]>([])
const activeTab = ref<'watchlist' | 'pooled'>('watchlist')
const search = ref('')
const categoryFilter = ref('')
const loading = ref(false)
const refreshing = ref(false)

const watchCount = computed(() => assets.value.filter(a => a.status === 'watchlist').length)
const pooledCount = computed(() => assets.value.filter(a => a.status === 'pooled').length)
const categories = computed(() => [...new Set(assets.value.map(a => a.category).filter(Boolean))] as string[])

const filteredAssets = computed(() => {
  const kw = search.value.trim().toLowerCase()
  return assets.value.filter(a => {
    if (a.status !== activeTab.value) return false
    if (categoryFilter.value && a.category !== categoryFilter.value) return false
    if (kw && !(a.name.toLowerCase().includes(kw) || a.symbol.toLowerCase().includes(kw))) return false
    return true
  })
})

function fmt4(n: number): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 }) }
function pct(v: number | null | undefined): string { return v === null || v === undefined ? '—' : (v * 100).toFixed(2) + '%' }
function colorClassNullable(v: number | null | undefined): string { return v === null || v === undefined ? '' : (v >= 0 ? 'text-income-color' : 'text-expense-color') }
function lagText(a: ResearchAsset): string {
  const p = a.indicators.points
  if (!p) return ''
  const d = a.indicators.last_date
  if (!d) return ''
  const lag = Math.floor((Date.now() - new Date(d + 'T00:00:00').getTime()) / 86400000)
  return lag <= 7 ? `最新 ${d.slice(5)}` : `落后 ${lag} 天`
}
function lagClass(a: ResearchAsset): string {
  const d = a.indicators.last_date
  if (!d) return ''
  const lag = Math.floor((Date.now() - new Date(d + 'T00:00:00').getTime()) / 86400000)
  return lag > 7 ? 'text-expense-color' : ''
}

function errDetail(e: unknown): string {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  return err?.response?.data?.detail || err?.message || '请求失败'
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/research/assets')
    assets.value = res.data as ResearchAsset[]
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    loading.value = false
  }
}

const showAddModal = ref(false)
const adding = ref(false)
const addForm = ref({ symbol: '', exchange: 'FUND_CN', asset_type: 'fund', category: '', name: '' })

function openAddModal() {
  addForm.value = { symbol: '', exchange: 'FUND_CN', asset_type: 'fund', category: '', name: '' }
  showAddModal.value = true
}

async function submitAdd() {
  adding.value = true
  try {
    const res = await api.post('/research/assets', addForm.value)
    show(`已添加自选：${(res.data as ResearchAsset).name}`, 'success')
    showAddModal.value = false
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    adding.value = false
  }
}

const poolTarget = ref<ResearchAsset | null>(null)
const pooling = ref(false)
const poolForm = ref({ mgmt_fee: null as number | null, custody_fee: null as number | null, purchase_fee: null as number | null, redeem_fee_note: '', min_purchase: null as number | null, redeem_t_days: null as number | null, liquidity_note: '', data_quality: '' })

function openPoolModal(a: ResearchAsset) {
  poolTarget.value = a
  poolForm.value = { mgmt_fee: null, custody_fee: null, purchase_fee: null, redeem_fee_note: '', min_purchase: null, redeem_t_days: null, liquidity_note: '', data_quality: '' }
}

let pollTimer: ReturnType<typeof setTimeout> | null = null

async function submitPool() {
  if (!poolTarget.value) return
  pooling.value = true
  try {
    const target = poolTarget.value
    await api.post(`/research/assets/${target.id}/pool`, poolForm.value)
    show('已入池，后台正在拉取全量历史净值…', 'success')
    poolTarget.value = null
    await load()
    pollPriceStatus(target.id, 10)
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    pooling.value = false
  }
}

function pollPriceStatus(assetId: string, remaining: number) {
  if (remaining <= 0) return
  pollTimer = setTimeout(async () => {
    try {
      const res = await api.get('/research/assets/price-status')
      const st = (res.data as AssetPriceStatus[]).find(s => s.asset_id === assetId)
      if (st && st.rows > 0) {
        show(`历史净值拉取完成（${st.rows} 行，${st.last_date}）`, 'success')
        await load()
        return
      }
    } catch { /* transient — keep polling */ }
    pollPriceStatus(assetId, remaining - 1)
  }, 3000)
}

async function syncOne(a: AssetRow) {
  a._syncing = true
  try {
    const res = await api.post(`/research/assets/${a.id}/sync`)
    const r = res.data as SyncResult
    show(`同步成功：${r.rows} 行（${r.begin} ~ ${r.end}，${r.source}）`, 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    a._syncing = false
  }
}

async function refreshAll() {
  refreshing.value = true
  try {
    const res = await api.post('/research/assets/refresh-prices')
    const results = res.data as SyncResult[]
    const ok = results.filter(r => !r.error)
    const fail = results.filter(r => r.error)
    show(`刷新完成：成功 ${ok.length}（共 ${ok.reduce((s, r) => s + r.rows, 0)} 行）${fail.length ? ` / 失败 ${fail.length}` : ''}`, fail.length ? 'warning' : 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    refreshing.value = false
  }
}

async function removeAsset(a: ResearchAsset) {
  if (!confirm(`确认删除「${a.name}」及其全部历史净值数据？`)) return
  try {
    await api.delete(`/research/assets/${a.id}`)
    show('已删除', 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  }
}

const detail = ref<ResearchAsset | null>(null)
const navSeries = ref<ResearchPricePoint[]>([])
const navLoading = ref(false)
const CHART_W = 440
const CHART_H = 160

async function openDetail(a: ResearchAsset) {
  detail.value = a
  navSeries.value = []
  navLoading.value = true
  try {
    const res = await api.get(`/research/assets/${a.id}/nav-history`)
    navSeries.value = res.data as ResearchPricePoint[]
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    navLoading.value = false
  }
}

const chartCloses = computed(() => navSeries.value.map(p => p.close))
const chartMin = computed(() => Math.min(...chartCloses.value))
const chartMax = computed(() => Math.max(...chartCloses.value))
const navRangeDays = computed(() => {
  if (navSeries.value.length < 2) return 0
  const first = new Date(navSeries.value[0].date + 'T00:00:00').getTime()
  const last = new Date(navSeries.value[navSeries.value.length - 1].date + 'T00:00:00').getTime()
  return Math.round((last - first) / 86400000)
})
const polylinePoints = computed(() => {
  const closes = chartCloses.value
  if (closes.length < 2) return ''
  const min = chartMin.value
  const max = chartMax.value
  const span = max - min || 1
  const pad = 4
  return closes.map((c, i) => {
    const x = pad + (i / (closes.length - 1)) * (CHART_W - pad * 2)
    const y = CHART_H - pad - ((c - min) / span) * (CHART_H - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

onMounted(load)
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>
