<template>
  <div class="p-6">
    <h1 class="text-xl font-bold mb-6">管理</h1>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">账户</h2>
      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <div class="p-4 border-b border-border-default flex justify-between items-center">
          <span class="text-sm text-text-secondary">共 {{ accounts.length }} 个账户</span>
          <button @click="openAccountModal()" class="px-3 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">+ 添加账户</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr>
              <th class="px-4 py-2 font-medium">名称</th>
              <th class="px-4 py-2 font-medium">类型</th>
              <th class="px-4 py-2 font-medium">货币</th>
              <th class="px-4 py-2 font-medium">初始余额</th>
              <th class="px-4 py-2 font-medium">当前余额</th>
              <th class="px-4 py-2 font-medium">隐藏</th>
              <th class="px-4 py-2 font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="acc in accounts" :key="acc.id" class="border-t border-border-default hover:bg-bg-secondary">
              <td class="px-4 py-2">{{ acc.name }}</td>
              <td class="px-4 py-2">{{ acc.account_type === 'cash' ? '现金' : acc.account_type === 'investment' ? '投资' : acc.account_type === 'custodial' ? '代管' : '现金' }}</td>
              <td class="px-4 py-2">{{ acc.currency }}</td>
              <td class="px-4 py-2">{{ sym }}{{ acc.initial_balance.toLocaleString('zh-CN') }}</td>
              <td class="px-4 py-2 font-medium">{{ sym }}{{ acc.current_balance.toLocaleString('zh-CN') }}</td>
              <td class="px-4 py-2"><span :class="acc.hidden ? 'text-expense-color' : 'text-income-color'">{{ acc.hidden ? '是' : '否' }}</span></td>
              <td class="px-4 py-2">
                <button @click="openAccountModal(acc)" class="text-text-secondary hover:text-accent-primary mr-2">编辑</button>
                <button @click="deleteAccount(acc.id)" class="text-text-secondary hover:text-expense-color">删除</button>
              </td>
            </tr>
            <tr v-if="!accounts.length"><td colspan="7" class="px-4 py-6 text-center text-text-muted">暂无账户</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">分类</h2>
      <div class="flex gap-2 mb-3">
        <button v-for="t in ['expense', 'income']" :key="t" @click="catTab = t"
          :class="['px-4 py-1.5 text-sm rounded-md transition-colors', catTab === t ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-border-default']">
          {{ t === 'expense' ? '支出' : '收入' }}
        </button>
      </div>
      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <div class="p-4 border-b border-border-default flex justify-between items-center">
          <span class="text-sm text-text-secondary">共 {{ filteredCats.length }} 个分类</span>
          <button @click="openCatModal()" class="px-3 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">+ 添加分类</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr><th class="px-4 py-2 font-medium">颜色</th><th class="px-4 py-2 font-medium">名称</th><th class="px-4 py-2 font-medium">必要</th><th class="px-4 py-2 font-medium">利润表分类</th><th class="px-4 py-2 font-medium">现金流分类</th><th class="px-4 py-2 font-medium">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="cat in filteredCats" :key="cat.id" class="border-t border-border-default">
              <td class="px-4 py-2"><div class="w-5 h-5 rounded" :style="{ backgroundColor: cat.color }"></div></td>
              <td class="px-4 py-2">{{ cat.name }}</td>
              <td class="px-4 py-2">{{ cat.is_necessary ? '是' : '否' }}</td>
              <td class="px-4 py-2">
                <select :value="cat.pl_section" @change="updateCatPlSection(cat.id, ($event.target as HTMLSelectElement).value)" class="text-xs px-2 py-1 border border-border-default rounded">
                  <option value="">默认</option>
                  <option v-if="cat.type === 'expense'" value="main_cost">主营业务成本</option>
                  <option v-if="cat.type === 'expense'" value="other_cost">其他成本</option>
                  <option v-if="cat.type === 'expense'" value="exclude_expense">不计入</option>
                  <option v-if="cat.type === 'income'" value="main_income">主营业务收入</option>
                  <option v-if="cat.type === 'income'" value="other_income">其他收入</option>
                  <option v-if="cat.type === 'income'" value="exclude_income">不计入</option>
                </select>
              </td>
              <td class="px-4 py-2">
                <select :value="cat.cf_section" @change="updateCatCfSection(cat.id, ($event.target as HTMLSelectElement).value)" class="text-xs px-2 py-1 border border-border-default rounded">
                  <option value="">默认</option>
                  <option value="operating">经营活动</option>
                  <option value="investing">投资活动</option>
                  <option value="financing">筹资活动</option>
                </select>
              </td>
              <td class="px-4 py-2">
                <button @click="openCatModal(cat)" class="text-text-secondary hover:text-accent-primary mr-2">编辑</button>
                <button @click="deleteCategory(cat.id)" class="text-text-secondary hover:text-expense-color">删除</button>
              </td>
            </tr>
            <tr v-if="!filteredCats.length"><td colspan="6" class="px-4 py-6 text-center text-text-muted">暂无分类</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">标签</h2>
      <div class="bg-white rounded-lg shadow-sm p-4">
        <div class="flex flex-wrap gap-2 mb-3">
          <span v-for="tag in tags" :key="tag.id" class="inline-flex items-center gap-1 px-2 py-1 rounded text-sm" :style="{ backgroundColor: tag.color + '20', color: tag.color }">
            {{ tag.name }}
            <button @click="deleteTag(tag.id)" class="hover:opacity-70">×</button>
          </span>
        </div>
        <div class="flex gap-2">
          <input v-model="newTagName" placeholder="标签名" class="flex-1 px-3 py-1.5 border border-border-default rounded-md text-sm" />
          <input v-model="newTagColor" type="color" class="w-9 h-9 rounded cursor-pointer" />
          <button @click="addTag" class="px-3 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">添加</button>
        </div>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">设置</h2>
      <div class="bg-white rounded-lg shadow-sm p-6 space-y-5">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium mb-1">语言</label>
            <select v-model="settingsForm.language" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="zh">中文</option><option value="en">English</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">货币符号</label>
            <select v-model="settingsForm.currency_symbol" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="¥">¥ (CNY)</option><option value="$">$ (USD)</option><option value="€">€ (EUR)</option><option value="£">£ (GBP)</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium mb-1">日期格式</label>
            <select v-model="settingsForm.date_format" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="YYYY-MM-DD">YYYY-MM-DD</option><option value="DD/MM/YYYY">DD/MM/YYYY</option><option value="MM/DD/YYYY">MM/DD/YYYY</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <input v-model="settingsForm.sidebar_expanded" type="checkbox" id="sidebarExp" class="w-5 h-5" />
            <label for="sidebarExp" class="text-sm font-medium">侧边栏默认展开</label>
          </div>
        </div>
        <button @click="saveSettings" class="px-6 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存设置</button>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">修改密码</h2>
      <div class="bg-white rounded-lg shadow-sm p-6 space-y-3">
        <div><label class="block text-sm mb-1">当前密码</label><input v-model="pwd.current" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">新密码</label><input v-model="pwd.newPass" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">确认新密码</label><input v-model="pwd.confirm" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <button @click="changePwd" class="px-6 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">修改密码</button>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">AI 助手设置</h2>
      <div class="bg-white rounded-lg shadow-sm overflow-hidden">
        <div class="p-4 border-b border-border-default flex justify-between items-center">
          <span class="text-sm text-text-secondary">共 {{ aiPresetsStore.presets.length }} 个预设</span>
          <button @click="openAiPresetModal()" class="px-3 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">+ 添加预设</button>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr><th class="px-4 py-2 font-medium">名称</th><th class="px-4 py-2 font-medium">模型</th><th class="px-4 py-2 font-medium">API URL</th><th class="px-4 py-2 font-medium">默认</th><th class="px-4 py-2 font-medium">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="preset in aiPresetsStore.presets" :key="preset.id" class="border-t border-border-default">
              <td class="px-4 py-2">{{ preset.name }}</td>
              <td class="px-4 py-2">{{ preset.model_name }}</td>
              <td class="px-4 py-2 text-text-muted truncate max-w-xs">{{ preset.api_url }}</td>
              <td class="px-4 py-2">
                <span v-if="preset.is_default" class="text-income-color">是</span>
                <button v-else @click="setDefaultPreset(preset.id)" class="text-text-secondary hover:text-accent-primary text-xs">设为默认</button>
              </td>
              <td class="px-4 py-2">
                <button @click="openAiPresetModal(preset)" class="text-text-secondary hover:text-accent-primary mr-2">编辑</button>
                <button @click="deleteAiPreset(preset.id)" class="text-text-secondary hover:text-expense-color">删除</button>
              </td>
            </tr>
            <tr v-if="!aiPresetsStore.presets.length"><td colspan="5" class="px-4 py-6 text-center text-text-muted">暂无预设</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">AI 搜索后端</h2>
      <div class="bg-white rounded-lg shadow-sm p-6 space-y-4">
        <p class="text-sm text-text-secondary">
          用于投资 AI 分析的实时新闻搜索。在"投资 → AI 分析"中会自动使用当前选择的后端。
        </p>
        <div>
          <label class="block text-sm font-medium mb-2">搜索后端</label>
          <div class="flex gap-4">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" v-model="searchForm.ai_search_backend" value="duckduckgo" />
              <span class="text-sm">DuckDuckGo <span class="text-text-muted text-xs">（免费无 key，推荐）</span></span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" v-model="searchForm.ai_search_backend" value="tavily" />
              <span class="text-sm">Tavily <span class="text-text-muted text-xs">（需 key，自带 finance 过滤）</span></span>
            </label>
          </div>
        </div>
        <div v-if="searchForm.ai_search_backend === 'tavily'">
          <label class="block text-sm font-medium mb-1">Tavily API Key</label>
          <input v-model="searchForm.ai_search_api_key" type="password" placeholder="tvly-..." class="w-full px-3 py-2 border border-border-default rounded-md" />
          <div class="text-xs text-text-muted mt-1">在 <a href="https://tavily.com" target="_blank" rel="noopener" class="text-accent-primary hover:underline">tavily.com</a> 注册可免费获得 1000 credits/月。</div>
        </div>
        <button @click="saveSearchSettings" class="px-6 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存搜索设置</button>
      </div>
    </div>

    <div class="mb-6">
      <h2 class="text-lg font-semibold mb-3">数据管理</h2>
      <div class="bg-white rounded-lg shadow-sm p-6 flex gap-3">
        <button @click="exportData" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">导出数据</button>
        <button @click="deleteAccountData" class="px-4 py-2 border border-expense-color text-expense-color rounded-md hover:bg-red-50">删除账户</button>
      </div>
    </div>

    <BaseModal v-if="showAccModal" :title="editAcc ? '编辑账户' : '添加账户'" @close="showAccModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">名称</label><input v-model="accForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div>
          <label class="block text-sm mb-1">账户类型</label>
          <select v-model="accForm.account_type" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="cash">现金账户</option>
            <option value="investment">投资账户</option>
            <option value="custodial">代管账户</option>
          </select>
        </div>
        <div><label class="block text-sm mb-1">货币</label><input v-model="accForm.currency" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">初始余额</label><input v-model.number="accForm.initial_balance" type="number" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div class="flex items-center gap-2"><input v-model="accForm.hidden" type="checkbox" id="accHidden" /><label for="accHidden" class="text-sm">隐藏</label></div>
      </div>
      <template #footer>
        <button @click="showAccModal = false" class="px-4 py-2 text-text-secondary hover:text-text-primary">取消</button>
        <button @click="saveAccount" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存</button>
      </template>
    </BaseModal>

    <BaseModal v-if="showCatModal" :title="editCat ? '编辑分类' : '添加分类'" @close="showCatModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">名称</label><input v-model="catForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">类型</label>
          <select v-model="catForm.type" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="expense">支出</option><option value="income">收入</option>
          </select>
        </div>
        <div><label class="block text-sm mb-1">颜色</label>
          <div class="flex flex-wrap gap-2 mb-2">
            <div v-for="c in presetColors" :key="c" @click="catForm.color = c"
              :class="['w-7 h-7 rounded cursor-pointer border-2', catForm.color === c ? 'border-accent-primary' : 'border-transparent']"
              :style="{ backgroundColor: c }"></div>
          </div>
          <div class="flex items-center gap-2">
            <input v-model="catForm.color" type="text" placeholder="#RRGGBB" class="flex-1 px-3 py-2 border border-border-default rounded-md text-sm" />
            <input v-model="catForm.color" type="color" class="w-9 h-9 rounded cursor-pointer" />
          </div>
        </div>
        <div class="flex items-center gap-2" v-if="catForm.type === 'expense'">
          <input type="checkbox" v-model="catForm.is_necessary" id="cat-necessary" />
          <label for="cat-necessary" class="text-sm">必要支出</label>
        </div>
        <div><label class="block text-sm mb-1">利润表分类</label>
          <select v-model="catForm.pl_section" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">默认</option>
            <option v-if="catForm.type === 'expense'" value="main_cost">主营业务成本</option>
            <option v-if="catForm.type === 'expense'" value="other_cost">其他成本</option>
            <option v-if="catForm.type === 'expense'" value="exclude_expense">不计入</option>
            <option v-if="catForm.type === 'income'" value="main_income">主营业务收入</option>
            <option v-if="catForm.type === 'income'" value="other_income">其他收入</option>
            <option v-if="catForm.type === 'income'" value="exclude_income">不计入</option>
          </select>
        </div>
        <div><label class="block text-sm mb-1">现金流量表分类</label>
          <select v-model="catForm.cf_section" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">默认</option>
            <option value="operating">经营活动</option>
            <option value="investing">投资活动</option>
            <option value="financing">筹资活动</option>
          </select>
        </div>
      </div>
      <template #footer>
        <button @click="showCatModal = false" class="px-4 py-2 text-text-secondary hover:text-text-primary">取消</button>
        <button @click="saveCategory" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存</button>
      </template>
    </BaseModal>

    <BaseModal v-if="showAiPresetModal" :title="editAiPreset ? '编辑预设' : '添加预设'" @close="showAiPresetModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">名称</label><input v-model="aiPresetForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">API URL</label><input v-model="aiPresetForm.api_url" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="https://api.openai.com/v1" /></div>
        <div><label class="block text-sm mb-1">API Key</label><input v-model="aiPresetForm.api_key" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="sk-..." /></div>
        <div><label class="block text-sm mb-1">模型</label><input v-model="aiPresetForm.model_name" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="gpt-4o" /></div>
        <div><label class="block text-sm mb-1">System Prompt</label><textarea v-model="aiPresetForm.system_prompt" rows="4" class="w-full px-3 py-2 border border-border-default rounded-md text-sm" placeholder="你是一个专业的财务助手..."></textarea></div>
        <div class="flex items-center gap-2"><input type="checkbox" v-model="aiPresetForm.is_default" id="aiPresetDefault" /><label for="aiPresetDefault" class="text-sm">设为默认</label></div>
      </div>
      <template #footer>
        <button @click="showAiPresetModal = false" class="px-4 py-2 text-text-secondary hover:text-text-primary">取消</button>
        <button @click="saveAiPreset" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存</button>
      </template>
    </BaseModal>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAccountsStore } from '@/stores/accounts'
import { useCategoriesStore } from '@/stores/categories'
import { useTagsStore } from '@/stores/tags'
import { useSettingsStore } from '@/stores/settings'
import { useAiPresetsStore } from '@/stores/aiPresets'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'

const accStore = useAccountsStore()
const catStore = useCategoriesStore()
const tagStore = useTagsStore()
const settingsStore = useSettingsStore()
const aiPresetsStore = useAiPresetsStore()
const api = useApi()
const { show } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)
const accounts = computed(() => accStore.accounts)
const tags = computed(() => tagStore.tags)
const catTab = ref('expense')
const filteredCats = computed(() => catStore.categories.filter(c => c.type === catTab.value))

const presetColors = ['#4CAF50','#F44336','#2196F3','#FF9800','#9C27B0','#00BCD4','#795548','#607D8B','#E91E63','#3F51B5','#8BC34A','#FF5722','#673AB7','#009688','#CDDC39','#FFC107','#6735B4','#E91E63','#795548','#9E9E9E','#212121']

const showAccModal = ref(false), editAcc = ref<any>(null)
const accForm = ref({ name: '', currency: 'CNY', initial_balance: 0, hidden: false, account_type: 'cash' })
const showCatModal = ref(false), editCat = ref<any>(null)
const catForm = ref<{ name: string; type: 'income' | 'expense'; color: string; is_necessary: boolean; pl_section: string; cf_section: string }>({ name: '', type: 'expense', color: '#6B6B6B', is_necessary: false, pl_section: '', cf_section: '' })
const newTagName = ref(''), newTagColor = ref('#9B9E9E')

const settingsForm = ref({ language: 'zh', currency_symbol: '¥', date_format: 'YYYY-MM-DD', timezone: 'Asia/Shanghai', sidebar_expanded: true })
const searchForm = ref({ ai_search_backend: 'duckduckgo', ai_search_api_key: '' })
const pwd = ref({ current: '', newPass: '', confirm: '' })

const showAiPresetModal = ref(false), editAiPreset = ref<any>(null)
const aiPresetForm = ref({ name: '', api_url: '', api_key: '', model_name: '', system_prompt: '', is_default: false })

function openAccountModal(acc?: any) { editAcc.value = acc; accForm.value = acc ? { name: acc.name, currency: acc.currency, initial_balance: acc.initial_balance, hidden: acc.hidden, account_type: acc.account_type || 'cash' } : { name: '', currency: 'CNY', initial_balance: 0, hidden: false, account_type: 'cash' }; showAccModal.value = true }
function openCatModal(cat?: any) { 
  editCat.value = cat; 
  catForm.value = cat ? { 
    name: cat.name, 
    type: cat.type, 
    color: cat.color, 
    is_necessary: cat.is_necessary || false,
    pl_section: cat.pl_section || '',
    cf_section: cat.cf_section || ''
  } : { name: '', type: catTab.value, color: '#6B6B6B', is_necessary: false, pl_section: '', cf_section: '' }; 
  showCatModal.value = true 
}
async function updateCatPlSection(id: string, pl_section: string) { await catStore.updateCategory(id, { pl_section }); show('已更新', 'success') }
async function updateCatCfSection(id: string, cf_section: string) { await catStore.updateCategory(id, { cf_section }); show('已更新', 'success') }

async function saveAccount() {
  try { if (editAcc.value) await accStore.updateAccount(editAcc.value.id, accForm.value); else await accStore.createAccount(accForm.value); showAccModal.value = false; show('保存成功', 'success') }
  catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}
async function deleteAccount(id: string) { if (confirm('确定删除？')) { await accStore.deleteAccount(id); show('已删除', 'success') } }
async function saveCategory() {
  try { if (editCat.value) await catStore.updateCategory(editCat.value.id, catForm.value); else await catStore.createCategory(catForm.value); showCatModal.value = false; show('保存成功', 'success') }
  catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}
async function deleteCategory(id: string) { if (confirm('确定删除？')) { await catStore.deleteCategory(id); show('已删除', 'success') } }
async function addTag() {
  if (!newTagName.value) return
  await tagStore.createTag({ name: newTagName.value, color: newTagColor.value })
  newTagName.value = ''
  show('标签已添加', 'success')
}
async function deleteTag(id: string) { await tagStore.deleteTag(id) }

async function saveSettings() {
  try { await settingsStore.updateSettings(settingsForm.value); show('设置已保存', 'success') }
  catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function saveSearchSettings() {
  try {
    await settingsStore.updateSettings(searchForm.value as any)
    show('搜索设置已保存', 'success')
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
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

function deleteAccountData() {
  const c = prompt('输入 DELETE 确认删除账户（不可恢复）：')
  if (c === 'DELETE') { show('请联系管理员删除账户', 'warning') }
}

function openAiPresetModal(preset?: any) {
  editAiPreset.value = preset
  aiPresetForm.value = preset ? {
    name: preset.name,
    api_url: preset.api_url,
    api_key: preset.api_key,
    model_name: preset.model_name,
    system_prompt: preset.system_prompt,
    is_default: preset.is_default
  } : { name: '', api_url: '', api_key: '', model_name: '', system_prompt: '', is_default: false }
  showAiPresetModal.value = true
}

async function saveAiPreset() {
  try {
    if (editAiPreset.value) {
      await aiPresetsStore.updatePreset(editAiPreset.value.id, aiPresetForm.value)
    } else {
      await aiPresetsStore.createPreset(aiPresetForm.value)
    }
    showAiPresetModal.value = false
    show('保存成功', 'success')
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function deleteAiPreset(id: string) {
  if (confirm('确定删除此预设？')) {
    try {
      await aiPresetsStore.deletePreset(id)
      show('已删除', 'success')
    } catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
  }
}

async function setDefaultPreset(id: string) {
  try {
    await aiPresetsStore.setDefault(id)
    show('已设为默认', 'success')
  } catch (e: any) { show(e.response?.data?.detail || '设置失败', 'error') }
}

onMounted(async () => {
  settingsForm.value = { ...settingsStore.settings }
  searchForm.value = {
    ai_search_backend: (settingsStore.settings.ai_search_backend as string) || 'duckduckgo',
    ai_search_api_key: (settingsStore.settings.ai_search_api_key as string) || ''
  }
  await Promise.all([accStore.fetchAccounts(), catStore.fetchCategories(), tagStore.fetchTags(), aiPresetsStore.fetchPresets()])
  if (!catStore.categories.length) {
    const defaults: { type: 'income' | 'expense'; name: string; color: string; is_necessary?: boolean }[] = [
      { type: 'expense', name: '餐饮', color: '#F44336', is_necessary: true }, { type: 'expense', name: '交通', color: '#2196F3', is_necessary: true },
      { type: 'expense', name: '住房', color: '#9C27B0', is_necessary: true }, { type: 'expense', name: '娱乐', color: '#FF9800', is_necessary: false },
      { type: 'expense', name: '购物', color: '#E91E63', is_necessary: false }, { type: 'expense', name: '医疗', color: '#4CAF50', is_necessary: true },
      { type: 'expense', name: '教育', color: '#00BCD4', is_necessary: false }, { type: 'expense', name: '其他', color: '#607D8B', is_necessary: false },
      { type: 'income', name: '工资', color: '#4CAF50' }, { type: 'income', name: '奖金', color: '#FF9800' },
      { type: 'income', name: '投资', color: '#2196F3' }, { type: 'income', name: '其他', color: '#9C27B0' },
    ]
    for (const d of defaults) await catStore.createCategory(d)
  }
})
</script>