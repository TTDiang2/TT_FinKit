<template>
  <div class="p-6">
    <h1 class="text-xl font-bold mb-6">设置</h1>

    <div class="flex gap-2 mb-6">
      <button @click="activeSection = 'settings'" :class="['px-4 py-2 text-sm rounded-md transition-colors', activeSection === 'settings' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">设置</button>
      <button @click="activeSection = 'reconciliation'" :class="['px-4 py-2 text-sm rounded-md transition-colors', activeSection === 'reconciliation' ? 'bg-accent-primary text-white' : 'border border-border-default text-text-secondary hover:bg-bg-tertiary']">勾稽</button>
    </div>

    <ReconciliationTab v-if="activeSection === 'reconciliation'" />
    <template v-else>

    <!-- 基本设置 -->
    <div class="bg-white rounded-lg shadow-sm p-6 space-y-5">
      <h2 class="font-semibold">基本设置</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
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
        <div class="flex items-center gap-2">
          <input v-model="form.sidebar_expanded" type="checkbox" id="sidebarExp" class="w-5 h-5" />
          <label for="sidebarExp" class="text-sm font-medium">侧边栏默认展开</label>
        </div>
      </div>
      <button @click="saveSettings" class="px-6 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存设置</button>
    </div>

    <!-- 账户管理 -->
    <div class="bg-white rounded-lg shadow-sm mt-6 overflow-hidden">
      <div class="p-4 border-b border-border-default flex justify-between items-center">
        <h2 class="font-semibold">账户管理</h2>
        <button @click="openAccountModal()" class="px-3 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">+ 添加账户</button>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-4 py-2 font-medium">名称</th>
            <th class="px-4 py-2 font-medium">类型</th>
            <th class="px-4 py-2 font-medium">当前余额</th>
            <th class="px-4 py-2 font-medium">校验口径</th>
            <th class="px-4 py-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="acc in accounts" :key="acc.id" class="border-t border-border-default hover:bg-bg-secondary">
            <td class="px-4 py-2">{{ acc.name }}</td>
            <td class="px-4 py-2">{{ acc.account_type === 'cash' ? '现金' : acc.account_type === 'investment' ? '投资' : acc.account_type === 'custodial' ? '代管' : '现金' }}</td>
            <td class="px-4 py-2 font-medium">{{ sym }}{{ acc.current_balance.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</td>
            <td class="px-4 py-2 text-xs text-text-secondary max-w-xs">{{ formulaText(accountFormula(acc)) }}</td>
            <td class="px-4 py-2">
              <button @click="openAccountModal(acc)" class="text-text-secondary hover:text-accent-primary mr-2">编辑</button>
              <button @click="openBalanceCheck(acc)" class="text-text-secondary hover:text-accent-primary mr-2">校验</button>
              <button @click="deleteAccount(acc.id)" class="text-text-secondary hover:text-expense-color">删除</button>
            </td>
          </tr>
          <tr v-if="!accounts.length"><td colspan="5" class="px-4 py-6 text-center text-text-muted">暂无账户</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 分类管理 -->
    <div class="bg-white rounded-lg shadow-sm mt-6 overflow-hidden">
      <div class="p-4 border-b border-border-default flex justify-between items-center">
        <div class="flex items-center gap-3">
          <h2 class="font-semibold">分类管理</h2>
          <div class="flex gap-2">
            <button v-for="t in ['expense', 'income']" :key="t" @click="catTab = t"
              :class="['px-3 py-1.5 text-sm rounded-md transition-colors', catTab === t ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-border-default']">
              {{ t === 'expense' ? '支出' : '收入' }}
            </button>
          </div>
        </div>
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

    <!-- 标签管理 -->
    <div class="bg-white rounded-lg shadow-sm p-4 mt-6">
      <h2 class="font-semibold mb-3">标签管理</h2>
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

    <!-- AI 助手 -->
    <div class="bg-white rounded-lg shadow-sm mt-6 overflow-hidden">
      <div class="p-4 border-b border-border-default flex justify-between items-center">
        <h2 class="font-semibold">AI 助手</h2>
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
      <div class="p-4 border-t border-border-default">
        <h3 class="text-sm font-semibold mb-2">AI 搜索后端（投资 AI 分析用）</h3>
        <div class="flex gap-4 mb-3">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" v-model="searchForm.ai_search_backend" value="duckduckgo" />
            <span class="text-sm">DuckDuckGo <span class="text-text-muted text-xs">（免费无 key，推荐）</span></span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" v-model="searchForm.ai_search_backend" value="tavily" />
            <span class="text-sm">Tavily <span class="text-text-muted text-xs">（需 key，自带 finance 过滤）</span></span>
          </label>
        </div>
        <div v-if="searchForm.ai_search_backend === 'tavily'" class="mb-3">
          <label class="block text-sm font-medium mb-1">Tavily API Key</label>
          <input v-model="searchForm.ai_search_api_key" type="password" placeholder="tvly-..." class="w-full px-3 py-2 border border-border-default rounded-md" />
        </div>
        <button @click="saveSearchSettings" class="px-4 py-1.5 bg-accent-primary text-white text-sm rounded-md hover:bg-accent-hover">保存搜索设置</button>
      </div>
    </div>

    <!-- iFinD -->
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

    <!-- 修改密码 -->
    <div class="bg-white rounded-lg shadow-sm p-6 mt-6">
      <h2 class="font-semibold mb-4">修改密码</h2>
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">当前密码</label><input v-model="pwd.current" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">新密码</label><input v-model="pwd.newPass" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">确认新密码</label><input v-model="pwd.confirm" type="password" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <button @click="changePwd" class="px-6 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">修改密码</button>
      </div>
    </div>

    <!-- 数据管理 -->
    <div class="bg-white rounded-lg shadow-sm p-6 mt-6">
      <h2 class="font-semibold mb-4">数据管理</h2>
      <div class="flex gap-3">
        <button @click="exportData" class="px-4 py-2 border border-border-default rounded-md hover:bg-bg-tertiary">导出数据</button>
        <button @click="deleteAccountData" class="px-4 py-2 border border-expense-color text-expense-color rounded-md hover:bg-red-50">删除账户</button>
      </div>
    </div>

    <!-- 账户编辑弹窗（含校验口径公式编辑器） -->
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

        <div v-if="accForm.account_type === 'cash'" class="border border-border-default rounded-md p-3 bg-bg-tertiary">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium">校验口径（银行收支换算公式）</label>
            <div class="flex gap-2">
              <button @click="applyPreset('direct')" class="text-xs px-2 py-1 border border-border-default rounded bg-white hover:bg-bg-secondary">工资账户式</button>
              <button @click="applyPreset('composite')" class="text-xs px-2 py-1 border border-border-default rounded bg-white hover:bg-bg-secondary">消费账户式</button>
            </div>
          </div>
          <p class="text-xs text-text-muted mt-1 mb-3">用于「记账 → 校验」的月度汇总核对。不同银行 APP 的收支口径不同，可按需自定义；本设置在设置 tab 的账户管理中随时可改。</p>

          <div class="text-xs font-medium mb-1">银行收入 = 以下分项之和（至少选一项）</div>
          <div class="flex flex-wrap gap-3 mb-3">
            <label v-for="c in INCOME_COMPONENTS" :key="c.value" class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" :value="c.value" v-model="accForm.bankFormula.income" class="w-4 h-4" />
              <span class="text-sm">{{ c.label }}</span>
            </label>
          </div>

          <div class="text-xs font-medium mb-1">银行支出 = 以下分项之和（至少选一项）</div>
          <div class="flex flex-wrap gap-3 mb-3">
            <label v-for="c in EXPENSE_COMPONENTS" :key="c.value" class="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" :value="c.value" v-model="accForm.bankFormula.expense" class="w-4 h-4" />
              <span class="text-sm">{{ c.label }}</span>
            </label>
          </div>
          <div v-if="accForm.bankFormula.expense.length > 1" class="text-xs text-expense-color mb-2">正支出合计与支出净额同时勾选会重复计算退款，请只选一项。</div>
          <div v-if="!accForm.bankFormula.income.length || !accForm.bankFormula.expense.length" class="text-xs text-expense-color mb-2">收入与支出至少各选一项。</div>
          <div class="text-xs text-text-secondary">公式预览：{{ formulaText(accForm.bankFormula) }}</div>
        </div>
      </div>
      <template #footer>
        <button @click="showAccModal = false" class="px-4 py-2 text-text-secondary hover:text-text-primary">取消</button>
        <button @click="saveAccount" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存</button>
      </template>
    </BaseModal>

    <!-- 余额校验弹窗 -->
    <BaseModal v-if="showBalanceCheckModal" :title="`余额校验：${balanceCheckAcc?.name || ''}`" @close="showBalanceCheckModal = false">
      <div v-if="balanceCheckLoading" class="text-sm text-text-muted">加载中…</div>
      <div v-else-if="balanceCheckData" class="space-y-3 text-sm">
        <div>系统期望余额：<span class="font-medium">{{ sym }}{{ balanceCheckData.expected_balance.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</span></div>
        <div class="text-xs text-text-muted">期望余额 = 期初 + 收入 − 支出 + 转入 − 转出（转账计入余额）</div>
        <div>最后流水日期：<span class="text-text-secondary">{{ balanceCheckData.last_recorded_date || '—' }}</span></div>
        <div class="text-xs text-text-muted">{{ balanceCheckData.hint }}</div>
        <div class="text-xs text-text-muted">若与银行 APP 当前余额不符，检查初始余额是否填对、流水是否记全。</div>
      </div>
      <template #footer>
        <button @click="showBalanceCheckModal = false" class="px-4 py-2 text-text-secondary hover:text-text-primary">关闭</button>
      </template>
    </BaseModal>

    <!-- 分类编辑弹窗 -->
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

    <!-- AI 预设弹窗 -->
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
    </template>
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
import ReconciliationTab from '@/pages/investments/ReconciliationTab.vue'
import type { BankFormula } from '@/types'

const activeSection = ref<'settings' | 'reconciliation'>('settings')

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

// ---- 校验口径公式编辑器 ----
const INCOME_COMPONENTS = [
  { value: 'transfer_in', label: '转入转账' },
  { value: 'refund', label: '退款（负支出绝对值）' },
  { value: 'income', label: '收入合计' },
]
const EXPENSE_COMPONENTS = [
  { value: 'expense_positive', label: '正支出合计（毛支出）' },
  { value: 'expense_net', label: '支出净额（正支出−退款）' },
]
const COMPONENT_LABELS: Record<string, string> = {
  transfer_in: '转入转账',
  refund: '退款',
  income: '收入合计',
  expense_positive: '正支出合计',
  expense_net: '支出净额',
}
const PRESETS: Record<string, BankFormula> = {
  direct: { income: ['income'], expense: ['expense_net'] },
  composite: { income: ['transfer_in', 'refund', 'income'], expense: ['expense_positive'] },
}
function formulaText(f: BankFormula | null | undefined): string {
  if (!f) return '—'
  const inc = f.income.map(c => COMPONENT_LABELS[c] || c).join(' + ')
  const exp = f.expense.map(c => COMPONENT_LABELS[c] || c).join(' + ')
  return `银行收入 = ${inc}；银行支出 = ${exp}`
}
function accountFormula(acc: any): BankFormula | null {
  if (acc.bank_formula?.income?.length && acc.bank_formula?.expense?.length) return acc.bank_formula
  return PRESETS[acc.bank_statement_mode || 'direct'] || null
}
function applyPreset(name: 'direct' | 'composite') {
  accForm.value.bankFormula = { income: [...PRESETS[name].income], expense: [...PRESETS[name].expense] }
}
function matchPreset(f: BankFormula): string {
  for (const [name, preset] of Object.entries(PRESETS)) {
    if (f.income.slice().sort().join(',') === preset.income.slice().sort().join(',')
      && f.expense.slice().sort().join(',') === preset.expense.slice().sort().join(',')) return name
  }
  return 'custom'
}

// ---- 账户 ----
const showAccModal = ref(false), editAcc = ref<any>(null)
const accForm = ref<{ name: string; currency: string; initial_balance: number; hidden: boolean; account_type: string; bankFormula: BankFormula }>({
  name: '', currency: 'CNY', initial_balance: 0, hidden: false, account_type: 'cash',
  bankFormula: { income: [...PRESETS.direct.income], expense: [...PRESETS.direct.expense] },
})
function openAccountModal(acc?: any) {
  editAcc.value = acc
  const f = acc ? accountFormula(acc) : PRESETS.direct
  accForm.value = {
    name: acc?.name || '', currency: acc?.currency || 'CNY',
    initial_balance: acc?.initial_balance || 0, hidden: acc?.hidden || false,
    account_type: acc?.account_type || 'cash',
    bankFormula: { income: [...(f?.income || PRESETS.direct.income)], expense: [...(f?.expense || PRESETS.direct.expense)] },
  }
  showAccModal.value = true
}
async function saveAccount() {
  if (!accForm.value.bankFormula.income.length || !accForm.value.bankFormula.expense.length) {
    show('校验口径的收入与支出至少各选一项', 'warning'); return
  }
  try {
    const payload: any = {
      name: accForm.value.name, currency: accForm.value.currency,
      initial_balance: accForm.value.initial_balance, hidden: accForm.value.hidden,
      account_type: accForm.value.account_type,
    }
    if (accForm.value.account_type === 'cash') {
      payload.bank_formula = accForm.value.bankFormula
      payload.bank_statement_mode = matchPreset(accForm.value.bankFormula)
    }
    if (editAcc.value) await accStore.updateAccount(editAcc.value.id, payload)
    else await accStore.createAccount(payload)
    showAccModal.value = false
    show('保存成功', 'success')
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}
async function deleteAccount(id: string) { if (confirm('确定删除？')) { await accStore.deleteAccount(id); show('已删除', 'success') } }

// ---- 余额校验 ----
const showBalanceCheckModal = ref(false)
const balanceCheckAcc = ref<any>(null)
const balanceCheckData = ref<any>(null)
const balanceCheckLoading = ref(false)
async function openBalanceCheck(acc: any) {
  balanceCheckAcc.value = acc
  balanceCheckData.value = null
  showBalanceCheckModal.value = true
  balanceCheckLoading.value = true
  try {
    const res = await api.get('/reconciliation/expected-balance', { params: { account_id: acc.id } })
    balanceCheckData.value = res.data
  } catch (e: any) { show(e.response?.data?.detail || '加载失败', 'error') }
  finally { balanceCheckLoading.value = false }
}

// ---- 分类 ----
const showCatModal = ref(false), editCat = ref<any>(null)
const catForm = ref<{ name: string; type: 'income' | 'expense'; color: string; is_necessary: boolean; pl_section: string; cf_section: string }>({ name: '', type: 'expense', color: '#6B6B6B', is_necessary: false, pl_section: '', cf_section: '' })
const presetColors = ['#4CAF50','#F44336','#2196F3','#FF9800','#9C27B0','#00BCD4','#795548','#607D8B','#E91E63','#3F51B5','#8BC34A','#FF5722','#673AB7','#009688','#CDDC39','#FFC107','#795548','#9E9E9E','#212121']
function openCatModal(cat?: any) {
  editCat.value = cat
  catForm.value = cat ? {
    name: cat.name, type: cat.type, color: cat.color, is_necessary: cat.is_necessary || false,
    pl_section: cat.pl_section || '', cf_section: cat.cf_section || ''
  } : { name: '', type: catTab.value, color: '#6B6B6B', is_necessary: false, pl_section: '', cf_section: '' }
  showCatModal.value = true
}
async function updateCatPlSection(id: string, pl_section: string) { await catStore.updateCategory(id, { pl_section }); show('已更新', 'success') }
async function updateCatCfSection(id: string, cf_section: string) { await catStore.updateCategory(id, { cf_section }); show('已更新', 'success') }
async function saveCategory() {
  try { if (editCat.value) await catStore.updateCategory(editCat.value.id, catForm.value); else await catStore.createCategory(catForm.value); showCatModal.value = false; show('保存成功', 'success') }
  catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}
async function deleteCategory(id: string) { if (confirm('确定删除？')) { await catStore.deleteCategory(id); show('已删除', 'success') } }

// ---- 标签 ----
const newTagName = ref(''), newTagColor = ref('#9B9E9E')
async function addTag() {
  if (!newTagName.value) return
  await tagStore.createTag({ name: newTagName.value, color: newTagColor.value })
  newTagName.value = ''
  show('标签已添加', 'success')
}
async function deleteTag(id: string) { await tagStore.deleteTag(id) }

// ---- 设置 ----
const form = ref({ language: 'zh', currency_symbol: '¥', date_format: 'YYYY-MM-DD', timezone: 'Asia/Shanghai', sidebar_expanded: true, ifind_username: '', ifind_password: '' })
const searchForm = ref({ ai_search_backend: 'duckduckgo', ai_search_api_key: '' })
const pwd = ref({ current: '', newPass: '', confirm: '' })

const hasIfindPwd = ref(false)
const ifindTesting = ref(false)
const ifindTestResult = ref<{ ok: boolean; message?: string; error?: string } | null>(null)

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

async function saveSearchSettings() {
  try {
    await settingsStore.updateSettings(searchForm.value as any)
    show('搜索设置已保存', 'success')
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

function deleteAccountData() {
  const c = prompt('输入 DELETE 确认删除账户（不可恢复）：')
  if (c === 'DELETE') { show('请联系管理员删除账户', 'warning') }
}

// ---- AI 预设 ----
const showAiPresetModal = ref(false), editAiPreset = ref<any>(null)
const aiPresetForm = ref({ name: '', api_url: '', api_key: '', model_name: '', system_prompt: '', is_default: false })
function openAiPresetModal(preset?: any) {
  editAiPreset.value = preset
  aiPresetForm.value = preset ? {
    name: preset.name, api_url: preset.api_url, api_key: preset.api_key,
    model_name: preset.model_name, system_prompt: preset.system_prompt, is_default: preset.is_default
  } : { name: '', api_url: '', api_key: '', model_name: '', system_prompt: '', is_default: false }
  showAiPresetModal.value = true
}
async function saveAiPreset() {
  try {
    if (editAiPreset.value) await aiPresetsStore.updatePreset(editAiPreset.value.id, aiPresetForm.value)
    else await aiPresetsStore.createPreset(aiPresetForm.value)
    showAiPresetModal.value = false
    show('保存成功', 'success')
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}
async function deleteAiPreset(id: string) {
  if (confirm('确定删除此预设？')) {
    try { await aiPresetsStore.deletePreset(id); show('已删除', 'success') }
    catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
  }
}
async function setDefaultPreset(id: string) {
  try { await aiPresetsStore.setDefault(id); show('已设为默认', 'success') }
  catch (e: any) { show(e.response?.data?.detail || '设置失败', 'error') }
}

onMounted(async () => {
  form.value = { ...form.value, ...settingsStore.settings, ifind_password: '' }
  hasIfindPwd.value = !!settingsStore.settings.has_ifind_password
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
