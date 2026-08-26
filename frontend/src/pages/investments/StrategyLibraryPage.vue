<template>
  <div class="p-6">
    <!-- Sub-tab navigation -->
    <div class="flex gap-2 mb-4 border-b border-border-default">
      <button v-for="t in subTabs" :key="t.key" @click="setSubTab(t.key)"
        :class="['px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
          activeSubTab === t.key ? 'border-accent-primary text-accent-primary' : 'border-transparent text-text-secondary hover:text-text-primary']">
        {{ t.label }}
      </button>
    </div>

    <!-- 策略列表 -->
    <div v-show="activeSubTab === 'strategy'">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">策略</h2>
        <div class="flex items-center gap-3">
          <select v-model="folderFilter" class="px-2 py-1.5 text-xs border border-border-default rounded-md">
            <option value="">全部分类</option>
            <option v-for="f in folderNames" :key="f" :value="f">{{ f }}</option>
            <option value="__none__">未分类</option>
            <option value="__archive__">收纳箱</option>
          </select>
          <select v-model="sortMode" class="px-2 py-1.5 text-xs border border-border-default rounded-md">
            <option value="created_at_desc">最新创建</option>
            <option value="created_at_asc">最早创建</option>
            <option value="name_asc">名称 A→Z</option>
          </select>
          <button @click="showImport = true" class="btn-primary"><Upload :size="14" /> 导入策略</button>
        </div>
      </div>

      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-3 py-2 font-medium">名称</th>
              <th class="px-3 py-2 font-medium text-right">最新回测</th>
              <th class="px-3 py-2 font-medium text-right">夏普</th>
              <th class="px-3 py-2 font-medium text-right">回撤</th>
              <th class="px-3 py-2 font-medium text-center">频率</th>
              <th class="px-3 py-2 font-medium text-center">版本</th>
              <th class="px-3 py-2 font-medium">分类</th>
              <th class="px-3 py-2 font-medium text-right">创建时间</th>
              <th class="px-3 py-2 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sortedStrategies" :key="s.id" class="border-t border-border-default hover:bg-bg-secondary">
              <td class="px-3 py-2">
                <div class="font-medium text-accent-primary">{{ s.name }}</div>
                <div v-if="s.factor_keys?.length" class="text-xs text-text-muted mt-0.5">因子: {{ s.factor_keys.join(', ') }}</div>
              </td>
              <td class="px-3 py-2 text-right text-xs" :class="metricClass(s.latest_backtest?.ann_return)">
                {{ fmtPct(s.latest_backtest?.ann_return) }}
              </td>
              <td class="px-3 py-2 text-right text-xs">{{ s.latest_backtest?.sharpe?.toFixed(2) ?? '—' }}</td>
              <td class="px-3 py-2 text-right text-xs" :class="metricClass(s.latest_backtest?.max_drawdown)">
                {{ fmtPct(s.latest_backtest?.max_drawdown) }}
              </td>
              <td class="px-3 py-2 text-center text-xs">{{ s.rebalance_freq }}</td>
              <td class="px-3 py-2 text-center text-xs text-text-muted">v{{ s.version }}</td>
              <td class="px-3 py-2 text-xs text-text-secondary">
                <button @click.stop="startMove(s)" class="hover:text-accent-primary">{{ s.folder || '—' }}</button>
              </td>
              <td class="px-3 py-2 text-right text-xs text-text-muted">{{ fmtDate(s.created_at) }}</td>
              <td class="px-3 py-2 text-right">
                <button v-if="!s.is_builtin && activeStrategy?.strategy_id !== s.id" @click="activateStrategy(s)" class="px-2 py-1 text-xs rounded bg-accent-primary text-white hover:bg-accent-hover">激活</button>
                <span v-if="activeStrategy?.strategy_id === s.id" class="px-2 py-1 text-xs rounded bg-income-bg text-income-color font-medium">● 已激活</span>
              </td>
            </tr>
            <tr v-if="!loading && sortedStrategies.length === 0">
              <td colspan="9" class="px-4 py-12 text-center text-text-muted">暂无策略，点击右上角导入</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Move-to-folder inline editor -->
      <div v-if="movingStrategy" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click="movingStrategy = null">
        <div class="bg-white rounded-lg p-4 shadow-lg w-80" @click.stop>
          <div class="text-sm font-medium mb-2">移动「{{ movingStrategy.name }}」到分类</div>
          <input v-model="moveTarget" type="text" list="folder-list" placeholder="输入分类名（如：动量类、归档）"
            class="w-full px-3 py-2 text-sm border border-border-default rounded-md mb-3" @keyup.enter="doMove" />
          <datalist id="folder-list">
            <option v-for="f in folderNames" :key="f" :value="f" />
          </datalist>
          <div class="flex gap-2">
            <button @click="doMove" class="btn-primary flex-1">确认</button>
            <button @click="movingStrategy = null" class="btn-secondary flex-1">取消</button>
          </div>
        </div>
      </div>

      <!-- Import modal: file upload + paste + auto-parse -->
      <BaseModal v-if="showImport" title="导入策略" @close="showImport = false" width="max-w-2xl">
        <div class="space-y-4">
          <!-- File upload -->
          <div>
            <label class="block text-sm font-medium mb-1">选择 .py 文件</label>
            <input type="file" accept=".py" @change="onFileSelect" ref="fileInput"
              class="w-full text-sm text-text-secondary file:mr-3 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-accent-primary file:text-white" />
            <div class="text-xs text-text-muted mt-1">或直接粘贴代码到下方文本框</div>
          </div>
          <!-- Code + auto-parse -->
          <div>
            <div class="flex items-center justify-between mb-1">
              <label class="text-sm font-medium">策略代码</label>
              <button v-if="importForm.code" @click="autoParse" :disabled="parsing"
                class="text-xs text-accent-primary hover:underline">{{ parsing ? '解析中...' : '从注释自动识别元信息' }}</button>
            </div>
            <textarea v-model="importForm.code" rows="12"
              class="w-full px-3 py-2 text-sm font-mono border border-border-default rounded-md focus:outline-none focus:ring-1 focus:ring-accent-primary"
              :placeholder="codePlaceholder"></textarea>
          </div>
          <!-- Metadata preview (auto-filled by parse) -->
          <div v-if="importParsed" class="grid grid-cols-2 gap-3 bg-bg-secondary rounded-md p-3">
            <div><span class="text-xs text-text-muted">名称</span><div class="text-sm">{{ importForm.name || '—' }}</div></div>
            <div><span class="text-xs text-text-muted">频率</span><div class="text-sm">{{ importForm.rebalance_freq || '—' }}</div></div>
            <div><span class="text-xs text-text-muted">版本</span><div class="text-sm">v{{ importForm.version || 1 }}</div></div>
            <div><span class="text-xs text-text-muted">因子</span><div class="text-sm">{{ importForm.factor_keys?.join(', ') || '—' }}</div></div>
            <div class="col-span-2"><span class="text-xs text-text-muted">逻辑</span><div class="text-sm text-text-secondary">{{ importForm.description?.slice(0, 120) }}</div></div>
          </div>
          <!-- Folder -->
          <div>
            <label class="block text-sm font-medium mb-1">分类（可选）</label>
            <input v-model="importForm.folder" list="folder-list" placeholder="如：动量类"
              class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
          </div>
          <div v-if="importError" class="text-sm text-expense-color bg-expense-bg px-3 py-2 rounded">{{ importError }}</div>
          <div v-if="importSuccess" class="text-sm text-income-color bg-income-bg px-3 py-2 rounded">{{ importSuccess }}</div>
          <button @click="doImport" :disabled="importing || !importForm.code"
            class="btn-primary w-full disabled:opacity-50"><Upload :size="14" /> {{ importing ? '导入中...' : '导入策略' }}</button>
          <div class="text-xs text-text-muted bg-bg-secondary rounded-md px-3 py-2">
            策略需继承 <code class="font-mono">finkit_strategy.Strategy</code> 基类并实现 <code class="font-mono">target_weights(ctx, date)</code>。
            文件头注释格式：<code class="font-mono">名称：xxx / 频率：monthly / 版本：1 / 因子：gold,equity</code>，分隔线 <code>---</code> 后是代码。完整规范见 <code>docs/STRATEGY_API.md</code>。
          </div>
        </div>
      </BaseModal>
    </div>

    <!-- 回测子tab -->
    <div v-show="activeSubTab === 'backtest'">
      <BacktestList />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Upload } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import BaseModal from '@/components/common/BaseModal.vue'
import BacktestList from './BacktestListPage.vue'
import type { StrategyResponse, ActiveStrategyResponse } from '@/types'

const api = useApi()
const route = useRoute()
const router = useRouter()
const subTabs = [
  { key: 'strategy' as const, label: '策略' },
  { key: 'backtest' as const, label: '回测' },
]
const activeSubTab = ref<'strategy' | 'backtest'>('strategy')
const folderFilter = ref('')
const sortMode = ref('created_at_desc')

function setSubTab(t: 'strategy' | 'backtest') {
  activeSubTab.value = t
  router.replace({ query: { ...route.query, sub: t === 'backtest' ? 'backtest' : undefined } })
}
if (route.query.sub === 'backtest') activeSubTab.value = 'backtest'
watch(() => route.query.sub, (val) => {
  const v = Array.isArray(val) ? val[0] : val
  activeSubTab.value = v === 'backtest' ? 'backtest' : 'strategy'
})

const strategies = ref<StrategyResponse[]>([])
const activeStrategy = ref<ActiveStrategyResponse | null>(null)
const loading = ref(false)
const showImport = ref(false)
const importing = ref(false)
const importError = ref('')
const importSuccess = ref('')
const parsing = ref(false)
const importParsed = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const importForm = ref({ name: '', code: '', description: '', rebalance_freq: 'monthly', version: 1, factor_keys: [] as string[], folder: '' })

const movingStrategy = ref<StrategyResponse | null>(null)
const moveTarget = ref('')

const codePlaceholder = `策略名称：黄金双均线择时
策略逻辑：快线上穿慢线金叉买入...
频率：monthly
版本：1
因子：gold,equity
---
from finkit_strategy import Strategy, StrategyContext

class MyStrategy(Strategy):
    ...`

const folderNames = computed(() => [...new Set(strategies.value.map(s => s.folder).filter((f): f is string => !!f))])

const sortedStrategies = computed(() => {
  let list = [...strategies.value]
  if (folderFilter.value === '__none__') list = list.filter(s => !s.folder)
  else if (folderFilter.value === '__archive__') list = list.filter(s => s.folder === '收纳箱' || s.folder === '归档')
  else if (folderFilter.value) list = list.filter(s => s.folder === folderFilter.value)
  if (sortMode.value === 'created_at_desc') list.sort((a, b) => b.created_at.localeCompare(a.created_at))
  else if (sortMode.value === 'created_at_asc') list.sort((a, b) => a.created_at.localeCompare(b.created_at))
  else if (sortMode.value === 'name_asc') list.sort((a, b) => a.name.localeCompare(b.name))
  return list
})

async function loadStrategies() {
  loading.value = true
  try {
    const res = await api.get<StrategyResponse[]>('/strategies')
    strategies.value = res.data
  } finally { loading.value = false }
}

async function loadActive() {
  try {
    const res = await api.get<ActiveStrategyResponse | null>('/strategies/active')
    activeStrategy.value = res.data
  } catch { activeStrategy.value = null }
}

function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    importForm.value.code = String(reader.result || '')
    autoParse()
  }
  reader.readAsText(file)
}

async function autoParse() {
  if (!importForm.value.code) return
  parsing.value = true
  try {
    const res = await api.post<any>('/strategies/parse-docstring', { code: importForm.value.code })
    const d = res.data
    if (d.name) importForm.value.name = d.name
    if (d.description) importForm.value.description = d.description
    if (d.rebalance_freq) importForm.value.rebalance_freq = d.rebalance_freq
    if (d.version) importForm.value.version = d.version
    if (d.factor_keys) importForm.value.factor_keys = d.factor_keys
    importParsed.value = true
  } catch { /* parse failure is non-fatal */ }
  finally { parsing.value = false }
}

async function doImport() {
  importing.value = true
  importError.value = ''
  importSuccess.value = ''
  try {
    const res = await api.post<any>('/strategies/import', {
      name: importForm.value.name,
      code: importForm.value.code,
      description: importForm.value.description,
      params_schema: {},
      rebalance_freq: importForm.value.rebalance_freq,
      factor_keys: importForm.value.factor_keys,
      folder: importForm.value.folder || undefined,
    })
    const result = res.data
    importSuccess.value = `策略已${result.status === 'updated' ? '更新' : '导入'}（v${result.version}）`
    importForm.value = { name: '', code: '', description: '', rebalance_freq: 'monthly', version: 1, factor_keys: [], folder: '' }
    importParsed.value = false
    if (fileInput.value) fileInput.value.value = ''
    await loadStrategies()
    setTimeout(() => { showImport.value = false; importSuccess.value = '' }, 1500)
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || String(e)
  } finally { importing.value = false }
}

function startMove(s: StrategyResponse) {
  movingStrategy.value = s
  moveTarget.value = s.folder || ''
}

async function doMove() {
  if (!movingStrategy.value) return
  try {
    await api.post(`/strategies/${movingStrategy.value.id}/move`, { folder: moveTarget.value || null })
    movingStrategy.value.folder = moveTarget.value || undefined
    movingStrategy.value = null
    await loadStrategies()
  } catch { /* ignore */ }
}

async function activateStrategy(s: StrategyResponse) {
  await api.post('/strategies/active', { strategy_id: s.id, version: s.version, params: {} })
  await loadActive()
}

function fmtPct(v?: number | null) { return v != null ? `${(v * 100).toFixed(1)}%` : '—' }
function fmtDate(v?: string) { return v ? v.slice(0, 10) : '—' }
function metricClass(v?: number | null) { return v == null ? 'text-text-muted' : v >= 0 ? 'text-income-color' : 'text-expense-color' }

onMounted(() => { loadStrategies(); loadActive() })
</script>
