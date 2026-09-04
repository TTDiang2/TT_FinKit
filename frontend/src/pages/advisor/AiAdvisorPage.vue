<template>
  <div class="flex" style="height: calc(100vh - 4rem)">
    <!-- 左侧栏：新对话 + 历史会话 -->
    <aside class="w-60 shrink-0 border-r border-border-default bg-white flex flex-col">
      <div class="p-3">
        <button @click="newConversation" class="w-full btn-primary text-sm flex items-center justify-center gap-1.5">
          <Plus :size="15" /> 新对话
        </button>
      </div>
      <div class="px-3 pb-1 text-[10px] font-medium text-text-muted uppercase tracking-wide">历史会话</div>
      <div class="flex-1 overflow-y-auto px-2 pb-3 space-y-0.5">
        <div v-if="archiveLoading" class="text-xs text-text-muted px-2 py-3">加载中…</div>
        <div v-else-if="!archiveSessions.length" class="text-xs text-text-muted px-2 py-3">暂无历史对话</div>
        <div v-for="s in archiveSessions" :key="s.session_id"
          :class="['group flex items-start justify-between gap-1 px-2 py-1.5 rounded-md cursor-pointer text-xs',
                   viewingSession?.session_id === s.session_id ? 'bg-accent-primary/10' : 'hover:bg-bg-secondary']"
          @click="openArchiveDetail(s)">
          <div class="min-w-0">
            <div class="font-medium truncate" :title="s.first_question">{{ s.first_question || '（无提问）' }}</div>
            <div class="text-[10px] text-text-muted mt-0.5">
              {{ s.started_at?.slice(5, 10) }} · {{ Math.ceil((s.msg_count || 0) / 2) }} 轮
            </div>
          </div>
          <button @click.stop="deleteArchiveSession(s)"
            class="opacity-0 group-hover:opacity-100 text-text-muted hover:text-expense-color shrink-0" title="删除">
            <Trash2 :size="12" />
          </button>
        </div>
      </div>
    </aside>

    <!-- 主区 -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- 顶栏：标题 + 视图切换 -->
      <div class="flex items-center justify-between px-5 py-2.5 border-b border-border-default bg-white shrink-0">
        <div class="min-w-0">
          <h2 class="text-base font-semibold leading-tight">AI 财富审计师</h2>
          <p class="text-[10px] text-text-muted">严厉 · 理性 · 只引用真实数据 · 不提供情绪价值</p>
        </div>
        <div class="flex gap-1 bg-bg-tertiary rounded-lg p-0.5">
          <button v-for="t in viewTabs" :key="t.key" @click="viewMode = t.key"
            :class="['px-3 py-1 text-xs rounded-md transition-colors flex items-center gap-1',
                     viewMode === t.key ? 'bg-white shadow-sm font-medium' : 'text-text-secondary hover:text-text-primary']">
            <component :is="t.icon" :size="13" /> {{ t.label }}
          </button>
        </div>
      </div>

      <!-- ══════════ 对话视图 ══════════ -->
      <template v-if="viewMode === 'chat'">
        <!-- 归档查看模式 -->
        <template v-if="viewingSession">
          <div class="flex items-center gap-2 px-5 py-2 bg-bg-secondary border-b border-border-default text-xs shrink-0">
            <button @click="closeArchiveDetail" class="underline text-text-secondary hover:text-text-primary">← 返回当前对话</button>
            <span class="text-text-muted">正在查看历史：{{ viewingSession.first_question }}（{{ viewingSession.started_at?.slice(0, 16) }}）</span>
          </div>
          <div class="flex-1 overflow-y-auto p-5">
            <div class="max-w-3xl mx-auto space-y-3">
              <div v-for="m in archiveMessages" :key="m.id"
                :class="['rounded-lg px-4 py-2.5 text-sm', m.role === 'user' ? 'ml-auto max-w-[80%] bg-accent-primary/10' : 'bg-bg-tertiary']">
                <div v-if="m.role === 'assistant'" class="text-[10px] text-text-muted mb-1">财富审计师</div>
                <div v-if="m.role === 'assistant'" class="md-body" v-html="renderMd(m.content)"></div>
                <div v-else class="whitespace-pre-wrap">{{ m.content }}</div>
              </div>
            </div>
          </div>
        </template>

        <!-- 实时对话 -->
        <template v-else>
          <div ref="chatBox" class="flex-1 overflow-y-auto p-5">
            <div class="max-w-3xl mx-auto space-y-3">
              <div v-if="!messages.length" class="text-sm text-text-muted py-16 text-center">
                问点什么，例如：<br><br>
                <span class="text-text-secondary">「评价一下我这一个月的消费决策」</span><br>
                <span class="text-text-secondary">「我的应急储备够不够？离目标差多少」</span><br>
                <span class="text-text-secondary">「审视我的投资组合暴露是否与购房目标冲突」</span>
              </div>
              <div v-for="(m, i) in messages" :key="i"
                :class="['rounded-lg px-4 py-2.5 text-sm', m.role === 'user' ? 'ml-auto max-w-[80%] bg-accent-primary/10' : 'bg-bg-tertiary']">
                <div v-if="m.role === 'assistant'" class="text-[10px] text-text-muted mb-1">财富审计师</div>
                <div v-if="m.role === 'assistant' && m.content" class="md-body" v-html="renderMd(m.content)"></div>
                <div v-else-if="m.role === 'user'" class="whitespace-pre-wrap">{{ m.content }}</div>
              </div>

              <!-- 思考过程面板 -->
              <div v-if="reasoningText"
                ref="reasoningBox"
                class="max-w-[80%] bg-bg-secondary border border-border-default rounded-lg px-4 py-2 text-xs text-text-muted">
                <div class="flex items-center justify-between mb-1">
                  <span>
                    <template v-if="asking && !messages[messages.length - 1]?.content">🤔 思考中…（逐字输出）</template>
                    <template v-else>🤔 深度思考过程</template>
                  </span>
                  <button @click="showReasoning = !showReasoning" class="underline">
                    {{ showReasoning ? '收起' : `展开（${reasoningText.length} 字）` }}
                  </button>
                </div>
                <div v-show="showReasoning" class="whitespace-pre-wrap" style="max-height: 220px; overflow-y: auto">{{ reasoningText.slice(-1500) }}</div>
              </div>
              <div v-if="asking && !reasoningText && !messages[messages.length - 1]?.content" class="text-sm text-text-muted">
                审计师正在核对数据，首字生成可能需要数十秒…
              </div>
              <div v-if="askError" class="text-xs text-expense-color">
                {{ askError }}
                <button v-if="lastQuestion && !asking" @click="retryLast" class="underline ml-1 font-medium">重新生成</button>
              </div>
            </div>
          </div>
          <div class="px-5 pb-4 shrink-0">
            <div class="max-w-3xl mx-auto flex gap-2">
              <textarea v-model="question" rows="2"
                placeholder="例如：评价我最近一个月的消费决策和财务状况"
                class="flex-1 px-3 py-2 text-sm border border-border-default rounded-lg resize-none bg-white" />
              <button @click="ask" :disabled="asking || !question.trim()"
                class="btn-primary self-end disabled:opacity-50">
                {{ asking ? '分析中…' : '提交' }}
              </button>
            </div>
          </div>
        </template>
      </template>

      <!-- ══════════ 数据画像视图 ══════════ -->
      <template v-else-if="viewMode === 'snapshot'">
        <div class="flex-1 overflow-y-auto p-5">
          <div v-if="!snapshot" class="text-sm text-text-muted py-16 text-center">加载中…</div>
          <div v-else class="max-w-5xl mx-auto space-y-4">
            <!-- 关键指标卡 -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div class="bg-white rounded-lg shadow-sm p-3">
                <div class="text-xs text-text-muted">近6月储蓄率</div>
                <div class="text-lg font-bold" :class="(snapshot.savings_6m?.savings_rate ?? 0) < 0.1 ? 'text-expense-color' : 'text-income-color'">
                  {{ fmtPct(snapshot.savings_6m?.savings_rate) }}</div>
              </div>
              <div class="bg-white rounded-lg shadow-sm p-3">
                <div class="text-xs text-text-muted">应急覆盖（现金口径）</div>
                <div class="text-lg font-bold" :class="(snapshot.emergency_reserve?.cover_months ?? 9) < 6 ? 'text-expense-color' : 'text-income-color'">
                  {{ snapshot.emergency_reserve?.cover_months ?? '—' }} 个月</div>
              </div>
              <div class="bg-white rounded-lg shadow-sm p-3">
                <div class="text-xs text-text-muted">现金总额</div>
                <div class="text-lg font-bold">{{ fmt(snapshot.cash_total) }}</div>
              </div>
              <div class="bg-white rounded-lg shadow-sm p-3">
                <div class="text-xs text-text-muted">累计落袋盈亏</div>
                <div class="text-lg font-bold" :class="(snapshot.investment_profile?.realized_pnl ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
                  {{ fmt(snapshot.investment_profile?.realized_pnl) }}</div>
              </div>
            </div>

            <!-- 图表行 -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div class="bg-white rounded-lg shadow-sm p-4 lg:col-span-2">
                <h3 class="font-medium text-sm mb-2">月度收支趋势（近12月）</h3>
                <div style="height: 220px"><Bar v-if="monthlyChartData" :data="monthlyChartData" :options="chartOpts" /></div>
              </div>
              <div class="bg-white rounded-lg shadow-sm p-4">
                <h3 class="font-medium text-sm mb-2">收入结构（近12月）</h3>
                <div style="height: 220px"><Doughnut v-if="incomeChartData" :data="incomeChartData" :options="doughnutOpts" /></div>
              </div>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div class="bg-white rounded-lg shadow-sm p-4">
                <h3 class="font-medium text-sm mb-2">支出结构（近90天）</h3>
                <div style="height: 220px"><Doughnut v-if="expenseChartData" :data="expenseChartData" :options="doughnutOpts" /></div>
              </div>
              <div class="bg-white rounded-lg shadow-sm p-4 lg:col-span-2">
                <h3 class="font-medium text-sm mb-2">收支时间窗口（滚动 6/3/1 月）</h3>
                <div style="height: 220px"><Bar v-if="windowChartData" :data="windowChartData" :options="chartOpts" /></div>
              </div>
            </div>

            <!-- 明细（两列） -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 text-xs">
              <div class="bg-white rounded-lg shadow-sm p-4">
                <h3 class="font-medium text-sm mb-2">收入画像（近12月）</h3>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">总收入</span>
                  <span class="font-mono">{{ fmt(snapshot.income_profile?.['12m_total']) }}</span></div>
                <div v-for="(v, k) in (snapshot.income_profile?.by_subcategory || {})" :key="k" class="flex justify-between py-0.5">
                  <span>{{ k }}</span>
                  <span class="font-mono">{{ fmt(v.total_12m) }}（{{ ((v.share || 0) * 100).toFixed(1) }}%）</span>
                </div>
                <h3 class="font-medium text-sm mb-2 mt-3">投资画像</h3>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">持仓市值 / 浮动盈亏</span>
                  <span class="font-mono">{{ fmt(snapshot.investment_profile?.current_total_value) }} / {{ fmt(snapshot.investment_profile?.current_total_pnl) }}</span></div>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">累计投入 / 回收</span>
                  <span class="font-mono">{{ fmt(snapshot.investment_profile?.total_deposits) }} / {{ fmt(snapshot.investment_profile?.total_withdrawals) }}</span></div>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">XIRR 年化</span>
                  <span class="font-mono">{{ snapshot.investment_profile?.xirr_annualized_pct != null ? snapshot.investment_profile.xirr_annualized_pct + '%' : '—' }}</span></div>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">近12月建仓</span>
                  <span class="font-mono text-[10px]">{{ Object.entries(snapshot.investment_profile?.['12m_new_positions_by_month'] || {}).map(([m, n]) => `${m.slice(2)}:${n}`).join(' ') || '—' }}</span></div>
              </div>

              <div class="bg-white rounded-lg shadow-sm p-4">
                <h3 class="font-medium text-sm mb-2">购房画像（{{ (snapshot.housing_profile?.target_cities || []).join(' / ') }}，{{ snapshot.housing_profile?.target_years }} 年内 {{ snapshot.housing_profile?.area_sqm }}㎡）</h3>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">公积金月缴 / 年累积</span>
                  <span class="font-mono">{{ fmt(snapshot.housing_profile?.housing_fund?.monthly_total) }} / {{ fmt(snapshot.housing_profile?.housing_fund?.annual_accumulation) }}</span></div>
                <div v-for="s in (snapshot.housing_profile?.scenarios || [])" :key="s.city_key" class="flex justify-between py-0.5">
                  <span>{{ s.city }}：总价/首付</span>
                  <span class="font-mono">{{ (s.est_total_price / 10000).toFixed(0) }}万 / {{ (s.down_payment / 10000).toFixed(0) }}万 · 月供 {{ s.monthly_payment.toLocaleString() }}
                    <span :class="s.affordable_with_fund ? 'text-income-color' : 'text-expense-color'">{{ s.affordable_with_fund ? '✓' : '✗' }}</span>
                  </span>
                </div>
                <h3 class="font-medium text-sm mb-2 mt-3">风险敞口与支出节奏</h3>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">现金 / 投资占比</span>
                  <span class="font-mono">{{ ((snapshot.risk_exposure?.cash_share ?? 0) * 100).toFixed(0) }}% / {{ ((snapshot.risk_exposure?.invest_share ?? 0) * 100).toFixed(0) }}%</span></div>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">近30天支出 / 2σ阈值</span>
                  <span class="font-mono">{{ fmt(snapshot.expense_rhythm?.last30d_total) }} / {{ fmt(snapshot.expense_rhythm?.anomaly_threshold_2sigma) }}</span></div>
                <h3 class="font-medium text-sm mb-2 mt-3">投资账户对账（自证勾稽）</h3>
                <div class="flex justify-between py-0.5"><span class="text-text-muted">账户余额 / 差额</span>
                  <span class="font-mono">{{ fmt(snapshot.investment_reconciliation?.account_balance) }} /
                    <span :class="(snapshot.investment_reconciliation?.difference ?? 0) === 0 ? 'text-income-color' : 'text-expense-color font-medium'">{{ fmt(snapshot.investment_reconciliation?.difference) }}</span></span></div>
              </div>
            </div>

            <!-- 投资组合书面配置 -->
            <div class="bg-white rounded-lg shadow-sm p-4 text-xs" v-if="snapshot.portfolio_plan">
              <h3 class="font-medium text-sm mb-2">
                投资组合书面配置
                <span v-if="snapshot.portfolio_plan.active_strategy" class="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-income-bg text-income-color font-normal">
                  执行中：{{ snapshot.portfolio_plan.active_strategy.name }} v{{ snapshot.portfolio_plan.active_strategy.version }}
                </span>
              </h3>
              <div v-if="snapshot.portfolio_plan.current_target_weights" class="mb-2">
                <div class="text-text-muted mb-1">当前目标权重（信号 {{ snapshot.portfolio_plan.current_target_weights.signal_run_date }}）</div>
                <div class="flex flex-wrap gap-1">
                  <span v-for="(w, s) in (snapshot.portfolio_plan.current_target_weights.weights || {})" :key="s"
                    class="px-1.5 py-0.5 rounded bg-bg-tertiary font-mono">{{ s }} {{ (w * 100).toFixed(1) }}%</span>
                </div>
              </div>
              <div v-if="(snapshot.portfolio_plan.recent_backtests || []).length" class="overflow-x-auto">
                <table class="w-full">
                  <thead class="text-text-muted">
                    <tr class="border-b border-border-default">
                      <th class="text-left py-1 font-normal">策略</th>
                      <th class="text-right py-1 font-normal">回测日</th>
                      <th class="text-right py-1 font-normal">年化</th>
                      <th class="text-right py-1 font-normal">夏普</th>
                      <th class="text-right py-1 font-normal">最大回撤</th>
                      <th class="text-right py-1 font-normal">超额</th>
                      <th class="text-right py-1 font-normal">年换手</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="b in snapshot.portfolio_plan.recent_backtests" :key="b.strategy + b.version"
                      class="border-b border-border-default/50">
                      <td class="py-1">{{ b.strategy }} <span class="text-text-muted">v{{ b.version }}</span></td>
                      <td class="text-right font-mono">{{ b.backtest_date }}</td>
                      <td class="text-right font-mono" :class="b.ann_return_pct >= 0 ? 'text-income-color' : 'text-expense-color'">{{ b.ann_return_pct }}%</td>
                      <td class="text-right font-mono">{{ b.sharpe }}</td>
                      <td class="text-right font-mono text-expense-color">{{ b.max_drawdown_pct }}%</td>
                      <td class="text-right font-mono">{{ b.alpha_ann_pct }}%</td>
                      <td class="text-right font-mono">{{ b.turnover_annual }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="text-text-muted mt-2">
                策略库共 {{ (snapshot.portfolio_plan.strategies || []).length }} 个策略
                <span v-for="s in (snapshot.portfolio_plan.strategies || []).slice(0, 10)" :key="s.id" class="ml-1 px-1 rounded bg-bg-tertiary">
                  {{ s.name }}v{{ s.version }}{{ s.activated ? '★' : '' }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- ══════════ 个人画像视图 ══════════ -->
      <template v-else-if="viewMode === 'profile'">
        <div class="flex-1 overflow-y-auto p-5">
          <div class="max-w-3xl mx-auto bg-white rounded-lg shadow-sm p-4">
            <h3 class="font-medium text-sm mb-2">个人画像（AI 的人设文档——写清你的真实背景，AI 才不会说废话）</h3>
            <textarea v-model="profileMd" rows="20"
              class="w-full px-3 py-2 text-xs font-mono border border-border-default rounded-md resize-y" />
            <div class="flex gap-2 mt-2">
              <button @click="saveProfile" :disabled="savingProfile" class="btn-primary text-xs disabled:opacity-50">
                {{ savingProfile ? '保存中…' : '保存画像' }}
              </button>
              <button @click="resetProfile" class="btn-secondary text-xs">恢复默认</button>
            </div>
            <div v-if="profileMsg" class="text-xs mt-1" :class="profileOk ? 'text-income-color' : 'text-expense-color'">
              {{ profileMsg }}
            </div>
          </div>
        </div>
      </template>

      <!-- ══════════ 行动清单视图 ══════════ -->
      <template v-else>
        <div class="flex-1 overflow-y-auto p-5">
          <div class="max-w-3xl mx-auto bg-white rounded-lg shadow-sm p-4">
            <h3 class="font-medium text-sm mb-2">行动清单 / 目标</h3>
            <div v-if="!actions.length" class="text-xs text-text-muted py-2">还没有行动项——可以让 AI 在回答后把建议转成行动</div>
            <div class="space-y-1.5 mb-3">
              <div v-for="a in actions" :key="a.id"
                class="flex items-start gap-2 p-2 rounded border border-border-default">
                <input type="checkbox" :checked="a.status === 'done'" @change="toggleAction(a)" class="mt-0.5" />
                <div class="min-w-0 flex-1">
                  <div class="text-xs" :class="a.status === 'done' ? 'line-through text-text-muted' : 'font-medium'">
                    {{ a.title }}
                    <span class="ml-1 text-[10px] px-1 rounded bg-bg-tertiary text-text-muted">{{ actionCategoryLabel(a.category) }}</span>
                  </div>
                  <div v-if="a.detail" class="text-[10px] text-text-muted mt-0.5 whitespace-pre-wrap">{{ a.detail }}</div>
                  <div class="text-[10px] text-text-muted mt-0.5">
                    <span v-if="a.target_amount != null" class="font-mono">目标 {{ fmt(a.target_amount) }} · </span>
                    <span v-if="a.due_date">截止 {{ a.due_date }}</span>
                  </div>
                </div>
                <button @click="deleteAction(a)" class="text-[10px] text-expense-color shrink-0 hover:underline">删除</button>
              </div>
            </div>
            <div class="space-y-1.5 border-t border-border-default pt-2">
              <input v-model="newAction.title" placeholder="行动项标题，如：每月定投 5,000 到指数增强"
                class="w-full px-2 py-1 text-xs border border-border-default rounded" />
              <div class="flex gap-1.5">
                <select v-model="newAction.category" class="px-1 py-1 text-xs border border-border-default rounded flex-none">
                  <option value="emergency">应急</option>
                  <option value="invest">投资</option>
                  <option value="housing">购房</option>
                  <option value="spending">消费</option>
                  <option value="income">收入</option>
                  <option value="other">其他</option>
                </select>
                <input v-model="newAction.due_date" type="date" class="px-1 py-1 text-xs border border-border-default rounded flex-none" />
                <button @click="addAction" :disabled="!newAction.title.trim()" class="btn-primary text-xs px-3 disabled:opacity-50">添加</button>
              </div>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { Bar, Doughnut } from 'vue-chartjs'
import {
  Chart as ChartJS, Title, Tooltip, Legend, ArcElement, BarElement,
  CategoryScale, LinearScale, PointElement, LineElement, Filler,
} from 'chart.js'
import { Plus, Trash2, MessageSquare, BarChart3, User, ListChecks } from 'lucide-vue-next'

ChartJS.register(Title, Tooltip, Legend, ArcElement, BarElement, CategoryScale, LinearScale, PointElement, LineElement, Filler)

marked.setOptions({ breaks: true, gfm: true })

function renderMd(content: string): string {
  return DOMPurify.sanitize(marked.parse(content || '') as string)
}
import { useApi, apiLong } from '@/composables/useApi'
import { useAuthStore } from '@/stores/auth'

const api = useApi()
const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([])
const question = ref('')
const asking = ref(false)
const askError = ref('')
const reasoningText = ref('')
const showReasoning = ref(true)
const reasoningBox = ref<HTMLElement | null>(null)
const snapshot = ref<any>(null)
const profileMd = ref('')
const savingProfile = ref(false)
const profileMsg = ref('')
const profileOk = ref(false)
const chatBox = ref<HTMLElement | null>(null)

// 视图切换
const viewMode = ref<'chat' | 'snapshot' | 'profile' | 'actions'>('chat')
const viewTabs = [
  { key: 'chat', label: '对话', icon: MessageSquare },
  { key: 'snapshot', label: '数据画像', icon: BarChart3 },
  { key: 'profile', label: '个人画像', icon: User },
  { key: 'actions', label: '行动清单', icon: ListChecks },
] as const

function newConversation() {
  if (messages.value.length && !confirm('开始新对话？当前消息仍在归档中。')) return
  messages.value = []
  askError.value = ''
  reasoningText.value = ''
  viewingSession.value = null
  archiveDetail.value = null
  archiveMessages.value = []
  viewMode.value = 'chat'
}

// ---- 对话归档（左侧栏） ----
const archiveLoading = ref(false)
const archiveSessions = ref<any[]>([])
const viewingSession = ref<any | null>(null)
const archiveDetail = ref<any | null>(null)
const archiveMessages = ref<any[]>([])

async function loadArchiveSessions() {
  archiveLoading.value = true
  try {
    const { data } = await api.get('/ai-advisor/archive/sessions')
    archiveSessions.value = data
  } catch { archiveSessions.value = [] } finally {
    archiveLoading.value = false
  }
}

async function openArchiveDetail(s: any) {
  try {
    const { data } = await api.get(`/ai-advisor/archive/sessions/${s.session_id}`)
    archiveMessages.value = data
    viewingSession.value = s
    archiveDetail.value = s
    viewMode.value = 'chat'
  } catch { /* 列表保留 */ }
}

function closeArchiveDetail() {
  viewingSession.value = null
  archiveDetail.value = null
  archiveMessages.value = []
}

async function deleteArchiveSession(s: any) {
  if (!confirm('删除这一轮对话（含全部消息）？不可恢复。')) return
  try {
    await api.delete(`/ai-advisor/archive/sessions/${s.session_id}`)
    if (viewingSession.value?.session_id === s.session_id) closeArchiveDetail()
    await loadArchiveSessions()
  } catch { /* ignore */ }
}

// ---- 行动清单 ----
const actions = ref<any[]>([])
const newAction = ref({ title: '', category: 'other', due_date: '' })

const ACTION_CATEGORY_LABELS: Record<string, string> = {
  emergency: '应急', invest: '投资', housing: '购房',
  spending: '消费', income: '收入', other: '其他',
}
function actionCategoryLabel(c: string): string {
  return ACTION_CATEGORY_LABELS[c] || c || '其他'
}

function fmt(v: number | null | undefined): string {
  return v == null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 }) + ' 元'
}
function fmtPct(v: number | null | undefined): string {
  return v == null ? '—' : (v * 100).toFixed(1) + '%'
}

// ---- 图表 ----
const chartOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { position: 'top' as const, labels: { boxWidth: 12, font: { size: 11 } } } },
  scales: { x: { ticks: { font: { size: 10 } } }, y: { ticks: { font: { size: 10 } } } },
}
const doughnutOpts = {
  responsive: true, maintainAspectRatio: false,
  plugins: { legend: { position: 'right' as const, labels: { boxWidth: 12, font: { size: 10 } } } },
}

const PALETTE = ['#4CAF50', '#F44336', '#2196F3', '#FF9800', '#9C27B0', '#00BCD4', '#8BC34A', '#FF5722', '#607D8B', '#E91E63']

const monthlyChartData = computed(() => {
  const m = snapshot.value?.monthly_12m || {}
  const months = Object.keys(m).sort()
  if (!months.length) return null
  return {
    labels: months.map(x => x.slice(2)),
    datasets: [
      { label: '收入', data: months.map(x => m[x].income || 0), backgroundColor: '#4CAF50' },
      { label: '支出', data: months.map(x => m[x].expense || 0), backgroundColor: '#F44336' },
    ],
  }
})

const incomeChartData = computed(() => {
  const sub = snapshot.value?.income_profile?.by_subcategory || {}
  const entries = Object.entries(sub).filter(([, v]: any) => (v.total_12m || 0) > 0)
  if (!entries.length) return null
  return {
    labels: entries.map(([k]) => k),
    datasets: [{ data: entries.map(([, v]: any) => v.total_12m), backgroundColor: PALETTE }],
  }
})

const expenseChartData = computed(() => {
  const cats = (snapshot.value?.expense_90d_by_category || []).slice(0, 8)
  if (!cats.length) return null
  return {
    labels: cats.map((c: any) => c.category),
    datasets: [{ data: cats.map((c: any) => c.total), backgroundColor: PALETTE }],
  }
})

const windowChartData = computed(() => {
  const tw = snapshot.value?.time_windows
  if (!tw) return null
  const labels = ['近1月', '近3月', '近6月']
  return {
    labels,
    datasets: [
      { label: '收入', data: ['1m', '3m', '6m'].map(k => tw[k]?.income ?? 0), backgroundColor: '#4CAF50' },
      { label: '支出', data: ['1m', '3m', '6m'].map(k => tw[k]?.expense ?? 0), backgroundColor: '#F44336' },
    ],
  }
})

async function loadSnapshot() {
  try {
    const { data } = await api.get('/ai-advisor/data-summary')
    snapshot.value = data
  } catch { /* 快照加载失败不阻断聊天 */ }
}

async function loadProfile() {
  try {
    const { data } = await api.get('/ai-advisor/profile')
    profileMd.value = data.profile_md
  } catch { /* 默认模板由后端返回 */ }
}

async function saveProfile() {
  savingProfile.value = true
  try {
    await api.put('/ai-advisor/profile', { profile_md: profileMd.value })
    profileMsg.value = '已保存'
    profileOk.value = true
  } catch (e: any) {
    profileMsg.value = e?.response?.data?.detail || '保存失败'
    profileOk.value = false
  } finally {
    savingProfile.value = false
  }
}

async function resetProfile() {
  try {
    const { data } = await api.get('/ai-advisor/profile', { params: { default: true } })
    profileMd.value = data.profile_md
    profileMsg.value = '已恢复默认模板（记得点保存）'
    profileOk.value = true
  } catch {
    profileMsg.value = '获取默认模板失败'
    profileOk.value = false
  }
}

async function loadActions() {
  try {
    const { data } = await api.get('/ai-advisor/actions')
    actions.value = data
  } catch { actions.value = [] }
}

async function addAction() {
  const title = newAction.value.title.trim()
  if (!title) return
  try {
    await api.post('/ai-advisor/actions', {
      title,
      category: newAction.value.category,
      due_date: newAction.value.due_date || null,
    })
    newAction.value = { title: '', category: newAction.value.category, due_date: '' }
    await loadActions()
  } catch { /* ignore */ }
}

async function toggleAction(a: any) {
  try {
    await api.put(`/ai-advisor/actions/${a.id}`, { status: a.status === 'done' ? 'todo' : 'done' })
    a.status = a.status === 'done' ? 'todo' : 'done'
  } catch { /* ignore */ }
}

async function deleteAction(a: any) {
  try {
    await api.delete(`/ai-advisor/actions/${a.id}`)
    await loadActions()
  } catch { /* ignore */ }
}

const lastQuestion = ref('')

async function ask() {
  const q = question.value.trim()
  if (!q || asking.value) return
  question.value = ''
  messages.value.push({ role: 'user', content: q })
  await streamInto(q)
}

async function retryLast() {
  if (asking.value || !lastQuestion.value) return
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant' && !last.content) messages.value.pop()
  messages.value.push({ role: 'assistant', content: '' })
  await streamInto(lastQuestion.value)
}

async function streamInto(q: string) {
  lastQuestion.value = q
  asking.value = true
  askError.value = ''
  reasoningText.value = ''
  showReasoning.value = true
  await nextTick()
  chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight })
  const authStore = useAuthStore()
  const idx = messages.value.length - 1
  messages.value[idx].content = ''
  try {
    const resp = await fetch('/api/ai-advisor/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${authStore.token}` },
      body: JSON.stringify({ question: q }),
    })
    if (!resp.ok || !resp.body) {
      let detail = `HTTP ${resp.status}`
      try { detail = (await resp.json()).detail || detail } catch { /* keep status text */ }
      throw new Error(detail)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let i
      while ((i = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, i).trim()
        buf = buf.slice(i + 2)
        if (!frame.startsWith('data:')) continue
        let payload: any
        try { payload = JSON.parse(frame.slice(5).trim()) } catch { continue }
        if (payload.reasoning) {
          reasoningText.value += payload.reasoning
          await nextTick()
          if (reasoningBox.value) reasoningBox.value.scrollTop = reasoningBox.value.scrollHeight
        }
        if (payload.delta) {
          if (showReasoning.value) showReasoning.value = false
          messages.value[idx].content += payload.delta
          await nextTick()
          chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight })
        }
        if (payload.error) {
          askError.value = messages.value[idx].content
            ? `生成中断（${payload.error}）——已保留以上内容，可重新生成`
            : payload.error
        }
      }
    }
    await loadSnapshot()
    await loadArchiveSessions()   // 新对话落库后刷新左侧会话列表
  } catch (e: any) {
    const partial = !!messages.value[idx].content
    askError.value = (e?.message || String(e)) + (partial ? '——已保留部分内容，可重新生成' : '')
  } finally {
    asking.value = false
  }
}

onMounted(() => { loadSnapshot(); loadProfile(); loadArchiveSessions(); loadActions() })
</script>

<style scoped>
.md-body { line-height: 1.65; }
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  font-weight: 700;
  margin: 0.9em 0 0.4em;
  padding-bottom: 0.15em;
  border-bottom: 1px solid rgba(0,0,0,0.08);
}
.md-body :deep(h1) { font-size: 1.25rem; }
.md-body :deep(h2) { font-size: 1.12rem; }
.md-body :deep(h3) { font-size: 1rem; border-bottom: none; }
.md-body :deep(h4) { font-size: 0.95rem; border-bottom: none; }
.md-body :deep(p) { margin: 0.5em 0; }
.md-body :deep(h2 + p),
.md-body :deep(h3 + p) { margin-top: 0.25em; }
.md-body :deep(ul),
.md-body :deep(ol) { margin: 0.5em 0; padding-left: 1.4em; }
.md-body :deep(li) { margin: 0.25em 0; }
.md-body :deep(strong) { font-weight: 700; color: inherit; }
.md-body :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 0.05em 0.3em;
  border-radius: 3px;
  font-size: 0.85em;
  font-family: ui-monospace, monospace;
}
.md-body :deep(pre) {
  background: rgba(0,0,0,0.05);
  padding: 0.6em;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
.md-body :deep(pre code) { background: transparent; padding: 0; }
.md-body :deep(table) {
  border-collapse: collapse;
  margin: 0.6em 0;
  font-size: 0.88em;
  width: 100%;
}
.md-body :deep(th) { background: rgba(0,0,0,0.04); font-weight: 600; }
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid rgba(0,0,0,0.12);
  padding: 0.3em 0.55em;
  text-align: left;
}
.md-body :deep(blockquote) {
  border-left: 3px solid rgba(0,0,0,0.15);
  padding-left: 0.7em;
  margin: 0.5em 0;
  opacity: 0.85;
}
.md-body :deep(hr) { border: none; border-top: 1px solid rgba(0,0,0,0.1); margin: 0.8em 0; }
.md-body :deep(a) { text-decoration: underline; }
.md-body :deep(> *:first-child) { margin-top: 0; }
.md-body :deep(> *:last-child) { margin-bottom: 0; }
</style>
