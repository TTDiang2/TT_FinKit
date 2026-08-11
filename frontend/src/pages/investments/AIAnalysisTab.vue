<template>
  <div>
    <div class="bg-white rounded-lg p-5 shadow-sm mb-4">
      <h2 class="font-semibold mb-3">AI 投资分析</h2>
      <p class="text-sm text-text-secondary mb-4">
        基于最新相关新闻与行情数据，自动生成结构化分析（情绪 / 关键发现 / 风险 / 建议）。
        分析需在 <router-link to="/admin" class="text-accent-primary underline">管理 → AI 助手设置</router-link> 中预先配置至少一个默认预设。
      </p>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label class="block text-sm font-medium mb-1">选择产品</label>
          <select v-model="selectedId" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">请选择</option>
            <option v-for="inv in activeInvestments" :key="inv.id" :value="inv.id">
              {{ inv.name }} {{ inv.symbol ? `(${inv.symbol})` : '' }}
            </option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">搜索近 N 天</label>
          <select v-model.number="days" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option :value="1">1 天</option>
            <option :value="7">7 天</option>
            <option :value="30">30 天</option>
            <option :value="90">90 天</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium mb-1">文章数</label>
          <select v-model.number="maxArticles" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option :value="5">5</option>
            <option :value="10">10</option>
            <option :value="20">20</option>
          </select>
        </div>
      </div>
      <div class="mb-3">
        <label class="block text-sm font-medium mb-1">自定义查询（可选）</label>
        <input v-model="customQuery" placeholder="留空则使用默认查询" class="w-full px-3 py-2 border border-border-default rounded-md text-sm" />
      </div>
      <button :disabled="!selectedId || analyzing" @click="runAnalyze"
        :class="['px-5 py-2 rounded-md text-white flex items-center gap-2', !selectedId || analyzing ? 'bg-gray-400 cursor-not-allowed' : 'bg-accent-primary hover:bg-accent-hover']">
        <Sparkles v-if="!analyzing" :size="16" />
        <span v-if="analyzing">分析中…</span>
        <span v-else>开始分析</span>
      </button>
    </div>

    <div v-if="error" class="bg-red-50 border border-expense-color text-expense-color rounded-lg p-4 mb-4">
      分析失败：{{ error }}
    </div>

    <div v-if="currentReport" class="bg-white rounded-lg p-5 shadow-sm mb-4">
      <div class="flex items-start justify-between mb-3">
        <div>
          <h3 class="font-semibold">{{ currentReport.investment_name }} <span v-if="currentReport.investment_symbol" class="text-text-muted text-sm">({{ currentReport.investment_symbol }})</span></h3>
          <div class="text-xs text-text-muted mt-1">
            搜索后端：{{ currentReport.search_backend }} ·
            模型：{{ currentReport.llm_model || '未生成' }} ·
            {{ formatDate(currentReport.generated_at) }}
          </div>
        </div>
        <span :class="['px-3 py-1 rounded text-sm font-medium', sentimentColor(currentReport.analysis?.sentiment)]">
          {{ sentimentLabel(currentReport.analysis?.sentiment) }} · {{ Math.round((currentReport.analysis?.sentiment_confidence || 0) * 100) }}%
        </span>
      </div>

      <div v-if="currentReport.error" class="text-expense-color text-sm mb-3">{{ currentReport.error }}</div>

      <template v-if="currentReport.analysis">
        <div class="mb-4">
          <h4 class="text-sm font-medium text-text-secondary mb-1">摘要</h4>
          <p class="text-sm leading-relaxed">{{ currentReport.analysis.summary }}</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <h4 class="text-sm font-medium text-text-secondary mb-1">关键发现</h4>
            <ul class="text-sm space-y-1 list-disc list-inside">
              <li v-for="(f, i) in currentReport.analysis.key_findings" :key="i">{{ f }}</li>
              <li v-if="!currentReport.analysis.key_findings.length" class="text-text-muted">无</li>
            </ul>
          </div>
          <div>
            <h4 class="text-sm font-medium text-text-secondary mb-1">关键风险</h4>
            <ul class="text-sm space-y-1 list-disc list-inside">
              <li v-for="(r, i) in currentReport.analysis.key_risks" :key="i">{{ r }}</li>
              <li v-if="!currentReport.analysis.key_risks.length" class="text-text-muted">无</li>
            </ul>
          </div>
        </div>

        <div class="mb-4">
          <h4 class="text-sm font-medium text-text-secondary mb-1">近期重大事件</h4>
          <ul class="text-sm space-y-1 list-disc list-inside">
            <li v-for="(d, i) in currentReport.analysis.notable_developments" :key="i">{{ d }}</li>
            <li v-if="!currentReport.analysis.notable_developments.length" class="text-text-muted">无</li>
          </ul>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <h4 class="text-sm font-medium text-text-secondary mb-1">建议操作</h4>
            <div class="flex items-center gap-2">
              <span :class="['px-2 py-1 rounded text-sm font-medium', actionColor(currentReport.analysis.suggested_action)]">
                {{ actionLabel(currentReport.analysis.suggested_action) }}
              </span>
              <span class="text-xs text-text-muted">置信度 {{ Math.round(currentReport.analysis.action_confidence * 100) }}%</span>
            </div>
          </div>
          <div>
            <h4 class="text-sm font-medium text-text-secondary mb-1">数据质量</h4>
            <span class="text-sm">{{ qualityLabel(currentReport.analysis.data_quality) }}</span>
          </div>
        </div>

        <div class="mb-4">
          <h4 class="text-sm font-medium text-text-secondary mb-1">各周期指标</h4>
          <div class="grid grid-cols-3 gap-2 text-sm">
            <div class="bg-bg-secondary rounded p-2 text-center">
              <div class="text-xs text-text-muted">短期</div>
              <div :class="indicatorColor(currentReport.analysis.relevant_indicators.short_term)">
                {{ indicatorLabel(currentReport.analysis.relevant_indicators.short_term) }}
              </div>
            </div>
            <div class="bg-bg-secondary rounded p-2 text-center">
              <div class="text-xs text-text-muted">中期</div>
              <div :class="indicatorColor(currentReport.analysis.relevant_indicators.medium_term)">
                {{ indicatorLabel(currentReport.analysis.relevant_indicators.medium_term) }}
              </div>
            </div>
            <div class="bg-bg-secondary rounded p-2 text-center">
              <div class="text-xs text-text-muted">长期</div>
              <div :class="indicatorColor(currentReport.analysis.relevant_indicators.long_term)">
                {{ indicatorLabel(currentReport.analysis.relevant_indicators.long_term) }}
              </div>
            </div>
          </div>
        </div>
      </template>

      <details class="mt-3">
        <summary class="cursor-pointer text-sm text-text-secondary">查看引用文章 ({{ currentReport.raw_articles?.length || 0 }})</summary>
        <ul class="mt-2 space-y-2 text-sm">
          <li v-for="(a, i) in currentReport.raw_articles" :key="i" class="bg-bg-secondary rounded p-2">
            <a :href="a.url" target="_blank" rel="noopener" class="text-accent-primary hover:underline font-medium">{{ a.title }}</a>
            <div class="text-xs text-text-muted">{{ a.source }} · {{ a.published }}</div>
            <div class="text-xs text-text-secondary mt-1">{{ a.snippet }}</div>
          </li>
          <li v-if="!currentReport.raw_articles?.length" class="text-text-muted">无引用文章</li>
        </ul>
      </details>
    </div>

    <div v-if="history.length" class="bg-white rounded-lg p-5 shadow-sm">
      <h3 class="font-semibold mb-3">历史分析</h3>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr><th class="px-3 py-2 font-medium">产品</th><th class="px-3 py-2 font-medium">情绪</th><th class="px-3 py-2 font-medium">建议</th><th class="px-3 py-2 font-medium">时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in history" :key="r.id" class="border-t border-border-default hover:bg-bg-secondary cursor-pointer" @click="selectReport(r)">
            <td class="px-3 py-2">{{ r.investment_name }}</td>
            <td class="px-3 py-2">{{ sentimentLabel(r.analysis?.sentiment) }}</td>
            <td class="px-3 py-2">{{ actionLabel(r.analysis?.suggested_action) }}</td>
            <td class="px-3 py-2 text-text-muted">{{ formatDate(r.generated_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Sparkles } from 'lucide-vue-next'
import { useInvestmentsStore } from '@/stores/investments'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { InvestmentAiReport, AnalyzeRequest, Investment, InvestmentAnalysisResponse } from '@/types'

const store = useInvestmentsStore()
const api = useApi()
const { show } = useToast()

const selectedId = ref('')
const days = ref(7)
const maxArticles = ref(10)
const customQuery = ref('')
const analyzing = ref(false)
const error = ref('')
const currentReport = ref<InvestmentAiReport | null>(null)
const history = ref<InvestmentAiReport[]>([])

const activeInvestments = computed(() => store.investments.filter(i => !i.sell_date))

function sentimentLabel(s?: InvestmentAnalysisResponse['sentiment']) {
  return s === 'bullish' ? '看多' : s === 'bearish' ? '看空' : s === 'mixed' ? '分歧' : s === 'neutral' ? '中性' : '—'
}
function sentimentColor(s?: InvestmentAnalysisResponse['sentiment']) {
  return s === 'bullish' ? 'bg-green-100 text-green-800' : s === 'bearish' ? 'bg-red-100 text-red-800' : s === 'mixed' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'
}
function actionLabel(a?: InvestmentAnalysisResponse['suggested_action']) {
  return a === 'buy' ? '买入' : a === 'sell' ? '卖出' : a === 'hold' ? '持有' : a === 'watch' ? '观望' : '数据不足'
}
function actionColor(a?: InvestmentAnalysisResponse['suggested_action']) {
  return a === 'buy' ? 'bg-green-100 text-green-800' : a === 'sell' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
}
function indicatorLabel(v?: string) {
  return v === 'positive' ? '正面' : v === 'negative' ? '负面' : '中性'
}
function indicatorColor(v?: string) {
  return v === 'positive' ? 'text-green-700 font-medium' : v === 'negative' ? 'text-red-700 font-medium' : 'text-text-muted'
}
function qualityLabel(q?: string) {
  return q === 'high' ? '高' : q === 'medium' ? '中' : '低'
}
function formatDate(s: string) {
  return new Date(s).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' })
}

async function runAnalyze() {
  if (!selectedId.value) return
  analyzing.value = true
  error.value = ''
  try {
    const body: AnalyzeRequest = { days: days.value, max_articles: maxArticles.value }
    if (customQuery.value.trim()) body.query = customQuery.value.trim()
    const res = await api.post(`/investments/${selectedId.value}/ai-analysis`, body)
    currentReport.value = res.data
    show('分析完成', 'success')
    await loadHistory(selectedId.value)
  } catch (e: any) {
    const msg = e.response?.data?.detail || e.message || '分析失败'
    error.value = msg
    show(msg, 'error')
  } finally {
    analyzing.value = false
  }
}

async function loadHistory(investmentId?: string) {
  try {
    const params = investmentId ? { investment_id: investmentId } : {}
    const res = await api.get('/investments/ai/reports', { params })
    history.value = res.data
  } catch {}
}

async function selectReport(r: InvestmentAiReport) {
  currentReport.value = r
  selectedId.value = r.investment_id
  await loadHistory(r.investment_id)
}

watch(selectedId, async (id) => {
  if (id) await loadHistory(id)
  else { history.value = []; currentReport.value = null }
})

onMounted(async () => {
  if (!store.investments.length) await store.fetchInvestments()
  await loadHistory()
})
</script>