<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <div class="flex gap-2">
        <button @click="activeTab = 'library'" :class="tabCls('library')">因子库</button>
        <button @click="activeTab = 'matrix'" :class="tabCls('matrix')">暴露矩阵</button>
        <button @click="activeTab = 'contribution'" :class="tabCls('contribution')">贡献分析</button>
      </div>
      <div class="flex gap-2">
        <button v-if="activeTab === 'library'" @click="refreshAll" :disabled="refreshing" class="btn-secondary">
          <RefreshCw :size="14" :class="refreshing ? 'animate-spin' : ''" /> 刷新全部
        </button>
        <button v-if="activeTab === 'library'" @click="openAgentModal" class="btn-primary">
          Agent 构建因子
        </button>
        <button v-if="activeTab === 'matrix'" @click="recomputeExposures" :disabled="recomputing" class="btn-secondary">
          <RefreshCw :size="14" :class="recomputing ? 'animate-spin' : ''" /> 重算暴露
        </button>
      </div>
    </div>

    <!-- 因子库 tab -->
    <div v-if="activeTab === 'library'" class="bg-white rounded-lg shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">名称</th>
            <th class="px-3 py-2 font-medium">类别</th>
            <th class="px-3 py-2 font-medium">代理</th>
            <th class="px-3 py-2 font-medium text-right">最新值</th>
            <th class="px-3 py-2 font-medium text-right">最新日期</th>
            <th class="px-3 py-2 font-medium text-right">数据行</th>
            <th class="px-3 py-2 font-medium text-center">状态</th>
            <th class="px-3 py-2 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in factors" :key="f.id" class="border-t border-border-default">
            <td class="px-3 py-2">
              <div class="font-medium text-text-primary">{{ f.name }}</div>
              <div class="text-xs text-text-muted">{{ f.definition?.slice(0, 60) }}</div>
            </td>
            <td class="px-3 py-2">
              <span :class="categoryCls(f.category)">{{ f.category }}</span>
            </td>
            <td class="px-3 py-2 text-xs text-text-muted font-mono">{{ f.proxy_symbol || '—' }}</td>
            <td class="px-3 py-2 text-right">
              <span v-if="f.stats.latest_value != null" :class="colorClass(f.stats.latest_value)">
                {{ f.stats.latest_value >= 0 ? '+' : '' }}{{ (f.stats.latest_value * 100).toFixed(4) }}%
              </span>
              <span v-else class="text-text-muted">—</span>
            </td>
            <td class="px-3 py-2 text-right text-xs text-text-muted">{{ f.stats.latest_date || '—' }}</td>
            <td class="px-3 py-2 text-right text-xs text-text-muted">{{ f.stats.rows || 0 }}</td>
            <td class="px-3 py-2 text-center">
              <span v-if="f.is_market" class="px-1.5 py-0.5 text-xs rounded bg-income-bg text-income-color">市场</span>
              <span v-else-if="f.active" class="px-1.5 py-0.5 text-xs rounded bg-bg-tertiary text-text-secondary">活跃</span>
              <span v-else class="px-1.5 py-0.5 text-xs rounded bg-bg-tertiary text-text-muted">停用</span>
            </td>
            <td class="px-3 py-2 text-right whitespace-nowrap">
              <button @click="refreshFactor(f)" :disabled="syncing.has(f.id)" class="px-1.5 py-0.5 text-xs text-accent-primary hover:underline disabled:opacity-50">{{ syncing.has(f.id) ? '同步中' : '同步' }}</button>
              <button @click="toggleActive(f)" class="px-1.5 py-0.5 text-xs text-text-muted hover:underline">{{ f.active ? '停用' : '启用' }}</button>
            </td>
          </tr>
          <tr v-if="!loading && !factors.length">
            <td colspan="8" class="px-4 py-8 text-center text-text-muted">加载中…</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 暴露矩阵 tab -->
    <div v-if="activeTab === 'matrix'">
      <div class="flex gap-3 mb-3 items-center">
        <div class="text-sm text-text-secondary">月份：</div>
        <input v-model="matrixAsOf" type="month" class="px-3 py-1.5 text-sm border border-border-default rounded-md" />
        <button @click="loadMatrix" class="btn-secondary">查询</button>
        <div class="text-xs text-text-muted ml-auto">Beta 色阶：正红负绿 | 粗体 = |t|&gt;1.5 显著 | 岭回归标黄</div>
      </div>
      <div v-if="matrixLoading" class="text-sm text-text-muted py-4 text-center">加载中…</div>
      <div v-else-if="!matrix.assets?.length" class="text-sm text-text-muted py-4 text-center">暂无暴露数据，请先在标的池入池产品后重算</div>
      <div v-else class="bg-white rounded-lg shadow-sm overflow-auto">
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-2 font-medium sticky left-0 bg-bg-tertiary z-10">标的</th>
              <th v-for="ff in matrix.factors" :key="ff.id" class="px-3 py-2 font-medium text-center min-w-24">
                <div>{{ ff.name }}</div>
                <div class="text-xs font-normal text-text-muted">{{ ff.stats.latest_value != null ? (ff.stats.latest_value * 100).toFixed(2) + '%' : '—' }}</div>
              </th>
              <th class="px-3 py-2 font-medium text-center">R²</th>
              <th class="px-3 py-2 font-medium text-center">方法</th>
              <th class="px-3 py-2 font-medium text-center">样本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in matrix.assets" :key="row.asset_id" class="border-t border-border-default">
              <td class="px-3 py-2 sticky left-0 bg-white z-10">
                <div class="font-medium text-text-primary">{{ row.asset_name }}</div>
                <div class="text-xs text-text-muted">{{ row.symbol }}</div>
                <span v-if="row.is_money_market" class="text-xs text-text-muted">货币基金</span>
              </td>
              <td v-for="ff in matrix.factors" :key="ff.id" class="px-3 py-2 text-center">
                <div v-if="row.cells?.[ff.id]" :class="['font-medium', betaColor(row.cells[ff.id].beta)]">
                  {{ row.cells[ff.id].beta >= 0 ? '+' : '' }}{{ row.cells[ff.id].beta.toFixed(3) }}
                  <span v-if="row.cells[ff.id].significant" class="font-bold" title="|t|>1.5 显著">*</span>
                </div>
                <div v-else class="text-text-muted">—</div>
                <div v-if="row.cells?.[ff.id] && row.cells[ff.id].t_stat != null" class="text-xs text-text-muted">
                  t={{ row.cells[ff.id]?.t_stat?.toFixed(2) }}
                </div>
              </td>
              <td class="px-3 py-2 text-center">
                <span v-if="row.r2 != null" :class="r2Class(row.r2)">{{ row.r2.toFixed(3) }}</span>
                <span v-else class="text-text-muted">—</span>
              </td>
              <td class="px-3 py-2 text-center">
                <span v-if="row.method === 'ridge'" class="px-1 py-0.5 text-xs rounded bg-yellow-100 text-yellow-800">岭回归</span>
                <span v-else-if="row.method" class="text-xs text-text-muted">OLS</span>
                <span v-else class="text-text-muted">—</span>
              </td>
              <td class="px-3 py-2 text-center text-xs text-text-muted">{{ row.n_samples || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 贡献分析 tab -->
    <div v-if="activeTab === 'contribution'">
      <div class="flex gap-3 mb-3 items-center flex-wrap">
        <div class="text-sm text-text-secondary">标的</div>
        <select v-model="contribAsset" class="px-3 py-1.5 text-sm border border-border-default rounded-md min-w-48">
          <option value="">— 选择标的 —</option>
          <option v-for="a in pooledAssets" :key="a.value" :value="a.value">{{ a.label }}</option>
        </select>
        <div class="text-sm text-text-secondary">区间</div>
        <input v-model="contribStart" type="month" class="px-3 py-1.5 text-sm border border-border-default rounded-md" />
        <div class="text-text-muted">~</div>
        <input v-model="contribEnd" type="month" class="px-3 py-1.5 text-sm border border-border-default rounded-md" />
        <div class="text-sm text-text-secondary">视图</div>
        <select v-model="contribView" class="px-3 py-1.5 text-sm border border-border-default rounded-md">
          <option value="return">收益归因</option>
          <option value="risk">风险分解</option>
        </select>
        <button @click="loadContribution" :disabled="!contribAsset || !contribStart || !contribEnd" class="btn-secondary">分析</button>
      </div>

      <div v-if="contribLoading" class="text-sm text-text-muted py-4 text-center">加载中…</div>
      <div v-else-if="contribResult">
        <!-- 收益归因视图 -->
        <div v-if="contribResult.view === 'return'" class="bg-white rounded-lg shadow-sm overflow-hidden">
          <div class="p-4 border-b border-border-default flex gap-6 text-sm">
            <div><span class="text-text-muted">标的：</span><span class="font-medium">{{ contribResult.asset_name }}</span></div>
            <div><span class="text-text-muted">区间：</span>{{ contribResult.start }} ~ {{ contribResult.end }}</div>
            <div><span class="text-text-muted">天数：</span>{{ contribResult.n_days }}</div>
            <div><span class="text-text-muted">区间总收益：</span>
              <span :class="colorClass(contribResult.total_return ?? null)">{{ pct(contribResult.total_return ?? null) }}</span>
            </div>
          </div>
          <table class="w-full text-sm">
            <thead class="bg-bg-tertiary text-left">
              <tr>
                <th class="px-3 py-2 font-medium">因子</th>
                <th class="px-3 py-2 font-medium text-right">Beta</th>
                <th class="px-3 py-2 font-medium text-right">区间收益</th>
                <th class="px-3 py-2 font-medium text-right">贡献</th>
                <th class="px-3 py-2 font-medium text-right">占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in contribResult.items" :key="it.factor_id" class="border-t border-border-default">
                <td class="px-3 py-2 font-medium">{{ it.factor_name }}</td>
                <td class="px-3 py-2 text-right">{{ it.beta >= 0 ? '+' : '' }}{{ it.beta.toFixed(4) }}</td>
                <td class="px-3 py-2 text-right" :class="colorClass(it.contribution ?? null)">
                  {{ pct(it.contribution ?? null) }}
                </td>
                <td class="px-3 py-2 text-right" :class="colorClass(it.contribution ?? null)">
                  {{ pct(it.contribution ?? null) }}
                </td>
                <td class="px-3 py-2 text-right text-text-muted">
                  {{ contribResult.total_return && Math.abs(contribResult.total_return) > 1e-9
                    ? (((it.contribution ?? 0) / contribResult.total_return) * 100).toFixed(1) + '%' : '—' }}
                </td>
              </tr>
              <tr class="border-t-2 border-border-default font-medium bg-bg-secondary">
                <td class="px-3 py-2">Alpha（未解释）</td>
                <td class="px-3 py-2 text-right">—</td>
                <td class="px-3 py-2 text-right" :class="colorClass(contribResult.alpha)">{{ pct(contribResult.alpha) }}</td>
                <td class="px-3 py-2 text-right" :class="colorClass(contribResult.alpha)">{{ pct(contribResult.alpha) }}</td>
                <td class="px-3 py-2 text-right text-text-muted">—</td>
              </tr>
              <tr class="border-t-2 border-border-default font-medium">
                <td class="px-3 py-2">合计</td>
                <td class="px-3 py-2 text-right">—</td>
                <td class="px-3 py-2 text-right" :class="colorClass(contribResult.total_return)">{{ pct(contribResult.total_return) }}</td>
                <td class="px-3 py-2 text-right" :class="colorClass(contribResult.total_return)">{{ pct(contribResult.total_return) }}</td>
                <td class="px-3 py-2 text-right text-text-muted">—</td>
              </tr>
            </tbody>
          </table>
          <div class="px-4 py-2 bg-bg-secondary text-xs text-text-muted flex gap-4">
            <span v-if="contribResult.identity_residual != null">
              恒等校验：Σ贡献+α − 区间收益 = <span :class="Math.abs(contribResult.identity_residual) < 1e-6 ? 'text-income-color' : 'text-expense-color'">
                {{ (contribResult.identity_residual * 100).toFixed(4) }}%
              </span>
            </span>
            <span>暴露基准：{{ contribResult.as_of }}</span>
          </div>
        </div>

        <!-- 风险分解视图 -->
        <div v-if="contribResult.view === 'risk'" class="bg-white rounded-lg shadow-sm overflow-hidden">
          <div class="p-4 border-b border-border-default text-sm">
            <span class="text-text-muted">解释波动率：</span>
            <span class="font-medium">{{ ((contribResult.explained_vol || 0) * 100).toFixed(2) }}%</span>
          </div>
          <table class="w-full text-sm">
            <thead class="bg-bg-tertiary text-left">
              <tr>
                <th class="px-3 py-2 font-medium">因子</th>
                <th class="px-3 py-2 font-medium text-right">Beta</th>
                <th class="px-3 py-2 font-medium text-right">年化波动</th>
                <th class="px-3 py-2 font-medium text-right">风险贡献</th>
                <th class="px-3 py-2 font-medium text-right">占比</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in contribResult.items" :key="it.factor_id" class="border-t border-border-default">
                <td class="px-3 py-2 font-medium">{{ it.factor_name }}</td>
                <td class="px-3 py-2 text-right">{{ it.beta >= 0 ? '+' : '' }}{{ it.beta.toFixed(4) }}</td>
                <td class="px-3 py-2 text-right">{{ it.sigma_ann != null ? (it.sigma_ann * 100).toFixed(2) + '%' : '—' }}</td>
                <td class="px-3 py-2 text-right">{{ ((it.risk_contribution || 0) * 100).toFixed(1) }}%</td>
                <td class="px-3 py-2 text-right">
                  <div class="w-full bg-bg-tertiary rounded-full h-1.5">
                    <div class="bg-accent-primary h-1.5 rounded-full" :style="{ width: ((it.risk_contribution || 0) * 100).toFixed(1) + '%' }"></div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else class="text-sm text-text-muted py-4 text-center">选择标的和区间，点击"分析"</div>
    </div>

    <!-- Agent 构建因子弹窗 -->
    <BaseModal v-if="agentModal" :title="'Agent 构建因子'" @close="agentModal = false" width="max-w-lg">
      <div v-if="!agentResult && !agentError" class="space-y-4">
        <p class="text-sm text-text-secondary">用自然语言描述你想要的因子，例如"帮我加一个中证800的超额收益因子"或"加一个价值风格的价差因子"</p>
        <textarea v-model="agentPrompt" rows="4" class="w-full px-3 py-2 text-sm border border-border-default rounded-md" placeholder="描述你想要的因子…"></textarea>
        <button @click="agentGenerate" :disabled="agentGenerating || !agentPrompt.trim()" class="btn-primary w-full disabled:opacity-50">
          {{ agentGenerating ? '生成中…' : '生成因子定义' }}
        </button>
      </div>
      <div v-else-if="agentResult" class="space-y-4">
        <div class="text-sm font-medium mb-2">候选因子（请确认后入库）</div>
        <div class="bg-bg-secondary rounded-md p-3 text-sm space-y-1">
          <div><span class="text-text-muted">名称：</span>{{ agentResult.name }}</div>
          <div><span class="text-text-muted">类别：</span>{{ agentResult.category }}</div>
          <div><span class="text-text-muted">定义：</span>{{ agentResult.definition }}</div>
          <div><span class="text-text-muted">代理：</span>
            <span v-if="agentResult.config.type === 'proxy'">{{ agentResult.config.symbol }} ({{ agentResult.config.exchange }})</span>
            <span v-else-if="agentResult.config.type === 'spread'">
              多头 {{ agentResult.config.long?.symbol }} — 空头 {{ agentResult.config.short?.symbol }}
            </span>
          </div>
        </div>
        <div v-if="agentPreview" class="text-xs text-text-muted">
          <div>样本天数：{{ agentPreview.sample_days }} | 区间：{{ agentPreview.first_date }}~{{ agentPreview.last_date }}</div>
          <div v-if="agentPreview.latest_level">最新水平值：{{ agentPreview.latest_level }}</div>
        </div>
        <div v-if="agentPreviewError" class="text-xs text-expense-color">{{ agentPreviewError }}</div>
        <div class="flex gap-2">
          <button @click="agentConfirm" :disabled="agentConfirming" class="btn-primary flex-1 disabled:opacity-50">
            {{ agentConfirming ? '入库中…' : '确认入库' }}
          </button>
          <button @click="resetAgent" class="btn-secondary flex-1">重新生成</button>
        </div>
      </div>
      <div v-else-if="agentError" class="space-y-3">
        <div class="text-sm text-expense-color">{{ agentError }}</div>
        <button @click="resetAgent" class="btn-secondary w-full">重新生成</button>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useApi } from '@/composables/useApi'
import { RefreshCw } from 'lucide-vue-next'
import BaseModal from '@/components/common/BaseModal.vue'
import type { FactorResponse, ExposureMatrix, ContributionResult, AgentFactorCandidate, AgentPreviewResult } from '@/types'

const api = useApi()
const activeTab = ref<'library' | 'matrix' | 'contribution'>('library')

// ---- state ----
const factors = ref<FactorResponse[]>([])
const syncing = ref<Set<string>>(new Set())
const loading = ref(false)
const refreshing = ref(false)
const matrix = ref<ExposureMatrix>({ as_of: null, factors: [], assets: [] })
const matrixLoading = ref(false)
const matrixAsOf = ref('')
const recomputing = ref(false)
const pooledAssets = ref<Array<{ value: string; label: string }>>([])
const contribAsset = ref('')
const contribStart = ref('')
const contribEnd = ref('')
const contribView = ref<'return' | 'risk'>('return')
const contribResult = ref<ContributionResult | null>(null)
const contribLoading = ref(false)
const agentModal = ref(false)
const agentPrompt = ref('')
const agentGenerating = ref(false)
const agentConfirming = ref(false)
const agentResult = ref<AgentFactorCandidate | null>(null)
const agentPreview = ref<AgentPreviewResult | null>(null)
const agentPreviewError = ref('')
const agentError = ref('')

// ---- helpers ----
function tabCls(tab: string) {
  return ['px-4 py-2 text-sm rounded-md transition-colors',
    activeTab.value === tab ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']
}
function categoryCls(cat: string) {
  const m: Record<string, string> = {
    asset_class: 'px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-800',
    style: 'px-1.5 py-0.5 text-xs rounded bg-purple-100 text-purple-800',
    macro: 'px-1.5 py-0.5 text-xs rounded bg-green-100 text-green-800',
    custom: 'px-1.5 py-0.5 text-xs rounded bg-gray-100 text-gray-700',
  }
  return m[cat] || 'px-1.5 py-0.5 text-xs rounded bg-gray-100 text-gray-600'
}
function betaColor(beta: number) {
  if (beta > 0.5) return 'text-income-color'
  if (beta < -0.5) return 'text-expense-color'
  if (beta > 0) return 'text-yellow-600'
  if (beta < 0) return 'text-blue-600'
  return 'text-text-secondary'
}
function r2Class(r2: number) {
  if (r2 >= 0.6) return 'text-income-color'
  if (r2 >= 0.3) return 'text-blue-600'
  return 'text-text-muted'
}
function colorClass(v: number | null | undefined) {
  if (v == null) return 'text-text-muted'
  return v >= 0 ? 'text-income-color' : 'text-expense-color'
}
function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : (v * 100).toFixed(2) + '%'
}
function fmt4(n: number): string {
  return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 })
}

// ---- data loaders ----
async function loadFactors() {
  loading.value = true
  try {
    const data = (await api.get<FactorResponse[]>('/research/factors')).data
    factors.value = data
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  refreshing.value = true
  try {
    await api.post('/research/factors/refresh-all')
    await loadFactors()
  } finally {
    refreshing.value = false
  }
}

async function refreshFactor(f: FactorResponse) {
  syncing.value.add(f.id)
  try {
    await api.post(`/research/factors/${f.id}/refresh`)
    await loadFactors()
  } finally {
    syncing.value.delete(f.id)
  }
}

async function toggleActive(f: FactorResponse) {
  await api.put(`/research/factors/${f.id}`, { active: !f.active })
  await loadFactors()
}

async function loadMatrix() {
  matrixLoading.value = true
  try {
    const params: Record<string, string> = {}
    if (matrixAsOf.value) params.as_of = matrixAsOf.value + '-01'
    matrix.value = (await api.get<ExposureMatrix>('/research/factors/exposure-matrix', params)).data
    if (!matrixAsOf.value && matrix.value.as_of) {
      matrixAsOf.value = matrix.value.as_of!.slice(0, 7)
    }
  } finally {
    matrixLoading.value = false
  }
}

async function recomputeExposures() {
  recomputing.value = true
  try {
    await api.post('/research/factors/recompute-exposures')
    await loadMatrix()
  } finally {
    recomputing.value = false
  }
}

async function loadContribution() {
  if (!contribAsset.value || !contribStart.value || !contribEnd.value) return
  contribLoading.value = true
  contribResult.value = null
  try {
    contribResult.value = (await api.get('/research/factors/contribution', {
      params: {
        asset_id: contribAsset.value,
        start: contribStart.value + '-01',
        end: contribEnd.value + '-01',
        view: contribView.value,
      }
    })).data as ContributionResult
  } finally {
    contribLoading.value = false
  }
}

async function loadPooledAssets() {
  const assets = (await api.get<any[]>('/research/assets?status=pooled')).data as any[]
  pooledAssets.value = assets.map((a: any) => ({ value: a.id, label: `${a.name} (${a.symbol})` }))
}

// ---- agent ----
async function agentGenerate() {
  agentGenerating.value = true
  agentError.value = ''
  agentResult.value = null
  agentPreview.value = null
  agentPreviewError.value = ''
  try {
    const candidate = (await api.post<AgentFactorCandidate>('/research/factors/agent/generate', { prompt: agentPrompt.value })).data
    agentResult.value = candidate
    await agentPreviewCandidate(candidate)
  } catch (e: any) {
    agentError.value = e?.message || String(e)
  } finally {
    agentGenerating.value = false
  }
}

async function agentPreviewCandidate(c: AgentFactorCandidate) {
  try {
    agentPreview.value = (await api.post<AgentPreviewResult>('/research/factors/agent/preview', { candidate: c })).data
    agentPreviewError.value = ''
  } catch (e: any) {
    agentPreviewError.value = e?.message || String(e)
    agentPreview.value = null
  }
}

async function agentConfirm() {
  if (!agentResult.value) return
  agentConfirming.value = true
  try {
    await api.post('/research/factors/agent/confirm', { candidate: agentResult.value })
    agentModal.value = false
    agentResult.value = null
    agentPrompt.value = ''
    await loadFactors()
  } finally {
    agentConfirming.value = false
  }
}

function resetAgent() {
  agentResult.value = null
  agentPreview.value = null
  agentError.value = ''
  agentPreviewError.value = ''
}

function openAgentModal() {
  agentModal.value = true
  resetAgent()
}

onMounted(async () => {
  await loadFactors()
  await loadPooledAssets()
  // pre-load matrix
  await loadMatrix()
})
</script>
