<template>
  <div class="p-6">
    <!-- Sub-tab navigation -->
    <div class="flex gap-2 mb-4 border-b border-border-default">
      <button
        v-for="t in subTabs"
        :key="t.key"
        @click="activeSubTab = t.key"
        :class="[
          'px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
          activeSubTab === t.key
            ? 'border-accent-primary text-accent-primary'
            : 'border-transparent text-text-secondary hover:text-text-primary'
        ]"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- 监控面板 -->
    <div v-show="activeSubTab === 'monitor'">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold">监控</h2>
        <button @click="showSettings = !showSettings" class="btn-secondary">
          <Settings2 :size="14" /> {{ showSettings ? '隐藏设置' : '告警设置' }}
        </button>
      </div>

      <!-- 告警汇总条 -->
      <div v-if="overview?.alerts_summary?.total_alerts"
        class="flex items-center gap-2 px-4 py-2 mb-4 bg-yellow-50 border border-yellow-200 rounded text-sm">
        <span class="text-yellow-600">⚠</span>
        <span>共 {{ overview.alerts_summary.total_alerts }} 个告警</span>
        <span v-if="overview.alerts_summary.portfolio_alerts">组合 {{ overview.alerts_summary.portfolio_alerts }} |</span>
        <span v-if="overview.alerts_summary.risk_alerts">风险 {{ overview.alerts_summary.risk_alerts }} |</span>
        <span v-if="overview.alerts_summary.deviation_alerts">偏离 {{ overview.alerts_summary.deviation_alerts }}</span>
      </div>

      <!-- 策略健康 / 调仓冷却 / 数据新鲜度 -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <!-- 策略健康 -->
        <div class="bg-white rounded-lg shadow-sm p-4" v-if="health">
          <div class="flex items-center justify-between mb-2">
            <h3 class="font-medium text-sm">策略健康
              <span v-if="health.strategy" class="text-xs text-text-muted ml-1">{{ health.strategy.name }}</span>
            </h3>
            <span :class="['px-2 py-0.5 text-xs rounded', health.level === 'ok' ? 'bg-income-bg text-income-color' : health.level === 'yellow' ? 'bg-yellow-50 text-yellow-700' : 'bg-expense-bg text-expense-color']">
              {{ health.level === 'ok' ? '正常' : health.level === 'yellow' ? '预警' : '失效' }}
            </span>
          </div>
          <ul v-if="health.reasons?.length" class="text-xs text-text-secondary space-y-1 mb-2">
            <li v-for="(r, i) in health.reasons" :key="i">⚠ {{ r }}</li>
          </ul>
          <div v-else class="text-xs text-text-muted mb-2">各项指标未触发失效阈值</div>
          <div v-if="health.backtest" class="text-xs text-text-muted">
            基线回测 {{ health.backtest.start }} ~ {{ health.backtest.end }}：
            年化 {{ fmtPct(health.backtest.ann) }} · 夏普 {{ (health.backtest.sharpe ?? 0).toFixed(2) }} · 回撤 {{ fmtPct(health.backtest.mdd) }}
          </div>
          <div v-if="health.live_drift?.since" class="text-xs text-text-secondary mt-1">
            信号日({{ health.live_drift.since }})以来：{{ fmtPct(health.live_drift.ret) }} / 区间回撤 {{ fmtPct(health.live_drift.mdd) }}
          </div>
          <div v-else class="text-xs text-text-muted mt-1">信号较新，实盘漂移样本积累中（≥126 日后启用滚动年化判定）</div>
        </div>

        <!-- 调仓冷却 -->
        <div class="bg-white rounded-lg shadow-sm p-4" v-if="health">
          <h3 class="font-medium text-sm mb-2">调仓节奏</h3>
          <div class="text-xs text-text-secondary space-y-1">
            <div>最近调仓：<span class="font-medium">{{ health.rebalance?.last_date || '无记录' }}</span>
              <span class="text-text-muted">（{{ health.rebalance?.source }}）</span></div>
            <div v-if="health.rebalance?.in_cooldown" class="text-income-color">
              冷却期内（至 {{ health.rebalance.cooldown_until }}），信号页不会重复催促调仓
            </div>
            <div v-if="health.signal">下次调仓日：{{ health.signal.next_rebalance }}</div>
          </div>
          <button @click="confirmRebalance" :disabled="confirming"
            class="btn-secondary mt-3 text-xs disabled:opacity-50">
            {{ confirming ? '记录中…' : '✓ 我已完成调仓' }}
          </button>
          <div v-if="confirmMsg" class="text-xs text-income-color mt-1">{{ confirmMsg }}</div>
        </div>

        <!-- 数据新鲜度 -->
        <div class="bg-white rounded-lg shadow-sm p-4" v-if="health">
          <h3 class="font-medium text-sm mb-2">数据新鲜度</h3>
          <div class="text-xs text-text-secondary space-y-1">
            <div>入池标的价格最新日期：<span class="font-medium">{{ health.data_freshness?.max_date }}</span>
              （{{ health.data_freshness?.lag_days }} 天前）</div>
            <div v-if="health.data_freshness?.remind_full_update" class="text-warning">
              ⚠ 已超过 {{ health.data_freshness.remind_after_days }} 天未更新——给出信号前建议先做一次全量数据更新（标的页 → 批量拉取）
            </div>
            <div v-else class="text-text-muted">数据新鲜度正常（月度全量更新提醒阈值 {{ health.data_freshness.remind_after_days }} 天）</div>
          </div>
        </div>
      </div>

      <!-- 三大区 -->
      <div class="grid grid-cols-1 gap-6">

        <!-- Zone 1: 组合监控 -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="font-medium mb-3">组合监控</h3>
          <div v-if="overview?.zone1_portfolio?.items?.length" class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="bg-bg-tertiary text-left">
                <tr>
                  <th class="px-3 py-2 font-medium">标的</th>
                  <th class="px-3 py-2 font-medium text-right">目标权重</th>
                  <th class="px-3 py-2 font-medium text-right">实际权重</th>
                  <th class="px-3 py-2 font-medium text-right">偏离</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in overview.zone1_portfolio.items" :key="item.asset_id"
                  class="border-t border-border-default">
                  <td class="px-3 py-2">
                    <span class="font-medium">{{ item.symbol }}</span>
                    <span class="text-text-muted text-xs ml-1">{{ item.name }}</span>
                  </td>
                  <td class="px-3 py-2 text-right">{{ (item.target_weight * 100).toFixed(1) }}%</td>
                  <td class="px-3 py-2 text-right">{{ (item.actual_weight * 100).toFixed(1) }}%</td>
                  <td class="px-3 py-2 text-right">
                    <span :class="item.has_alert ? 'text-expense-color font-medium' : 'text-text-secondary'">
                      {{ (item.deviation * 100).toFixed(1) }}pp
                    </span>
                    <span v-if="item.has_alert" class="ml-1 text-expense-color">⚠</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-sm text-text-muted py-4 text-center">
            暂无持仓数据
          </div>
        </div>

        <!-- Zone 2: 风险监控 -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="font-medium mb-3">风险监控</h3>
          <div class="grid grid-cols-4 gap-4 mb-4">
            <div class="text-center">
              <div class="text-xs text-text-muted mb-1">当前净值</div>
              <div class="text-xl font-semibold">{{ overview?.zone2_risk?.current_nav?.toFixed(4) ?? '-' }}</div>
            </div>
            <div class="text-center">
              <div class="text-xs text-text-muted mb-1">最大回撤</div>
              <div class="text-xl font-semibold" :class="overview?.zone2_risk?.drawdown_alert ? 'text-expense-color' : 'text-text-primary'">
                {{ ((overview?.zone2_risk?.max_drawdown ?? 0) * 100).toFixed(1) }}%
                <span v-if="overview?.zone2_risk?.drawdown_alert" class="text-expense-color">⚠</span>
              </div>
            </div>
            <div class="text-center">
              <div class="text-xs text-text-muted mb-1">VaR 95%</div>
              <div class="text-xl font-semibold text-text-primary">
                {{ ((overview?.zone2_risk?.var_95 ?? 0) * 100).toFixed(2) }}%
              </div>
            </div>
            <div class="text-center">
              <div class="text-xs text-text-muted mb-1">CVaR 95%</div>
              <div class="text-xl font-semibold text-text-primary">
                {{ ((overview?.zone2_risk?.cvar_95 ?? 0) * 100).toFixed(2) }}%
              </div>
            </div>
          </div>
          <div v-if="overview?.zone2_risk?.factor_exposures?.length">
            <div class="text-xs text-text-muted mb-2">因子暴露与风险贡献</div>
            <table class="w-full text-sm">
              <thead class="bg-bg-tertiary text-left">
                <tr>
                  <th class="px-3 py-1.5 font-medium">因子</th>
                  <th class="px-3 py-1.5 font-medium text-right">加权 β</th>
                  <th class="px-3 py-1.5 font-medium text-right">风险贡献</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="f in overview.zone2_risk.factor_exposures" :key="f.factor_id"
                  class="border-t border-border-default">
                  <td class="px-3 py-1.5">{{ f.factor_name }}</td>
                  <td class="px-3 py-1.5 text-right">{{ f.weighted_beta.toFixed(3) }}</td>
                  <td class="px-3 py-1.5 text-right">{{ (f.risk_contribution * 100).toFixed(1) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Zone 3: 策略偏离 -->
        <div class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="font-medium mb-3">策略偏离</h3>
          <div class="flex items-center gap-4 mb-4 text-sm">
            <div v-if="overview?.zone3_deviation">
              <span class="text-text-muted">上次信号:</span>
              <span class="ml-1">{{ overview.zone3_deviation.last_signal_date ?? '-' }}</span>
            </div>
            <div v-if="overview?.zone3_deviation?.next_rebalance_date">
              <span class="text-text-muted">下一调仓:</span>
              <span class="ml-1 font-medium">{{ overview.zone3_deviation.next_rebalance_date }}</span>
            </div>
            <div>
              <span :class="overview?.zone3_deviation?.continuity_status === 'ok' ? 'text-income-color' : 'text-expense-color'">
                {{ overview?.zone3_deviation?.continuity_status === 'ok' ? '✅ 策略运行正常' :
                   overview?.zone3_deviation?.continuity_status === 'stale' ? '⚠️ 信号过期' : '⚠️ 无信号' }}
              </span>
            </div>
          </div>
          <div v-if="overview?.zone3_deviation?.factor_drifts?.length">
            <table class="w-full text-sm">
              <thead class="bg-bg-tertiary text-left">
                <tr>
                  <th class="px-3 py-1.5 font-medium">因子</th>
                  <th class="px-3 py-1.5 font-medium text-right">当前 β</th>
                  <th class="px-3 py-1.5 font-medium text-right">3月前 β</th>
                  <th class="px-3 py-1.5 font-medium text-right">漂移</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="f in overview.zone3_deviation.factor_drifts" :key="f.factor_id"
                  class="border-t border-border-default">
                  <td class="px-3 py-1.5">{{ f.factor_name }}</td>
                  <td class="px-3 py-1.5 text-right">{{ f.current_beta.toFixed(3) }}</td>
                  <td class="px-3 py-1.5 text-right text-text-secondary">{{ f.prev_beta.toFixed(3) }}</td>
                  <td class="px-3 py-1.5 text-right">
                    <span :class="f.has_alert ? 'text-expense-color font-medium' : 'text-text-secondary'">
                      {{ f.drift.toFixed(3) }}
                    </span>
                    <span v-if="f.has_alert" class="ml-1 text-expense-color">⚠</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="text-sm text-text-muted py-4 text-center">
            暂无因子漂移数据
          </div>
        </div>
      </div>

      <div v-if="showSettings" class="mt-6 bg-white rounded-lg shadow-sm p-4">
        <h3 class="font-medium mb-3">告警阈值设置</h3>
        <div class="grid grid-cols-3 gap-4 mb-4">
          <div>
            <label class="block text-sm font-medium mb-1">权重偏离告警 (pp)</label>
            <input v-model.number="settings.weight_deviation_pp" type="number" min="0.1" step="0.5"
              class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">因子暴露漂移告警</label>
            <input v-model.number="settings.exposure_drift" type="number" min="0.01" step="0.05"
              class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">回撤告警 (%)</label>
            <input v-model.number="settings.drawdown_alert_pct" type="number" min="1" step="1"
              class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
          </div>
        </div>
        <button @click="saveSettings" :disabled="saving"
          class="btn-primary disabled:opacity-50">
          {{ saving ? '保存中...' : '保存设置' }}
        </button>
        <span v-if="saveMsg" class="ml-3 text-sm text-income-color">{{ saveMsg }}</span>
      </div>
    </div>

    <!-- 信号子tab -->
    <div v-show="activeSubTab === 'signal'">
      <SignalPanel />
    </div>
  </div>
    <!-- 驱动事件（RSS 原型） -->
    <div v-show="activeSubTab === 'events'" class="p-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-lg font-semibold">驱动事件</h2>
          <p class="text-xs text-text-muted mt-0.5">RSS 财经事件流（原型）——按关键词归类资产，未来可触发紧急调仓。采集器：backend/scripts 事件服务。</p>
        </div>
        <button @click="collectEvents" :disabled="collecting" class="btn-secondary">
          {{ collecting ? '采集中…' : '立即采集' }}
        </button>
      </div>
      <div class="flex gap-2 mb-3">
        <select v-model="eventClass" @change="loadEvents" class="px-2 py-1 text-xs border border-border-default rounded-md">
          <option value="">全部类别</option>
          <option value="rates">利率/央行</option>
          <option value="gold">黄金</option>
          <option value="semis">半导体</option>
          <option value="oil">原油</option>
          <option value="a_share">A股</option>
          <option value="bond">债券</option>
        </select>
        <span v-if="eventsLoaded" class="text-xs text-text-muted self-center">{{ events.length }} 条</span>
      </div>
      <div class="bg-white rounded-lg shadow-sm divide-y divide-border-default">
        <div v-for="e in events" :key="e.id" class="px-4 py-2.5">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <a v-if="e.link" :href="e.link" target="_blank" rel="noopener"
                class="text-sm font-medium hover:text-accent-primary truncate block">{{ e.title }}</a>
              <span v-else class="text-sm">{{ e.title }}</span>
              <div class="text-xs text-text-muted mt-0.5">{{ e.source }} · {{ e.published }} ·
                <span v-if="e.asset_class" class="px-1 rounded bg-bg-tertiary">{{ e.asset_class }}</span>
                <span v-else class="text-text-muted">未归类</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="!events.length && eventsLoaded" class="px-4 py-6 text-center text-text-muted text-sm">
          暂无事件。点「立即采集」拉取最新 RSS。
        </div>
      </div>
    </div>

</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

const health = ref<any>(null)
const confirming = ref(false)
const confirmMsg = ref('')

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : '—'
}

async function loadHealth() {
  try {
    const { data } = await api.get('/monitor/strategy-health')
    health.value = data
  } catch { health.value = null }
}

async function confirmRebalance() {
  confirming.value = true
  confirmMsg.value = ''
  try {
    const { data } = await api.post('/monitor/rebalance-log', {})
    confirmMsg.value = `已记录调仓完成：${data.date}`
    await loadHealth()
  } catch (e: any) {
    confirmMsg.value = `记录失败：${e?.response?.data?.detail || e?.message || e}`
  } finally {
    confirming.value = false
  }
}
import { Settings2 } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import SignalPanel from './SignalPage.vue'
import type { MonitorOverview, MonitorSettings } from '@/types'

const api = useApi()
const route = useRoute()

const events = ref<any[]>([])
const eventsLoaded = ref(false)
const eventClass = ref('')
const collecting = ref(false)

async function loadEvents() {
  try {
    const params: Record<string, unknown> = { limit: 100 }
    if (eventClass.value) params.asset_class = eventClass.value
    const { data } = await api.get('/monitor/events', { params })
    events.value = data
    eventsLoaded.value = true
  } catch { events.value = [] }
}

async function collectEvents() {
  collecting.value = true
  try {
    await api.post('/monitor/events/collect', {})
    await loadEvents()
  } finally {
    collecting.value = false
  }
}


const subTabs: { key: 'monitor' | 'signal' | 'events'; label: string }[] = [
  { key: 'monitor', label: '监控' },
  { key: 'signal', label: '信号' },
  { key: 'events', label: '驱动事件' },
]
const activeSubTab = ref<'monitor' | 'signal' | 'events'>('monitor')
watch(activeSubTab, (t) => { if (t === 'events' && !eventsLoaded.value) loadEvents() })

if (route.query.sub === 'signal') activeSubTab.value = 'signal'
watch(() => route.query.sub, (val) => {
  const v = Array.isArray(val) ? val[0] : val
  if (v === 'signal') activeSubTab.value = 'signal'
  else activeSubTab.value = 'monitor'
})

const overview = ref<MonitorOverview | null>(null)
const loading = ref(false)
const showSettings = ref(false)
const saving = ref(false)
const saveMsg = ref('')

const settings = ref<MonitorSettings>({
  weight_deviation_pp: 5,
  exposure_drift: 0.3,
  drawdown_alert_pct: 10,
})

async function loadOverview() {
  loading.value = true
  try {
    const { data } = await api.get<MonitorOverview>('/monitor/overview')
    overview.value = data
  } finally {
    loading.value = false
  }
}

async function loadSettings() {
  try {
    const { data } = await api.get<MonitorSettings>('/monitor/settings')
    settings.value = data
  } catch {}
}

async function saveSettings() {
  saving.value = true
  saveMsg.value = ''
  try {
    await api.put('/monitor/settings', settings.value)
    saveMsg.value = '设置已保存'
    setTimeout(() => { saveMsg.value = '' }, 2000)
  } catch (e) {
    saveMsg.value = '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => { loadOverview(); loadSettings(); loadHealth() })
</script>
