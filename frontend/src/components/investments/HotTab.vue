<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">热点</h2>
      <button @click="load" :disabled="loading" class="btn-secondary text-xs">
        {{ loading ? '计算中…' : '刷新' }}
      </button>
    </div>

    <div v-if="loadError" class="mb-4 px-3 py-2 bg-expense-bg text-expense-color text-sm rounded">{{ loadError }}</div>

    <!-- 持仓层（每日自动更新） -->
    <div class="bg-white rounded-lg shadow-sm p-4 mb-6">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-medium text-sm">持仓异动
          <span class="text-xs text-text-muted font-normal">· 每日随应用启动自动更新</span>
        </h3>
        <span v-if="hot?.holdings?.data_as_of" class="text-xs text-text-muted">数据截至 {{ hot.holdings.data_as_of }}</span>
      </div>
      <table v-if="hot?.holdings?.items?.length" class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-1.5 font-medium">标的</th>
            <th class="px-3 py-1.5 text-right font-medium">今日</th>
            <th class="px-3 py-1.5 text-right font-medium">近5日</th>
            <th class="px-3 py-1.5 text-right font-medium">近1月</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in hot.holdings.items" :key="h.symbol" class="border-t border-border-default">
            <td class="px-3 py-1.5"><span class="font-medium">{{ h.name }}</span>
              <span class="text-xs text-text-muted ml-1">{{ h.symbol }}</span></td>
            <td class="px-3 py-1.5 text-right font-mono" :class="pctCls(h.ret_1d)">{{ pct(h.ret_1d) }}</td>
            <td class="px-3 py-1.5 text-right font-mono" :class="pctCls(h.ret_5d)">{{ pct(h.ret_5d) }}</td>
            <td class="px-3 py-1.5 text-right font-mono" :class="pctCls(h.ret_21d)">{{ pct(h.ret_21d) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="text-xs text-text-muted py-3 text-center">当前没有持仓</div>
    </div>

    <!-- 全池层（截至最近全量更新） -->
    <div class="bg-white rounded-lg shadow-sm p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-medium text-sm">全市场异动
          <span class="text-xs text-text-muted font-normal">· 全部入池标的</span>
        </h3>
        <span v-if="hot?.pool?.data_as_of" class="text-xs text-text-muted">数据截至 {{ hot.pool.data_as_of }}</span>
      </div>
      <div v-if="hot?.pool?.stale_note" class="px-3 py-2 mb-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-700">
        ⚠ {{ hot.pool.stale_note }}
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="board in boards" :key="board.title">
          <h4 class="text-xs text-text-secondary mb-1">{{ board.title }}</h4>
          <ol class="text-sm">
            <li v-for="(row, i) in board.rows" :key="row.symbol"
              class="flex items-center justify-between py-1 border-t border-border-default">
              <span class="truncate">
                <span class="text-text-muted mr-1">{{ i + 1 }}.</span>
                <span class="font-medium">{{ row.name?.slice(0, 14) }}</span>
                <span class="text-xs text-text-muted ml-1">{{ row.symbol }}</span>
              </span>
              <span class="font-mono text-right" :class="row.value >= 0 ? 'text-expense-color' : 'text-income-color'">
                {{ (row.value * 100).toFixed(0) }}%
              </span>
            </li>
            <li v-if="!board.rows.length" class="text-text-muted py-2 text-xs">暂无数据</li>
          </ol>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApi } from '@/composables/useApi'

const api = useApi()
const hot = ref<any>(null)
const loading = ref(false)
const loadError = ref('')

const boards = computed(() => [
  { title: '近1月涨幅榜', rows: hot.value?.pool?.movers_21d || [] },
  { title: '近3月涨幅榜', rows: hot.value?.pool?.movers_63d || [] },
  { title: '近1年涨幅榜', rows: hot.value?.pool?.movers_252d || [] },
  { title: '近1年夏普榜', rows: hot.value?.pool?.sharpe_1y || [] },
])

function pct(v: number | null | undefined): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : '—'
}
function pctCls(v: number | null | undefined): string {
  if (v == null) return ''
  return v >= 0 ? 'text-expense-color' : 'text-income-color'
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await api.get('/research/assets/hot')
    hot.value = data
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
