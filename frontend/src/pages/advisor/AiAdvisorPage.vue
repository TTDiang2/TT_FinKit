<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-lg font-semibold">AI 财富审计师</h2>
        <p class="text-xs text-text-muted mt-0.5">
          严厉 · 理性 · 冷静 · 只引用真实数据 · 不提供情绪价值
        </p>
      </div>
      <div class="flex gap-2">
        <button @click="showData = !showData" class="btn-secondary text-xs">
          {{ showData ? '隐藏数据画像' : '查看数据画像' }}
        </button>
        <button @click="showProfile = !showProfile" class="btn-secondary text-xs">
          {{ showProfile ? '隐藏画像编辑' : '编辑个人画像' }}
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

function resetProfile() {
  profileMd.value = DEFAULT_PROFILE_LOCAL
  profileMsg.value = '已恢复默认模板（记得点保存）'
  profileOk.value = true
}

const DEFAULT_PROFILE_LOCAL = `# 个人画像

## 收入
- 工资为主，月入约 1.0万~1.7万（有奖金/补贴波动）
- 家庭支持的可能性存在（尤其购房时），但不应作为日常现金流依赖

## 投资纪律
- 每月固定投入约 1 万元到投资账户（定投为主）
- 投资品种：基金定投（指数增强、行业/主题基金、黄金、债券），接受中高波动

## 目标与约束
- 应急储备：至少覆盖 6 个月支出（硬约束）
- 中期目标：未来 5~10 年内购房；可能获得父母家庭支持，但要求自己独立供得起月供

## 性格与偏好
- 能接受严厉、直接的批评；讨厌和稀泠式的安慰
- 希望得到可执行的数字级建议（金额/比例/期限）`

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
