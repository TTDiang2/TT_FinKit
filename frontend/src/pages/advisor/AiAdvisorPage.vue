<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold">AI 财富审计师</h2>
        <p class="text-xs text-text-muted mt-0.5">
          严厉 · 理性 · 冷静 · 只引用真实数据 · 不提供情绪价值
        </p>
      </div>
      <div class="flex gap-2 flex-wrap justify-end">
        <button @click="showData = !showData" class="btn-secondary text-xs">
          {{ showData ? '隐藏数据画像' : '查看数据画像' }}
        </button>
        <button @click="showProfile = !showProfile" class="btn-secondary text-xs">
          {{ showProfile ? '隐藏画像编辑' : '编辑个人画像' }}
        </button>
        <button @click="toggleArchive" class="btn-secondary text-xs">
          {{ showArchive ? '隐藏对话归档' : '对话归档' }}
        </button>
        <button @click="toggleActions" class="btn-secondary text-xs">
          {{ showActions ? '隐藏行动清单' : '行动清单' }}
        </button>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <!-- 左：对话 -->
      <div class="lg:col-span-2">
        <div class="bg-white rounded-lg shadow-sm p-4 flex flex-col" style="min-height: 60vh">
          <div ref="chatBox" class="flex-1 space-y-3 overflow-y-auto mb-3" style="max-height: 62vh">
            <div v-if="!messages.length"
              class="text-sm text-text-muted py-10 text-center">
              问点什么，例如：<br>「评价一下我这一个月的消费决策」<br>「我的应急储备够不够？离目标差多少」<br>「审视我的投资组合暴露是否与购房目标冲突」
            </div>
            <div v-for="(m, i) in messages" :key="i"
              :class="['max-w-[85%] rounded-lg px-3 py-2 text-sm',
                       m.role === 'user' ? 'ml-auto bg-accent-primary/10' : 'bg-bg-tertiary']">
              <div v-if="m.role === 'assistant'" class="text-xs text-text-muted mb-1">财富审计师</div>
              <div v-if="m.role === 'assistant'" class="md-body" v-html="renderMd(m.content)"></div>
              <div v-else class="whitespace-pre-wrap">{{ m.content }}</div>
            </div>
            <div v-if="reasoningText"
              id="reasoning-box"
              class="max-w-[85%] bg-bg-secondary border border-border-default rounded-lg px-3 py-2 text-xs text-text-muted">
              <div class="flex items-center justify-between mb-1">
                <span>
                  <template v-if="asking && !messages[messages.length - 1]?.content">🤔 思考中…（逐字输出）</template>
                  <template v-else>🤔 深度思考过程</template>
                </span>
                <button @click="showReasoning = !showReasoning" class="underline">
                  {{ showReasoning ? '收起' : `展开（${reasoningText.length} 字）` }}
                </button>
              </div>
              <div v-show="showReasoning" ref="reasoningBox" class="whitespace-pre-wrap" style="max-height: 220px; overflow-y: auto">{{ reasoningText.slice(-1500) }}</div>
            </div>
            <div v-if="asking && !reasoningText && !messages[messages.length - 1]?.content" class="text-sm text-text-muted">审计师正在核对数据，首字生成可能需要数十秒…</div>
            <div v-if="askError" class="text-xs text-expense-color">
              {{ askError }}
              <button v-if="lastQuestion && !asking" @click="retryLast" class="underline ml-1 font-medium">重新生成</button>
            </div>
          </div>
          <div class="flex gap-2">
            <textarea v-model="question" rows="2"
              placeholder="例如：评价我最近一个月的消费决策和财务状况"
              class="flex-1 px-3 py-2 text-sm border border-border-default rounded-md resize-none" />
            <button @click="ask" :disabled="asking || !question.trim()" class="btn-primary self-end disabled:opacity-50">
              {{ asking ? '分析中…' : '提交' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 右：数据画像 + 画像编辑 -->
      <div class="space-y-4">
        <div v-if="showData" class="bg-white rounded-lg shadow-sm p-4 text-xs">
          <h3 class="font-medium text-sm mb-2">数据画像（AI 看到的同一份数据）</h3>
          <div v-if="snapshot" class="space-y-2">
            <div class="flex justify-between"><span class="text-text-muted">近6月储蓄率</span>
              <span :class="(snapshot.savings_6m?.savings_rate ?? 0) < 0.1 ? 'text-expense-color font-medium' : ''">
                {{ fmtPct(snapshot.savings_6m?.savings_rate) }}</span></div>
            <div class="flex justify-between"><span class="text-text-muted">应急覆盖月数</span>
              <span :class="(snapshot.emergency_reserve?.cover_months ?? 9) < 6 ? 'text-expense-color font-medium' : ''">
                {{ snapshot.emergency_reserve?.cover_months ?? '—' }} 个月</span></div>
            <div class="flex justify-between"><span class="text-text-muted">现金总额</span>
              <span>{{ fmt(snapshot.cash_total) }}</span></div>
            <div class="flex justify-between"><span class="text-text-muted">投资市值</span>
              <span>{{ fmt(snapshot.portfolio?.total_value) }}</span></div>
            <div class="flex justify-between"><span class="text-text-muted">投资盈亏</span>
              <span :class="(snapshot.portfolio?.total_pnl ?? 0) >= 0 ? 'text-expense-color' : 'text-income-color'">
                {{ fmt(snapshot.portfolio?.total_pnl) }}</span></div>
            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">近90天支出结构</div>
              <div v-for="c in (snapshot.expense_90d_by_category || []).slice(0, 6)" :key="c.category"
                class="flex justify-between py-0.5">
                <span>{{ c.category }}</span>
                <span class="font-mono">{{ fmt(c.total) }}（{{ ((c.share || 0) * 100).toFixed(0) }}%）</span>
              </div>
            </div>

            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">收支时间窗口（滚动）</div>
              <div v-for="w in ['6m', '3m', '1m']" :key="w" class="flex justify-between py-0.5">
                <span>近{{ w === '6m' ? '6月' : w === '3m' ? '3月' : '1月' }}</span>
                <span class="font-mono">
                  {{ fmt(snapshot.time_windows?.[w]?.income) }} / {{ fmt(snapshot.time_windows?.[w]?.expense) }}
                  <span :class="(snapshot.time_windows?.[w]?.net ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">
                    （{{ fmt(snapshot.time_windows?.[w]?.net) }}）</span>
                </span>
              </div>
            </div>

            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">收入画像（近12月）</div>
              <div class="flex justify-between py-0.5"><span>总收入</span>
                <span class="font-mono">{{ fmt(snapshot.income_profile?.['12m_total']) }}</span></div>
              <div v-for="(v, k) in (snapshot.income_profile?.by_subcategory || {})" :key="k" class="flex justify-between py-0.5">
                <span>{{ k }}</span>
                <span class="font-mono">{{ fmt(v.total_12m) }}（{{ ((v.share || 0) * 100).toFixed(1) }}%）</span>
              </div>
            </div>

            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">投资画像</div>
              <div class="flex justify-between py-0.5"><span>持仓市值 / 浮动盈亏</span>
                <span class="font-mono">{{ fmt(snapshot.investment_profile?.current_total_value) }} /
                  <span :class="(snapshot.investment_profile?.current_total_pnl ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ fmt(snapshot.investment_profile?.current_total_pnl) }}</span></span></div>
              <div class="flex justify-between py-0.5"><span>累计落袋盈亏（含分红）</span>
                <span class="font-mono" :class="(snapshot.investment_profile?.realized_pnl ?? 0) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ fmt(snapshot.investment_profile?.realized_pnl) }}</span></div>
              <div class="flex justify-between py-0.5"><span>累计投入 / 累计回收</span>
                <span class="font-mono">{{ fmt(snapshot.investment_profile?.total_deposits) }} / {{ fmt(snapshot.investment_profile?.total_withdrawals) }}</span></div>
              <div class="flex justify-between py-0.5"><span>XIRR 年化（投资tab同款）</span>
                <span class="font-mono">{{ snapshot.investment_profile?.xirr_annualized_pct != null ? snapshot.investment_profile.xirr_annualized_pct + '%' : '—' }}</span></div>
              <div class="flex justify-between py-0.5"><span>Top1 集中度</span>
                <span class="font-mono">{{ snapshot.investment_profile?.current_top1_concentration != null ? ((snapshot.investment_profile.current_top1_concentration * 100).toFixed(1) + '%') : '—' }}</span></div>
              <div class="flex justify-between py-0.5"><span>近12月建仓（按月）</span>
                <span class="font-mono text-[10px]">{{ Object.entries(snapshot.investment_profile?.['12m_new_positions_by_month'] || {}).map(([m, n]) => `${m.slice(2)}:${n}`).join(' ') || '—' }}</span></div>
            </div>

            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">投资账户对账（自证勾稽）</div>
              <div class="flex justify-between py-0.5"><span>累计入金 / 出金</span>
                <span class="font-mono">{{ fmt(snapshot.investment_reconciliation?.total_deposits) }} /
                  {{ fmt(snapshot.investment_reconciliation?.total_withdrawals) }}</span></div>
              <div class="flex justify-between py-0.5"><span>净本金 + 累计盈亏</span>
                <span class="font-mono">{{ fmt(snapshot.investment_reconciliation?.net_principal) }} +
                  {{ fmt(snapshot.investment_reconciliation?.accumulated_pnl) }}</span></div>
              <div class="flex justify-between py-0.5"><span>账户余额 / 差额</span>
                <span class="font-mono">{{ fmt(snapshot.investment_reconciliation?.account_balance) }} /
                  <span :class="(snapshot.investment_reconciliation?.difference ?? 0) === 0 ? 'text-income-color' : 'text-expense-color font-medium'">
                    {{ fmt(snapshot.investment_reconciliation?.difference) }}</span></span></div>
            </div>

            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">购房画像（{{ (snapshot.housing_profile?.target_cities || []).join(' / ') }}，{{ snapshot.housing_profile?.target_years }} 年内 {{ snapshot.housing_profile?.area_sqm }}㎡）</div>
              <div class="flex justify-between py-0.5"><span>公积金月缴 / 年累积</span>
                <span class="font-mono">{{ fmt(snapshot.housing_profile?.housing_fund?.monthly_total) }} /
                  {{ fmt(snapshot.housing_profile?.housing_fund?.annual_accumulation) }}</span></div>
              <div class="flex justify-between py-0.5"><span>目标年公积金累积</span>
                <span class="font-mono">{{ fmt(snapshot.housing_profile?.housing_fund?.accumulation_by_target_year) }}</span></div>
              <div v-for="s in (snapshot.housing_profile?.scenarios || [])" :key="s.city_key"
                class="flex justify-between py-0.5">
                <span>{{ s.city }}：总价/首付</span>
                <span class="font-mono">{{ (s.est_total_price / 10000).toFixed(0) }}万 /
                  {{ (s.down_payment / 10000).toFixed(0) }}万 · 月供 {{ s.monthly_payment.toLocaleString() }}
                  <span :class="s.affordable_with_fund ? 'text-income-color' : 'text-expense-color'">{{ s.affordable_with_fund ? '✓可承受' : '✗超限' }}</span>
                </span>
              </div>
            </div>

            <div class="pt-2 border-t border-border-default">
              <div class="text-text-muted mb-1">支出节奏与风险敞口</div>
              <div class="flex justify-between py-0.5"><span>近30天支出</span>
                <span class="font-mono">{{ fmt(snapshot.expense_rhythm?.last30d_total) }}</span></div>
              <div class="flex justify-between py-0.5"><span>异常支出阈值（2σ）</span>
                <span class="font-mono">{{ fmt(snapshot.expense_rhythm?.anomaly_threshold_2sigma) }}</span></div>
              <div class="flex justify-between py-0.5"><span>现金 / 投资占比</span>
                <span class="font-mono">{{ ((snapshot.risk_exposure?.cash_share ?? 0) * 100).toFixed(0) }}% /
                  {{ ((snapshot.risk_exposure?.invest_share ?? 0) * 100).toFixed(0) }}%</span></div>
              <div class="flex justify-between py-0.5"><span>应急覆盖</span>
                <span class="font-mono">{{ snapshot.risk_exposure?.emergency_cover_months ?? '—' }} 个月</span></div>
            </div>
          </div>
          <div v-else class="text-text-muted">加载中…</div>
        </div>

        <div v-if="showProfile" class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="font-medium text-sm mb-2">个人画像（AI 的人设文档）</h3>
          <textarea v-model="profileMd" rows="14"
            class="w-full px-2 py-1.5 text-xs font-mono border border-border-default rounded-md resize-y" />
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

        <!-- 对话归档 -->
        <div v-if="showArchive" class="bg-white rounded-lg shadow-sm p-4">
          <div class="flex items-center justify-between mb-2">
            <h3 class="font-medium text-sm">对话归档（本地）</h3>
            <button v-if="archiveDetail" @click="closeArchiveDetail" class="text-xs underline text-text-muted">返回列表</button>
          </div>

          <template v-if="!archiveDetail">
            <div v-if="archiveLoading" class="text-xs text-text-muted">加载中…</div>
            <div v-else-if="!archiveSessions.length" class="text-xs text-text-muted py-4 text-center">暂无历史对话</div>
            <div v-else class="space-y-1.5 max-h-[60vh] overflow-y-auto">
              <div v-for="s in archiveSessions" :key="s.session_id"
                class="flex items-start justify-between gap-2 p-2 rounded border border-border-default hover:bg-bg-secondary cursor-pointer"
                @click="openArchiveDetail(s)">
                <div class="min-w-0">
                  <div class="text-xs font-medium truncate">{{ s.first_question || '（无提问记录）' }}</div>
                  <div class="text-[10px] text-text-muted mt-0.5">
                    {{ s.started_at?.slice(0, 16) }} · {{ Math.ceil((s.msg_count || 0) / 2) }} 轮
                  </div>
                </div>
                <button @click.stop="deleteArchiveSession(s)"
                  class="text-[10px] text-expense-color shrink-0 hover:underline">删除</button>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="text-[10px] text-text-muted mb-2">{{ archiveDetail.started_at?.slice(0, 16) }}</div>
            <div class="space-y-2 max-h-[60vh] overflow-y-auto">
              <div v-for="m in archiveMessages" :key="m.id"
                :class="['max-w-[92%] rounded-lg px-3 py-2 text-xs',
                         m.role === 'user' ? 'ml-auto bg-accent-primary/10' : 'bg-bg-tertiary']">
                <div v-if="m.role === 'assistant'" class="text-[10px] text-text-muted mb-1">财富审计师</div>
                <div v-if="m.role === 'assistant'" class="md-body" v-html="renderMd(m.content)"></div>
                <div v-else class="whitespace-pre-wrap">{{ m.content }}</div>
              </div>
            </div>
          </template>
        </div>

        <!-- 行动清单 -->
        <div v-if="showActions" class="bg-white rounded-lg shadow-sm p-4">
          <h3 class="font-medium text-sm mb-2">行动清单 / 目标</h3>
          <div v-if="!actions.length" class="text-xs text-text-muted py-2">还没有行动项——可以让 AI 在回答后把建议转成行动</div>
          <div class="space-y-1.5 max-h-[40vh] overflow-y-auto mb-3">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

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
const showData = ref(true)
const showProfile = ref(false)
const profileMd = ref('')
const savingProfile = ref(false)
const profileMsg = ref('')
const profileOk = ref(false)
const chatBox = ref<HTMLElement | null>(null)

// 对话归档
const showArchive = ref(false)
const archiveLoading = ref(false)
const archiveSessions = ref<any[]>([])
const archiveDetail = ref<any | null>(null)
const archiveMessages = ref<any[]>([])

// 行动清单
const showActions = ref(false)
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

// ---- 对话归档 ----

async function toggleArchive() {
  showArchive.value = !showArchive.value
  if (showArchive.value) {
    closeArchiveDetail()
    await loadArchiveSessions()
  }
}

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
    archiveDetail.value = s
  } catch { /* 列表保留 */ }
}

function closeArchiveDetail() {
  archiveDetail.value = null
  archiveMessages.value = []
}

async function deleteArchiveSession(s: any) {
  if (!confirm('删除这一轮对话（含全部消息）？不可恢复。')) return
  try {
    await api.delete(`/ai-advisor/archive/sessions/${s.session_id}`)
    await loadArchiveSessions()
  } catch { /* ignore */ }
}

// ---- 行动清单 ----

async function toggleActions() {
  showActions.value = !showActions.value
  if (showActions.value) await loadActions()
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
          if (showReasoning.value) showReasoning.value = false   // 正文开始 → 自动折叠 CoT
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
    await loadSnapshot()   // 回答完刷新数据画像
  } catch (e: any) {
    const partial = !!messages.value[idx].content
    askError.value = (e?.message || String(e)) + (partial ? '——已保留部分内容，可重新生成' : '')
  } finally {
    asking.value = false
  }
}

onMounted(() => { loadSnapshot(); loadProfile() })
</script>

<style scoped>
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0.6em 0 0.3em;
}
.md-body :deep(h1) { font-size: 1.05rem; }
.md-body :deep(p) { margin: 0.35em 0; }
.md-body :deep(ul),
.md-body :deep(ol) { margin: 0.35em 0; padding-left: 1.3em; }
.md-body :deep(li) { margin: 0.15em 0; }
.md-body :deep(strong) { font-weight: 600; }
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
  margin: 0.5em 0;
  font-size: 0.85em;
  width: 100%;
}
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid rgba(0,0,0,0.12);
  padding: 0.25em 0.5em;
  text-align: left;
}
.md-body :deep(blockquote) {
  border-left: 3px solid rgba(0,0,0,0.15);
  padding-left: 0.7em;
  margin: 0.5em 0;
  opacity: 0.85;
}
.md-body :deep(hr) { border: none; border-top: 1px solid rgba(0,0,0,0.1); margin: 0.6em 0; }
.md-body :deep(a) { text-decoration: underline; }
</style>
