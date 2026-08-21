<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">回测</h2>
      <button @click="showNew = true" class="btn-primary">新建回测</button>
    </div>

    <!-- 状态筛选 -->
    <div class="flex gap-2 mb-4">
      <button v-for="s in ['all', 'done', 'running', 'failed']" :key="s"
        @click="filterStatus = s"
        :class="['px-3 py-1 text-xs rounded', filterStatus === s ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary']">
        {{ s === 'all' ? '全部' : s }}
      </button>
    </div>

    <!-- 回测列表 -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">策略</th>
            <th class="px-3 py-2 font-medium text-center">版本</th>
            <th class="px-3 py-2 font-medium">区间</th>
            <th class="px-3 py-2 font-medium text-center">频率</th>
            <th class="px-3 py-2 font-medium text-right">年化收益</th>
            <th class="px-3 py-2 font-medium text-right">夏普</th>
            <th class="px-3 py-2 font-medium text-right">最大回撤</th>
            <th class="px-3 py-2 font-medium text-center">状态</th>
            <th class="px-3 py-2 font-medium text-right">创建时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="bt in filteredBacktests" :key="bt.id"
            @click="navigateTo(`/investments/backtests/${bt.id}`)"
            class="border-t border-border-default cursor-pointer hover:bg-bg-tertiary">
            <td class="px-3 py-2 font-medium">{{ bt.strategy_id }}</td>
            <td class="px-3 py-2 text-center text-xs">v{{ bt.strategy_version }}</td>
            <td class="px-3 py-2 text-xs text-text-secondary">{{ bt.start_date }} → {{ bt.end_date }}</td>
            <td class="px-3 py-2 text-center text-xs">{{ bt.rebalance_freq }}</td>
            <td class="px-3 py-2 text-right" :class="metricClass(bt.results?.metrics?.ann_return)">
              {{ fmtPct(bt.results?.metrics?.ann_return) }}
            </td>
            <td class="px-3 py-2 text-right">{{ fmtNum(bt.results?.metrics?.sharpe) }}</td>
            <td class="px-3 py-2 text-right" :class="metricClass(bt.results?.metrics?.max_drawdown)">
              {{ fmtPct(bt.results?.metrics?.max_drawdown) }}
            </td>
            <td class="px-3 py-2 text-center">
              <span :class="statusClass(bt.status)" class="px-1.5 py-0.5 text-xs rounded">
                {{ statusLabel(bt.status) }}
              </span>
            </td>
            <td class="px-3 py-2 text-right text-xs text-text-muted">{{ fmtDate(bt.created_at) }}</td>
          </tr>
          <tr v-if="!backtests.length">
            <td colspan="9" class="px-4 py-8 text-center text-text-muted">暂无回测记录</td>
          </tr>
        </tbody>
      </table>
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
            <option value="monthly">月度</option>
            <option value="weekly">周度</option>
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '@/composables/useApi'
import BaseModal from '@/components/common/BaseModal.vue'
import type { BacktestResponse, StrategyResponse, ResearchAsset } from '@/types'

const api = useApi()
const router = useRouter()
const backtests = ref<BacktestResponse[]>([])
const strategies = ref<StrategyResponse[]>([])
const pooledAssets = ref<ResearchAsset[]>([])
const loading = ref(false)
const showNew = ref(false)
const creating = ref(false)
const createError = ref('')
const filterStatus = ref('all')

const newForm = ref({
  strategy_id: '',
  strategy_version: 1,
  start_date: '',
  end_date: '',
  rebalance_freq: 'monthly',
  universe: [] as string[],
  params: {},
})

const filteredBacktests = computed(() => {
  if (filterStatus.value === 'all') return backtests.value
  return backtests.value.filter(b => b.status === filterStatus.value)
})

async function loadBacktests() {
  loading.value = true
  try {
    const { data } = await api.get<BacktestResponse[]>('/backtests')
    backtests.value = data
  } finally {
    loading.value = false
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
    newForm.value.universe = data.map(a => a.id)
  } catch {
    pooledAssets.value = []
  }
}

async function createBacktest() {
  creating.value = true
  createError.value = ''
  try {
    const strat = strategies.value.find(s => s.id === newForm.value.strategy_id)
    await api.post('/backtests', {
      strategy_id: newForm.value.strategy_id,
      strategy_version: strat?.version ?? 1,
      params: {},
      universe: newForm.value.universe,
      start_date: newForm.value.start_date,
      end_date: newForm.value.end_date,
      rebalance_freq: newForm.value.rebalance_freq,
    })
    showNew.value = false
    await loadBacktests()
  } catch (e: unknown) {
    createError.value = apiErrorMessage(e)
  } finally {
    creating.value = false
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
function fmtDate(v?: string) { return v ? v.slice(0, 10) : '-' }
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
</script>
