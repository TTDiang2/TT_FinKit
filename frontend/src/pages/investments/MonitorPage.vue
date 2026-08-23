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
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Settings2 } from 'lucide-vue-next'
import { useApi } from '@/composables/useApi'
import SignalPanel from './SignalPage.vue'
import type { MonitorOverview, MonitorSettings } from '@/types'

const api = useApi()
const route = useRoute()
const subTabs: { key: 'monitor' | 'signal'; label: string }[] = [
  { key: 'monitor', label: '监控' },
  { key: 'signal', label: '信号' },
]
const activeSubTab = ref<'monitor' | 'signal'>('monitor')
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

onMounted(() => { loadOverview(); loadSettings() })
</script>
