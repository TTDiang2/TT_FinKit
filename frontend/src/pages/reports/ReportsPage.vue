<template>
  <div class="p-6">
    <h1 class="text-xl font-bold mb-6">报表</h1>
    <div class="bg-white rounded-lg p-4 shadow-sm mb-4 flex flex-wrap gap-3 items-center">
      <select v-model="reportType" class="px-3 py-2 border border-border-default rounded-md text-sm">
        <option value="PL">利润表</option><option value="BS">资产负债表</option><option value="CF">现金流量表</option>
      </select>
      <select v-model="periodType" class="px-3 py-2 border border-border-default rounded-md text-sm">
        <option value="monthly">月报</option><option value="quarterly">季报</option><option value="annual">年报</option>
      </select>
      <input v-model.number="year" type="number" class="px-3 py-2 border border-border-default rounded-md text-sm w-24" />
      <span class="text-text-secondary">年</span>
      <template v-if="periodType === 'monthly'">
        <input v-model.number="month" type="number" min="1" max="12" class="px-3 py-2 border border-border-default rounded-md text-sm w-20" />
        <span class="text-text-secondary">月</span>
      </template>
      <template v-if="periodType === 'quarterly'">
        <select v-model.number="quarter" class="px-3 py-2 border border-border-default rounded-md text-sm w-20">
          <option :value="1">Q1</option><option :value="2">Q2</option><option :value="3">Q3</option><option :value="4">Q4</option>
        </select>
      </template>
      <button @click="generate" class="px-4 py-2 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">生成</button>
      <button @click="archive" class="px-4 py-2 border border-border-default text-sm rounded-md hover:bg-bg-tertiary">归档</button>
      <button @click="showExportModal = true" class="px-4 py-2 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover ml-auto">导出数据</button>
    </div>

    <div v-if="reportData && reportType === 'PL'" class="bg-white rounded-lg p-6 shadow-sm mb-6">
      <h2 class="text-lg font-bold mb-4 text-center">利润表</h2>
      <div class="text-sm text-text-secondary text-center mb-4">{{ reportData?.period || `${year}-${String(month).padStart(2, '0')}` }}</div>
      <table class="w-full text-sm">
        <tbody>
          <!-- 一、主营业务收入 -->
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">一、主营业务收入</td></tr>
          <tr v-for="item in (reportData.main_income || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right text-income-color">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">主营业务收入合计</td>
            <td class="px-4 py-2 text-right text-income-color">{{ sym }}{{ fmt(reportData.total_main_income) }}</td>
          </tr>
          <!-- 减：主营业务成本 -->
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">减：主营业务成本</td></tr>
          <tr v-for="item in (reportData.main_cost || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right text-expense-color">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">主营业务成本合计</td>
            <td class="px-4 py-2 text-right text-expense-color">{{ sym }}{{ fmt(reportData.total_main_cost) }}</td>
          </tr>
          <!-- 主营业务毛利 -->
          <tr class="border-t border-border-default font-bold bg-bg-tertiary">
            <td class="px-4 py-2">主营业务毛利</td>
            <td class="px-4 py-2 text-right" :class="(reportData.gross_profit ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(reportData.gross_profit) }} ({{ fmt(reportData.gross_margin) }}%)</td>
          </tr>
          <!-- 二、其他收入 -->
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">二、其他收入</td></tr>
          <tr v-for="item in (reportData.other_income || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right text-income-color">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">其他收入合计</td>
            <td class="px-4 py-2 text-right text-income-color">{{ sym }}{{ fmt(reportData.total_other_income) }}</td>
          </tr>
          <!-- 减：其他成本 -->
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">减：其他成本</td></tr>
          <tr v-for="item in (reportData.other_cost || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right text-expense-color">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">其他成本合计</td>
            <td class="px-4 py-2 text-right text-expense-color">{{ sym }}{{ fmt(reportData.total_other_cost) }}</td>
          </tr>
          <!-- 净利润 -->
          <tr class="border-t border-border-default font-bold bg-bg-tertiary">
            <td class="px-4 py-2">净利润</td>
            <td class="px-4 py-2 text-right" :class="(reportData.net_income ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(reportData.net_income) }} ({{ fmt(reportData.net_margin) }}%)</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="reportData && reportType === 'BS'" class="bg-white rounded-lg p-6 shadow-sm mb-6">
      <h2 class="text-lg font-bold mb-4 text-center">资产负债表</h2>
      <div class="text-sm text-text-secondary text-center mb-4">{{ reportData?.period || `${year}-${String(month).padStart(2, '0')}` }}</div>
      <div class="grid grid-cols-2 gap-6">
        <!-- 资产 -->
        <div>
          <h3 class="font-semibold mb-2 text-center bg-bg-secondary py-1">资产</h3>
          <table class="w-full text-sm">
            <tbody>
              <tr v-for="item in (reportData.assets || [])" :key="item.name" class="border-t border-border-default">
                <td class="px-4 py-2">{{ item.name }}</td>
                <td class="px-4 py-2 text-right">{{ sym }}{{ fmt(item.total) }}</td>
              </tr>
              <tr class="border-t border-border-default font-semibold bg-bg-tertiary">
                <td class="px-4 py-2">资产合计</td>
                <td class="px-4 py-2 text-right">{{ sym }}{{ fmt(reportData.total_assets) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 负债 + 权益 -->
        <div>
          <h3 class="font-semibold mb-2 text-center bg-bg-secondary py-1">负债与权益</h3>
          <table class="w-full text-sm">
            <tbody>
              <tr><td colspan="2" class="px-4 py-1 font-medium text-text-secondary">负债</td></tr>
              <tr v-for="item in (reportData.liabilities || [])" :key="item.name" class="border-t border-border-default">
                <td class="px-4 py-2 pl-4">{{ item.name }}</td>
                <td class="px-4 py-2 text-right text-expense-color">{{ sym }}{{ fmt(item.total) }}</td>
              </tr>
              <tr class="border-t border-border-default font-semibold">
                <td class="px-4 py-2 pl-4">负债合计</td>
                <td class="px-4 py-2 text-right text-expense-color">{{ sym }}{{ fmt(reportData.total_liabilities) }}</td>
              </tr>
              <tr><td colspan="2" class="px-4 py-1 font-medium text-text-secondary">权益（净资产）</td></tr>
              <tr v-for="item in (reportData.equity || [])" :key="item.name" class="border-t border-border-default">
                <td class="px-4 py-2 pl-4">{{ item.name }}</td>
                <td class="px-4 py-2 text-right text-income-color">{{ sym }}{{ fmt(item.total) }}</td>
              </tr>
              <tr class="border-t border-border-default font-semibold">
                <td class="px-4 py-2 pl-4">权益合计</td>
                <td class="px-4 py-2 text-right text-income-color">{{ sym }}{{ fmt(reportData.net_worth) }}</td>
              </tr>
              <tr class="border-t border-border-default font-semibold bg-bg-tertiary">
                <td class="px-4 py-2">负债与权益合计</td>
                <td class="px-4 py-2 text-right">{{ sym }}{{ fmt(reportData.total_liabilities_equity) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <!-- 验证行 -->
      <div class="mt-4 pt-4 border-t-2 border-border-default">
        <div class="flex justify-center gap-8 text-sm">
          <span>资产总计: <strong class="text-income-color">{{ sym }}{{ fmt(reportData.total_assets) }}</strong></span>
          <span>=</span>
          <span>负债与权益总计: <strong class="text-income-color">{{ sym }}{{ fmt(reportData.total_liabilities_equity) }}</strong></span>
        </div>
      </div>
    </div>

    <div v-if="reportData && reportType === 'CF'" class="bg-white rounded-lg p-6 shadow-sm mb-6">
      <h2 class="text-lg font-bold mb-4 text-center">现金流量表</h2>
      <div class="text-sm text-text-secondary text-center mb-4">{{ reportData?.period || `${year}-${String(month).padStart(2, '0')}` }}</div>
      <table class="w-full text-sm">
        <tbody>
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">经营活动</td></tr>
          <tr v-for="item in (reportData.operating || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right" :class="item.total >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">经营活动净现金流</td>
            <td class="px-4 py-2 text-right" :class="(reportData.operating_net ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(reportData.operating_net) }}</td>
          </tr>
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">投资活动</td></tr>
          <tr v-for="item in (reportData.investing || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right" :class="item.total >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">投资活动净现金流</td>
            <td class="px-4 py-2 text-right" :class="(reportData.investing_net ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(reportData.investing_net) }}</td>
          </tr>
          <tr><td colspan="2" class="px-4 py-2 font-semibold bg-bg-secondary">筹资活动</td></tr>
          <tr v-for="item in (reportData.financing || [])" :key="item.name" class="border-t border-border-default">
            <td class="px-4 py-2 pl-8">{{ item.name }}</td>
            <td class="px-4 py-2 text-right" :class="item.total >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(item.total) }}</td>
          </tr>
          <tr class="border-t border-border-default font-semibold">
            <td class="px-4 py-2">筹资活动净现金流</td>
            <td class="px-4 py-2 text-right" :class="(reportData.financing_net ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(reportData.financing_net) }}</td>
          </tr>
          <tr class="border-t border-border-default font-bold bg-bg-tertiary">
            <td class="px-4 py-2">现金净变动</td>
            <td class="px-4 py-2 text-right" :class="(reportData.net_change ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ sym }}{{ fmt(reportData.net_change) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="!reportData" class="bg-white rounded-lg p-6 shadow-sm mb-6 text-center text-text-muted">
      请先生成报表
    </div>

    <div class="bg-white rounded-lg shadow-sm">
      <div class="p-4 border-b border-border-default"><h2 class="font-semibold">历史归档</h2></div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr><th class="px-4 py-2 font-medium">类型</th><th class="px-4 py-2 font-medium">期间</th><th class="px-4 py-2 font-medium">时间</th><th class="px-4 py-2 font-medium">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in archives" :key="a.id" class="border-t border-border-default">
            <td class="px-4 py-2">{{ a.report_type }}</td>
            <td class="px-4 py-2">{{ a.period_start }} ~ {{ a.period_end }}</td>
            <td class="px-4 py-2 text-text-muted">{{ a.generated_at }}</td>
            <td class="px-4 py-2">
              <button @click="loadArchive(a)" class="text-text-secondary hover:text-accent-primary mr-3">查看</button>
              <button @click="deleteArchive(a.id)" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
            </td>
          </tr>
          <tr v-if="!archives.length"><td colspan="4" class="px-4 py-6 text-center text-text-muted">暂无归档</td></tr>
        </tbody>
      </table>
    </div>

    <BaseModal v-if="showExportModal" title="导出数据" @close="showExportModal = false">
      <div class="space-y-4">
        <p class="text-sm text-text-secondary">导出你的财务数据包（含数据 + AI分析指南），可用于外部AI工具分析。</p>
        <div v-if="archives.length">
          <h4 class="text-sm font-medium mb-2">选择要包含的已归档报表：</h4>
          <div class="space-y-1 max-h-48 overflow-y-auto">
            <label v-for="a in archives" :key="a.id" class="flex items-center gap-2 py-1 px-2 hover:bg-bg-secondary rounded cursor-pointer">
              <input type="checkbox" :value="a.id" v-model="selectedArchiveIds" class="w-4 h-4" />
              <span class="text-sm">{{ a.report_type === 'PL' ? '利润表' : a.report_type === 'BS' ? '资产负债表' : '现金流量表' }}</span>
              <span class="text-xs text-text-muted">{{ a.period_start }}</span>
            </label>
          </div>
        </div>
        <p class="text-xs text-text-muted">导出内容：用户画像、近12月收支趋势、当月报表、投资组合、近30天交易 + AI分析指南(.md)</p>
      </div>
      <template #footer>
        <button @click="showExportModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="exportAiPackage" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">导出</button>
      </template>
    </BaseModal>
  </div>
</template>
<script setup lang="ts">
import { ref, computed } from 'vue'
import { Trash2 } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import { useSettingsStore } from '@/stores/settings'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'

const api = useApi()
const settingsStore = useSettingsStore()
const { show } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)

const year = ref(new Date().getFullYear())
const month = ref(new Date().getMonth() + 1)
const quarter = ref(Math.ceil((new Date().getMonth() + 1) / 3))
const periodType = ref('monthly')
const reportType = ref('PL')
const reportData = ref<any>(null)
const archives = ref<any[]>([])
const showExportModal = ref(false)
const selectedArchiveIds = ref<string[]>([])
function fmt(n: number | undefined): string { return (n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

async function generate() {
  try {
    const params: any = { year: year.value, period_type: periodType.value }
    if (periodType.value === 'monthly') params.month = month.value
    if (periodType.value === 'quarterly') params.quarter = quarter.value
    const res = await api.get(`/reports/${reportType.value.toLowerCase()}`, { params })
    reportData.value = res.data
  } catch (e: any) { show(e.response?.data?.detail || '生成失败', 'error') }
}

async function archive() {
  if (!reportData.value) { show('请先生成报表', 'warning'); return }
  try {
    await api.post('/reports/archives', {
      report_type: reportType.value,
      period_start: `${year.value}-${String(month.value).padStart(2, '0')}-01`,
      period_end: `${year.value}-${String(month.value).padStart(2, '0')}-31`,
      content: JSON.stringify(reportData.value)
    })
    show('已归档', 'success')
    loadArchives()
  } catch (e: any) { show(e.response?.data?.detail || '归档失败', 'error') }
}

async function loadArchives() {
  const res = await api.get('/reports/archives')
  archives.value = res.data
}

async function loadArchive(a: any) {
  try {
    // Fetch full archive with content from dedicated endpoint
    const res = await api.get(`/reports/archives/${a.id}`)
    const archive = res.data
    reportType.value = archive.report_type
    const [y, m] = archive.period_start.split('-')
    year.value = parseInt(y)
    month.value = parseInt(m)
    reportData.value = typeof archive.content === 'string' ? JSON.parse(archive.content) : archive.content
  } catch (e: any) {
    show(e.response?.data?.detail || '加载失败', 'error')
  }
}

async function deleteArchive(id: string) {
  if (confirm('确定删除此归档？')) {
    try {
      await api.delete(`/reports/archives/${id}`)
      show('已删除', 'success')
      loadArchives()
    } catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
  }
}

async function exportAiPackage() {
  try {
    showExportModal.value = false
    const res = await api.post('/ai/export-package', selectedArchiveIds.value, {
      responseType: 'blob'
    })
    const blob = new Blob([res.data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `finkit-export-${new Date().toISOString().slice(0, 10)}.zip`
    a.click()
    URL.revokeObjectURL(url)
    show('数据包已下载（含 finkit-data.json + AI-GUIDE.md）', 'success')
    selectedArchiveIds.value = []
  } catch (e: any) {
    show(e.response?.data?.detail || '导出失败', 'error')
  }
}

import { onMounted } from 'vue'
onMounted(() => { loadArchives(); generate() })
</script>
