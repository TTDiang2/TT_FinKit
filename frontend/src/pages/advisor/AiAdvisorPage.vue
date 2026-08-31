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
              :class="['max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
                       m.role === 'user' ? 'ml-auto bg-accent-primary/10' : 'bg-bg-tertiary']">
              <div v-if="m.role === 'assistant'" class="text-xs text-text-muted mb-1">财富审计师</div>
              <div class="whitespace-pre-wrap">{{ m.content }}</div>
            </div>
            <div v-if="asking" class="text-sm text-text-muted">审计师正在核对数据…</div>
            <div v-if="askError" class="text-xs text-expense-color">{{ askError }}</div>
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
import { useApi } from '@/composables/useApi'

const api = useApi()
const messages = ref<{ role: 'user' | 'assistant'; content: string }[]>([])
const question = ref('')
const asking = ref(false)
const askError = ref('')
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

async function ask() {
  const q = question.value.trim()
  if (!q || asking.value) return
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  asking.value = true
  askError.value = ''
  await nextTick()
  chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight })
  try {
    const { data } = await api.post('/ai-advisor/ask', { question: q })
    messages.value.push({ role: 'assistant', content: data.answer })
  } catch (e: any) {
    askError.value = e?.response?.data?.detail || e?.message || '请求失败'
  } finally {
    asking.value = false
    await nextTick()
    chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight })
  }
}

onMounted(() => { loadSnapshot(); loadProfile() })
</script>
