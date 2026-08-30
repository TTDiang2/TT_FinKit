<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">回测</h2>
      <button @click="showNew = true" class="btn-primary"><Plus :size="14" /> 新建回测</button>
    </div>

    <!-- 按策略分组的回测列表 -->
    <div v-if="strategyGroups.length">
      <div v-for="g in strategyGroups" :key="g.strategyId" class="bg-white rounded-lg shadow-sm mb-4 overflow-hidden">
        <div
          class="flex items-center justify-between px-4 py-2.5 cursor-pointer select-none hover:bg-bg-tertiary/60"
          @click="toggleGroup(g.strategyId)"
        >
          <div class="flex items-center gap-2">
            <ChevronDown :size="14" class="transition-transform text-text-muted" :class="expandedGroupIds.has(g.strategyId) ? '' : '-rotate-90'" />
            <span class="text-sm font-medium">{{ g.name }}</span>
            <span class="text-xs text-text-muted">{{ g.items.length }} 次回测</span>
            <span v-if="g.runningCount" class="text-xs text-blue-600">● {{ g.runningCount }} 运行中</span>
            <span v-if="g.failedCount" class="text-xs text-expense-color">{{ g.failedCount }} 失败</span>
          </div>
          <span class="text-xs text-text-muted">最近 {{ fmtDateTime(g.items[0].created_at) }}</span>
        </div>

        <table v-if="expandedGroupIds.has(g.strategyId)" class="w-full text-sm border-t border-border-default">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-2 font-medium">区间</th>
              <th class="px-3 py-2 font-medium text-center">频率</th>
              <th class="px-3 py-2 font-medium text-right">年化收益</th>
              <th class="px-3 py-2 font-medium text-right">夏普</th>
              <th class="px-3 py-2 font-medium text-right">最大回撤</th>
              <th class="px-3 py-2 font-medium text-right">创建时间</th>
              <th class="px-3 py-2 font-medium text-center">状态</th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bt in g.items" :key="bt.id"
              @click="navigateTo(`/investments/backtests/${bt.id}`)"
              class="border-t border-border-default cursor-pointer hover:bg-bg-tertiary">
              <td class="px-3 py-2 text-xs text-text-secondary">{{ bt.start_date }} → {{ bt.end_date }}</td>
              <td class="px-3 py-2 text-center text-xs">{{ freqLabel(bt.rebalance_freq) }}</td>
              <td class="px-3 py-2 text-right" :class="metricClass(bt.results?.metrics?.ann_return)">
                {{ fmtPct(bt.results?.metrics?.ann_return) }}
              </td>
              <td class="px-3 py-2 text-right">{{ fmtNum(bt.results?.metrics?.sharpe) }}</td>
              <td class="px-3 py-2 text-right" :class="metricClass(bt.results?.metrics?.max_drawdown)">
                {{ fmtPct(bt.results?.metrics?.max_drawdown) }}
              </td>
              <td class="px-3 py-2 text-right text-xs text-text-muted">{{ fmtDateTime(bt.created_at) }}</td>
              <td class="px-3 py-2 text-center">
                <span v-if="bt.status !== 'done'" :class="statusClass(bt.status)" class="px-1.5 py-0.5 text-xs rounded">
                  {{ statusLabel(bt.status) }}
                </span>
                <span v-else class="text-text-muted text-xs">✓</span>
              </td>
              <td class="px-3 py-2 text-right whitespace-nowrap" @click.stop>
                <template v-if="deleteId === bt.id">
                  <span class="text-xs text-text-muted mr-1">确认删除？</span>
                  <button @click="deleteBacktest(bt)" :disabled="deleting" class="px-1.5 py-0.5 text-xs rounded bg-expense-bg text-expense-color disabled:opacity-50">
                    确认
                  </button>
                  <button @click="deleteId = null" class="px-1.5 py-0.5 text-xs rounded bg-bg-tertiary text-text-secondary ml-1">
                    取消
                  </button>
                </template>
                <button v-else @click="deleteId = bt.id" class="p-1 rounded hover:bg-expense-bg text-text-muted hover:text-expense-color" title="删除该回测">
                  <Trash2 :size="14" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-else class="bg-white rounded-lg shadow-sm py-10 text-center text-text-muted text-sm">
      暂无回测记录，点击右上角「新建回测」开始
    </div>

    <!-- 新建回测弹窗 -->
    <BaseModal v-if="showNew" title="新建回测" @close="showNew = false" width="max-w-lg">
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1">策略</label>
          <select v-model="newForm.strategy_id" class="w-full px-3 py-2 text-sm border border-border-default rounded-md">
            <option value="">请选择策略</option>
            <option v-for="s in strategies" :key="s.id" :value="s.id">
              {{ s.name }} (v{{ s.version }})
            </option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">标的范围（多选组合，限 ≤500 只）</label>
          <div class="border border-border-default rounded-md p-2 max-h-32 overflow-y-auto bg-bg-primary">
            <label v-if="!assetGroups.length" class="text-xs text-text-muted px-1 py-1">无可用组合，先在标的面板创建</label>
            <label v-for="g in assetGroups" :key="g.id" class="flex items-center gap-2 px-1 py-0.5 text-sm hover:bg-bg-tertiary rounded cursor-pointer">
              <input type="checkbox" :checked="newForm.scope_group_ids.includes(g.id)"
                @change="toggleScopeGroup(g.id)" class="accent-accent-primary" />
              <span class="flex-1 truncate">{{ g.name }}</span>
              <span class="text-xs text-text-muted">{{ g.asset_ids.length }}</span>
            </label>
          </div>
          <div v-if="newForm.scope_group_ids.length" class="text-xs text-text-muted mt-1">
            已选 {{ newForm.scope_group_ids.length }} 个组合（去重后的标的池将在回测详情页冻结显示）
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm font-medium mb-1">开始日期</label>
            <input v-model="newForm.start_date" type="date" class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">结束日期</label>
            <input v-model="newForm.end_date" type="date" class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">调仓频率</label>
          <select v-model="newForm.rebalance_freq" class="w-full px-3 py-2 text-sm border border-border-default rounded-md">
            <option value="monthly">月度（月末）</option>
            <option value="weekly">周度（周五）</option>
            <option value="daily">每日</option>
          </select>
        </div>
        <button @click="createBacktest" :disabled="creating || !newForm.strategy_id"
          class="btn-primary w-full disabled:opacity-50">
          {{ creating ? '运行中...' : '开始回测' }}
        </button>
        <div v-if="createError" class="text-sm text-expense-color">{{ createError }}</div>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Trash2, ChevronDown } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import BaseModal from '@/components/common/BaseModal.vue'
import type { BacktestResponse, StrategyResponse, ResearchAsset } from '@/types'

const api = useApi()
const router = useRouter()
const backtests = ref<BacktestResponse[]>([])
const strategies = ref<StrategyResponse[]>([])
const pooledAssets = ref<ResearchAsset[]>([])
const pooledLoadError = ref('')
const loading = ref(false)
const showNew = ref(false)
const creating = ref(false)
const createError = ref('')

const expandedGroupIds = ref<Set<string>>(new Set())
const assetGroups = ref<{ id: string; name: string; asset_ids: string[] }[]>([])
const deleteId = ref<string | null>(null)
const deleting = ref(false)

const newForm = ref({
  strategy_id: '',
  strategy_version: 1,
  start_date: '',
  end_date: '',
  rebalance_freq: 'monthly',
  scope_group_ids: [] as string[],
  universe: [] as string[],
  params: {},
})

function toggleScopeGroup(gid: string) {
  const i = newForm.value.scope_group_ids.indexOf(gid)
  if (i >= 0) newForm.value.scope_group_ids.splice(i, 1)
  else newForm.value.scope_group_ids.push(gid)
}

// ---- 按策略分组（组内按创建时间倒序，组间按最近创建倒序） ----
const strategyGroups = computed(() => {
  const map = new Map<string, { strategyId: string; name: string; items: BacktestResponse[]; runningCount: number; failedCount: number }>()
  for (const bt of backtests.value) {
    const key = bt.strategy_id
    if (!map.has(key)) map.set(key, { strategyId: key, name: bt.strategy_name || key.slice(0, 8), items: [], runningCount: 0, failedCount: 0 })
    const g = map.get(key)!
    g.items.push(bt)
    if (bt.status === 'running' || bt.status === 'pending') g.runningCount++
    if (bt.status === 'failed') g.failedCount++
  }
  const arr = [...map.values()]
  for (const g of arr) {
    g.items.sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    g.name = g.items[0].strategy_name || g.strategyId.slice(0, 8)
  }
  arr.sort((a, b) => (a.items[0].created_at < b.items[0].created_at ? 1 : -1))
  return arr
})

const hasActive = computed(() => backtests.value.some(b => b.status === 'running' || b.status === 'pending'))
let pollTimer: number | null = null

function toggleGroup(id: string) {
  const s = new Set(expandedGroupIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  expandedGroupIds.value = s
}

function startPolling() {
  if (pollTimer != null || !hasActive.value) return
  pollTimer = window.setInterval(loadBacktests, 5000)
}
function stopPolling() {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadBacktests() {
  loading.value = true
  try {
    const { data } = await api.get<BacktestResponse[]>('/backtests')
    backtests.value = data
  } finally {
    loading.value = false
    if (hasActive.value) startPolling()
    else stopPolling()
  }
}

async function loadStrategies() {
  const { data } = await api.get<StrategyResponse[]>('/strategies')
  strategies.value = data
}

async function loadPooledAssets() {
  try {
    const { data } = await api.get<ResearchAsset[]>('/research/assets?status=pooled')
    pooledAssets.value = data
    pooledLoadError.value = ''
  } catch (e) {
    pooledAssets.value = []
    // 不再静默吞错：后端现已支持空 universe 自动展开为全部入池，但要让用户知道列表没加载到
    pooledLoadError.value = `入池标的列表加载失败（不影响回测，后端将自动使用全部入池标的）`
  }
  try {
    const { data } = await api.get<{ id: string; name: string; asset_ids: string[] }[]>('/research/assets/groups')
    assetGroups.value = data
  } catch {
    assetGroups.value = []
  }
}

async function createBacktest() {
  creating.value = true
  createError.value = ''
  try {
    const strat = strategies.value.find(s => s.id === newForm.value.strategy_id)
    const groupIds = newForm.value.scope_group_ids
    if (!groupIds.length) {
      createError.value = '请至少选择一个标的组合'
      return
    }
    await api.post('/backtests', {
      strategy_id: newForm.value.strategy_id,
      strategy_version: strat?.version ?? 1,
      params: {},
      universe: [],
      group_ids: groupIds,
      start_date: newForm.value.start_date,
      end_date: newForm.value.end_date,
      rebalance_freq: newForm.value.rebalance_freq,
    })
    showNew.value = false
    newForm.value.scope_group_ids = []
    await loadBacktests()
  } catch (e: unknown) {
    createError.value = apiErrorMessage(e)
  } finally {
    creating.value = false
  }
}

async function deleteBacktest(bt: BacktestResponse) {
  deleting.value = true
  try {
    await api.delete(`/backtests/${bt.id}`)
    backtests.value = backtests.value.filter(x => x.id !== bt.id)
    deleteId.value = null
  } catch (e: unknown) {
    createError.value = apiErrorMessage(e)
  } finally {
    deleting.value = false
  }
}

function apiErrorMessage(e: unknown): string {
  if (e && typeof e === 'object' && 'response' in e) {
    const detail = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail
    if (detail) return detail
  }
  return String(e)
}

function navigateTo(path: string) {
  router.push(path)
}

function fmtPct(v?: number) { return v != null ? `${(v * 100).toFixed(1)}%` : '-' }
function fmtNum(v?: number) { return v != null ? v.toFixed(2) : '-' }
function fmtDateTime(v?: string) { return v ? v.slice(0, 16) : '-' }
function freqLabel(f: string) {
  const m: Record<string, string> = { monthly: '月度', weekly: '周度', daily: '每日' }
  return m[f] || f
}
function metricClass(v?: number) {
  if (v == null) return 'text-text-muted'
  return v >= 0 ? 'text-income-color' : 'text-expense-color'
}
function statusClass(s: string) {
  const m = { done: 'bg-income-bg text-income-color', running: 'bg-blue-100 text-blue-700', failed: 'bg-expense-bg text-expense-color', pending: 'bg-gray-100 text-gray-500' }
  return m[s as keyof typeof m] || ''
}
function statusLabel(s: string) {
  const m = { done: '完成', running: '运行中', failed: '失败', pending: '等待' }
  return m[s as keyof typeof m] || s
}

onMounted(() => { loadBacktests(); loadStrategies(); loadPooledAssets() })
onUnmounted(stopPolling)
</script>
