<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-lg font-semibold">策略库</h2>
      <button @click="showImport = true" class="btn-primary text-sm">
        导入策略 (.py)
      </button>
    </div>

    <!-- 策略列表 -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">名称</th>
            <th class="px-3 py-2 font-medium">描述</th>
            <th class="px-3 py-2 font-medium text-center">频率</th>
            <th class="px-3 py-2 font-medium text-center">版本</th>
            <th class="px-3 py-2 font-medium text-center">内置</th>
            <th class="px-3 py-2 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in strategies" :key="s.id" class="border-t border-border-default hover:bg-bg-secondary">
            <td class="px-3 py-2 font-medium text-accent-primary">{{ s.name }}</td>
            <td class="px-3 py-2 text-text-secondary text-xs">{{ s.description?.slice(0, 80) }}</td>
            <td class="px-3 py-2 text-center text-xs">
              <span class="px-1.5 py-0.5 rounded text-xs" :class="s.rebalance_freq === 'monthly' ? 'bg-info-bg text-info' : 'bg-warning-bg text-warning'">
                {{ s.rebalance_freq }}
              </span>
            </td>
            <td class="px-3 py-2 text-center text-xs text-text-muted">v{{ s.version }}</td>
            <td class="px-3 py-2 text-center">
              <span v-if="s.is_builtin" class="px-1.5 py-0.5 text-xs rounded bg-income-bg text-income-color">内置</span>
            </td>
            <td class="px-3 py-2 text-right">
              <button v-if="!s.is_builtin" @click="activateStrategy(s)" class="px-2 py-1 text-xs rounded bg-accent-primary text-white hover:bg-accent-hover">
                激活
              </button>
            </td>
          </tr>
          <tr v-if="!loading && strategies.length === 0">
            <td colspan="6" class="px-4 py-12 text-center text-text-muted">
              暂无策略，点击右上角导入或使用内置策略
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="6" class="px-4 py-8 text-center text-text-muted">加载中...</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 当前策略信息 -->
    <div v-if="activeStrategy" class="mt-4 p-4 bg-bg-secondary rounded-lg border border-border-default">
      <div class="text-sm font-medium mb-2">当前激活策略</div>
      <div class="text-sm text-text-secondary">
        {{ activeStrategy.name }} (v{{ activeStrategy.version }}) · {{ activeStrategy.rebalance_freq }}
      </div>
    </div>

    <!-- 导入弹窗 -->
    <BaseModal v-if="showImport" title="导入策略" @close="showImport = false" width="max-w-2xl">
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1">策略名称</label>
          <input
            v-model="importForm.name"
            class="w-full px-3 py-2 text-sm border border-border-default rounded-md focus:outline-none focus:ring-1 focus:ring-accent-primary"
            placeholder="我的动量策略"
          />
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">策略代码 (.py)</label>
          <textarea
            v-model="importForm.code"
            rows="14"
            class="w-full px-3 py-2 text-sm font-mono border border-border-default rounded-md focus:outline-none focus:ring-1 focus:ring-accent-primary"
            placeholder="from finkit_strategy import Strategy, StrategyContext&#10;&#10;class MyStrategy(Strategy):&#10;    name = &quot;我的策略&quot;&#10;    description = &quot;&quot;&#10;    rebalance_freq = &quot;monthly&quot;&#10;    params_schema = {}&#10;&#10;    def target_weights(self, ctx, date):&#10;        # Return {asset_id: weight} or None&#10;        return {}"
          ></textarea>
        </div>
        <div v-if="importError" class="text-sm text-expense-color bg-expense-bg px-3 py-2 rounded">
          {{ importError }}
        </div>
        <div v-if="importSuccess" class="text-sm text-income-color bg-income-bg px-3 py-2 rounded">
          {{ importSuccess }}
        </div>
        <button
          @click="doImport"
          :disabled="importing || !importForm.name || !importForm.code"
          class="btn-primary w-full disabled:opacity-50"
        >
          {{ importing ? '导入中...' : '导入策略' }}
        </button>
      </div>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'
import BaseModal from '@/components/common/BaseModal.vue'
import type { StrategyResponse, ActiveStrategyResponse } from '@/types'

const api = useApi()
const strategies = ref<StrategyResponse[]>([])
const activeStrategy = ref<ActiveStrategyResponse | null>(null)
const loading = ref(false)
const showImport = ref(false)
const importing = ref(false)
const importError = ref('')
const importSuccess = ref('')
const importForm = ref({ name: '', code: '' })

async function loadStrategies() {
  loading.value = true
  try {
    const res = await api.get<StrategyResponse[]>('/strategies')
    strategies.value = res.data
  } finally {
    loading.value = false
  }
}

async function loadActive() {
  try {
    const res = await api.get<ActiveStrategyResponse | null>('/strategies/active')
    activeStrategy.value = res.data
  } catch {
    activeStrategy.value = null
  }
}

async function doImport() {
  importing.value = true
  importError.value = ''
  importSuccess.value = ''
  try {
    const res = await api.post<any>('/strategies/import', {
      name: importForm.value.name,
      code: importForm.value.code,
      description: '',
      params_schema: {},
      rebalance_freq: 'monthly',
    })
    const result = res.data
    importSuccess.value = `策略已${result.status === 'updated' ? '更新' : '导入'}（v${result.version}）`
    importForm.value = { name: '', code: '' }
    await loadStrategies()
    setTimeout(() => { showImport.value = false; importSuccess.value = '' }, 1500)
  } catch (e: any) {
    importError.value = e?.response?.data?.detail || String(e)
  } finally {
    importing.value = false
  }
}

async function activateStrategy(s: StrategyResponse) {
  await api.post('/strategies/active', {
    strategy_id: s.id,
    version: s.version,
    params: {},
  })
  await loadActive()
}

onMounted(() => { loadStrategies(); loadActive() })
</script>
