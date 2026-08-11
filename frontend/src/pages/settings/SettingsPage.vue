<template>
  <div class="p-6 max-w-2xl">
    <h1 class="text-xl font-bold mb-6">设置</h1>
    <div class="bg-white rounded-lg shadow-sm p-6 space-y-5">
      <div><label class="block text-sm font-medium mb-1">语言</label>
        <select v-model="form.language" class="w-full px-3 py-2 border border-border-default rounded-md">
          <option value="zh">中文</option><option value="en">English</option>
        </select>
      </div>
      <div><label class="block text-sm font-medium mb-1">货币符号</label>
        <select v-model="form.currency_symbol" class="w-full px-3 py-2 border border-border-default rounded-md">
          <option value="¥">¥ (CNY)</option><option value="$">$ (USD)</option><option value="€">€ (EUR)</option><option value="£">£ (GBP)</option>
        </select>
      </div>
      <div><label class="block text-sm font-medium mb-1">日期格式</label>
        <select v-model="form.date_format" class="w-full px-3 py-2 border border-border-default rounded-md">
          <option value="YYYY-MM-DD">YYYY-MM-DD</option><option value="DD/MM/YYYY">DD/MM/YYYY</option><option value="MM/DD/YYYY">MM/DD/YYYY</option>
        </select>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-sm font-medium">侧边栏默认展开</span>
        <input v-model="form.sidebar_expanded" type="checkbox" class="w-5 h-5" />
      </div>
      <button @click="saveSettings" class="px-6 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存设置</button>
    </div>

    <div class="bg-white rounded-lg shadow-sm p-6 mt-6">
      <h2 class="font-semibold mb-4">修改密码</h2>
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">当前密码</label><input v-model="pwd.current" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">新密码</label><input v-model="pwd.newPass" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">确认新密码</label><input v-model="pwd.confirm" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <button @click="changePwd" class="px-6 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">修改密码</button>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm p-6 mt-6">
      <h2 class="font-semibold mb-1">同花顺 iFinD 行情数据</h2>
      <p class="text-xs text-text-muted mb-4">配置后，「投资」页可自动获取 A股/ETF/港股/基金的真实净值与历史曲线，并在净值图上标注买卖点。未配置或连接失败时自动降级到免费行情源。</p>
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">iFinD 账号</label>
          <input v-model="form.ifind_username" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="同花顺量化接口账号 ID" autocomplete="off" />
        </div>
        <div><label class="block text-sm mb-1">密码</label>
          <input v-model="form.ifind_password" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" :placeholder="hasIfindPwd ? '已配置（留空则保持不变）' : '请输入密码'" autocomplete="new-password" />
        </div>
        <div class="flex items-center gap-3 flex-wrap">
          <button @click="testIfind" :disabled="ifindTesting" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary disabled:opacity-50">
            {{ ifindTesting ? '测试中…' : '测试连接' }}
          </button>
          <button @click="saveSettings" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">保存凭证</button>
          <span v-if="ifindTestResult" :class="['text-sm', ifindTestResult.ok ? 'text-income-color' : 'text-expense-color']">
            {{ ifindTestResult.ok ? '✓ ' + (ifindTestResult.message || '连接成功') : '✗ ' + ifindTestResult.error }}
          </span>
          <span v-else-if="hasIfindPwd" class="text-xs text-text-muted">当前：已配置凭证</span>
        </div>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm p-6 mt-6">
      <h2 class="font-semibold mb-4">数据管理</h2>
      <div class="flex gap-3">
        <button @click="exportData" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">导出数据</button>
        <button @click="deleteAccount" class="px-4 py-2 border border-expense-color text-expense-color rounded-md hover:bg-red-50">删除账户</button>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const settingsStore = useSettingsStore()
const authStore = useAuthStore()
const api = useApi()
const { show } = useToast()

const form = ref({ language: 'zh', currency_symbol: '¥', date_format: 'YYYY-MM-DD', timezone: 'Asia/Shanghai', sidebar_expanded: true, ifind_username: '', ifind_password: '' })
const pwd = ref({ current: '', newPass: '', confirm: '' })

// iFinD connectivity test state
const hasIfindPwd = ref(false)
const ifindTesting = ref(false)
const ifindTestResult = ref<{ ok: boolean; message?: string; error?: string } | null>(null)

onMounted(() => {
  form.value = { ...form.value, ...settingsStore.settings, ifind_password: '' }
  hasIfindPwd.value = !!settingsStore.settings.has_ifind_password
})

async function saveSettings() {
  try {
    await settingsStore.updateSettings({
      language: form.value.language, currency_symbol: form.value.currency_symbol,
      date_format: form.value.date_format, timezone: form.value.timezone, sidebar_expanded: form.value.sidebar_expanded,
      ifind_username: form.value.ifind_username, ifind_password: form.value.ifind_password,
    })
    form.value.ifind_password = ''
    await settingsStore.fetchSettings()
    hasIfindPwd.value = !!settingsStore.settings.has_ifind_password
    show('设置已保存', 'success')
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function testIfind() {
  if (!form.value.ifind_username || !form.value.ifind_password) {
    show('请填写账号和密码后再测试', 'warning'); return
  }
  ifindTesting.value = true
  ifindTestResult.value = null
  try {
    const res = await api.post('/settings/ifind/test', { username: form.value.ifind_username, password: form.value.ifind_password })
    ifindTestResult.value = res.data
  } catch (e: any) {
    ifindTestResult.value = { ok: false, error: e.response?.data?.detail || e.message || '请求失败' }
  } finally { ifindTesting.value = false }
}

async function changePwd() {
  if (pwd.value.newPass !== pwd.value.confirm) { show('两次密码不一致', 'error'); return }
  try { await api.put('/settings/password', null, { params: { current_password: pwd.value.current, new_password: pwd.value.newPass } }); show('密码已修改', 'success'); pwd.value = { current: '', newPass: '', confirm: '' } }
  catch (e: any) { show(e.response?.data?.detail || '修改失败', 'error') }
}

async function exportData() {
  try {
    const [acc, cat, tag, txn] = await Promise.all([api.get('/accounts'), api.get('/categories'), api.get('/tags'), api.get('/transactions', { params: { page_size: 200 } })])
    const data = JSON.stringify({ accounts: acc.data, categories: cat.data, tags: tag.data, transactions: txn.data }, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'finkit-export.json'; a.click()
    URL.revokeObjectURL(url)
    show('数据已导出', 'success')
  } catch (e: any) { show('导出失败', 'error') }
}

function deleteAccount() {
  const c = prompt('输入 DELETE 确认删除账户（不可恢复）：')
  if (c === 'DELETE') { show('请联系管理员删除账户', 'warning') }
}
</script>
