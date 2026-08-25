<template>
  <div>
    <div class="flex items-end justify-between mb-4 border-b border-border-default">
      <div class="flex gap-2">
        <button @click="activeTab = 'watchlist'" :class="['px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px', activeTab === 'watchlist' ? 'border-accent-primary text-accent-primary' : 'border-transparent text-text-secondary hover:text-text-primary']">
          自选 ({{ watchCount }})
        </button>
        <button @click="activeTab = 'pooled'" :class="['px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px', activeTab === 'pooled' ? 'border-accent-primary text-accent-primary' : 'border-transparent text-text-secondary hover:text-text-primary']">
          入池 ({{ pooledCount }})
        </button>
        <button @click="activeTab = 'stats'" :class="['px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px', activeTab === 'stats' ? 'border-accent-primary text-accent-primary' : 'border-transparent text-text-secondary hover:text-text-primary']">
          统计
        </button>
      </div>
      <div class="flex gap-2 pb-2" v-if="activeTab !== 'stats'">
        <button @click="refreshAll" :disabled="refreshing" class="px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1 disabled:opacity-50">
          <RefreshCw :size="14" :class="refreshing ? 'animate-spin' : ''" /> 刷新行情
        </button>
        <button @click="openAddModal" class="px-4 py-2 text-sm rounded-md bg-accent-primary text-white hover:bg-accent-hover flex items-center gap-1">
          <Plus :size="14" /> 添加自选
        </button>
      </div>
    </div>

    <!-- 统计子 tab -->
    <AssetStatsTab v-if="activeTab === 'stats'" />

    <template v-else>
    <div class="flex items-center gap-3 mb-4">
      <div class="relative">
        <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input v-model="search" placeholder="搜索名称 / 代码" class="w-72 pl-9 pr-3 py-2 text-sm border border-border-default rounded-md" />
      </div>
      <select v-model="categoryFilter" class="px-3 py-2 text-sm border border-border-default rounded-md">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
      </select>
      <div class="text-xs text-text-muted ml-auto">研究标的池 · 入池后自动拉取全量历史净值，为因子暴露 / 回测提供数据地基</div>
    </div>

    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">
              <button @click="sortBy('name')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                名称 <SortIcon :dir="sortDir" :active="sortKey === 'name'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium min-w-[110px]">
              <button @click="sortBy('category')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                分类 <SortIcon :dir="sortDir" :active="sortKey === 'category'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('latest_close')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                最新净值 <SortIcon :dir="sortDir" :active="sortKey === 'latest_close'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('ret_1m')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                近1月 <SortIcon :dir="sortDir" :active="sortKey === 'ret_1m'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('ret_1y')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                近1年 <SortIcon :dir="sortDir" :active="sortKey === 'ret_1y'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('ann_volatility')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                年化波动 <SortIcon :dir="sortDir" :active="sortKey === 'ann_volatility'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('sharpe')" class="inline-flex items-center gap-0.5 hover:text-text-primary" title="全样本几何年化夏普">
                夏普 <SortIcon :dir="sortDir" :active="sortKey === 'sharpe'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('sharpe_1y')" class="inline-flex items-center gap-0.5 hover:text-text-primary" title="近 1 年滚动窗口夏普（与近1年列同口径）">
                夏普 1Y <SortIcon :dir="sortDir" :active="sortKey === 'sharpe_1y'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('max_drawdown')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                最大回撤 <SortIcon :dir="sortDir" :active="sortKey === 'max_drawdown'" />
              </button>
            </th>
            <th class="px-3 py-2 font-medium text-right">
              <button @click="sortBy('points')" class="inline-flex items-center gap-0.5 hover:text-text-primary">
                数据 <SortIcon :dir="sortDir" :active="sortKey === 'points'" />
              </button>
            </th>
            <!-- 入池 tab：费用列 -->
            <template v-if="activeTab === 'pooled'">
              <th class="px-3 py-2 font-medium text-right min-w-[70px]">管理费</th>
              <th class="px-3 py-2 font-medium text-right min-w-[70px]">申购费</th>
              <th class="px-3 py-2 font-medium text-right min-w-[150px]">赎回费</th>
              <th class="px-3 py-2 font-medium text-right min-w-[70px]">托管费</th>
              <th class="px-3 py-2 font-medium text-right min-w-[80px]">销售服务费</th>
            </template>
            <th class="px-3 py-2 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filteredAssets" :key="a.id" class="border-t border-border-default">
            <td class="px-3 py-2">
              <div class="font-medium text-text-primary">{{ a.name }}<span v-if="a.is_money_market" class="ml-1 text-xs text-text-muted">货币</span></div>
              <div class="text-xs text-text-muted">{{ a.symbol }} · {{ EXCHANGE_LABELS[a.exchange] || a.exchange || '—' }}</div>
            </td>
            <td class="px-3 py-2">
              <button v-if="a.category" @click="categoryFilter = a.category" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary hover:bg-bg-secondary">{{ a.category }}</button>
              <span v-else class="text-text-muted">—</span>
            </td>
            <td class="px-3 py-2 text-right">
              <div>{{ a.indicators.latest_close != null ? fmt4(a.indicators.latest_close) : '—' }}</div>
              <div class="text-xs text-text-muted">{{ a.indicators.last_date || '' }}</div>
            </td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(a.indicators.ret_1m)">{{ pct(a.indicators.ret_1m) }}</td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(a.indicators.ret_1y)">{{ pct(a.indicators.ret_1y) }}</td>
            <td class="px-3 py-2 text-right">{{ pct(a.indicators.ann_volatility) }}</td>
            <td class="px-3 py-2 text-right" :title="`全样本夏普（年化 ${(a.indicators.ann_return ?? 0)*100 >= 0 ? '+' : ''}${(a.indicators.ann_return ?? 0)*100 > 10 ? (a.indicators.ann_return ?? 0).toFixed(0) : (a.indicators.ann_return ?? 0).toFixed(2)}% / 波动 ${(a.indicators.ann_volatility ?? 0)*100 > 1 ? (a.indicators.ann_volatility ?? 0).toFixed(1) : (a.indicators.ann_volatility ?? 0).toFixed(2)}%）`">
              {{ a.indicators.sharpe != null ? a.indicators.sharpe.toFixed(2) : '—' }}
            </td>
            <td class="px-3 py-2 text-right text-text-secondary" :title="`近 1Y 滚动夏普（与近1年列同口径）`">
              {{ a.indicators.sharpe_1y != null ? a.indicators.sharpe_1y.toFixed(2) : '—' }}
            </td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(a.indicators.max_drawdown)">{{ pct(a.indicators.max_drawdown) }}</td>
            <td class="px-3 py-2 text-right text-xs">
              <div :class="lagClass(a)">{{ a.indicators.points ? `${a.indicators.points} 行` : '无数据' }}</div>
              <div class="text-text-muted">{{ lagText(a) }}</div>
            </td>
            <template v-if="activeTab === 'pooled'">
              <td class="px-3 py-2 text-right">{{ feePct(a.mgmt_fee) }}</td>
              <td class="px-3 py-2 text-right">{{ feePct(a.purchase_fee) }}</td>
              <td class="px-3 py-2 text-right text-xs" :title="a.redeem_fee_note || ''">{{ shortNote(a.redeem_fee_note) }}</td>
              <td class="px-3 py-2 text-right">{{ feePct(a.custody_fee) }}</td>
              <td class="px-3 py-2 text-right">{{ feePct(a.sales_service_fee) }}</td>
            </template>
            <td class="px-3 py-2 text-right whitespace-nowrap">
              <div class="flex items-center justify-end gap-2">
                <button @click="openDetail(a)" title="查看详情与净值曲线" class="text-text-secondary hover:text-accent-primary"><Eye :size="14" /></button>
                <button v-if="a.status === 'watchlist'" @click="openPoolModal(a)" title="入池" class="text-text-secondary hover:text-accent-primary"><PackagePlus :size="14" /></button>
                <button v-if="a.status === 'pooled'" @click="openEditModal(a)" title="编辑" class="text-text-secondary hover:text-accent-primary"><Edit2 :size="14" /></button>
                <button @click="syncOne(a)" :disabled="a._syncing" title="同步历史净值" class="text-accent-primary hover:text-accent-hover disabled:opacity-50">
                  <RefreshCw :size="14" :class="a._syncing ? 'animate-spin' : ''" />
                </button>
                <button @click="removeAsset(a)" title="删除" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && !filteredAssets.length">
            <td :colspan="activeTab === 'pooled' ? 17 : 12" class="px-4 py-8 text-center text-text-muted">{{ activeTab === 'watchlist' ? '暂无自选标的，点击右上角「添加自选」' : '暂无入池标的，从自选列表点击「入池」' }}</td>
          </tr>
          <tr v-if="loading">
            <td :colspan="activeTab === 'pooled' ? 17 : 12" class="px-4 py-8 text-center text-text-muted">加载中…</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <BaseModal v-if="showAddModal" title="添加自选" @close="showAddModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-sm mb-1">代码 *</label><input v-model.trim="addForm.symbol" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 161005" /></div>
          <div>
            <label class="block text-sm mb-1">市场</label>
            <select v-model="addForm.exchange" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="FUND_CN">场外基金</option>
              <option value="SH">沪市</option>
              <option value="SZ">深市</option>
              <option value="US">美股</option>
            </select>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="addForm.asset_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="fund">基金</option>
              <option value="stock">股票</option>
              <option value="index">指数</option>
              <option value="gold">黄金</option>
              <option value="other">其他</option>
            </select>
          </div>
          <div><label class="block text-sm mb-1">分类</label><input v-model.trim="addForm.category" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 核心-宽基" /></div>
        </div>
        <div><label class="block text-sm mb-1">名称</label><input v-model.trim="addForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="留空自动补全" /></div>
        <div class="text-xs text-text-muted">名称留空将通过行情源自动补全；货币基金会自动识别并跳过波动率 / 夏普计算</div>
      </div>
      <template #footer>
        <button @click="showAddModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="submitAdd" :disabled="!addForm.symbol || adding" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-50">{{ adding ? '添加中…' : '添加' }}</button>
      </template>
    </BaseModal>

    <BaseModal v-if="poolTarget" :title="`入池：${poolTarget.name}`" @close="poolTarget = null">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-sm mb-1">管理费 %/年</label><input v-model.number="poolForm.mgmt_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 1.5" /></div>
          <div><label class="block text-sm mb-1">托管费 %/年</label><input v-model.number="poolForm.custody_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.25" /></div>
          <div><label class="block text-sm mb-1">申购费 %</label><input v-model.number="poolForm.purchase_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.15" /></div>
          <div><label class="block text-sm mb-1">销售服务费 %/年</label><input v-model.number="poolForm.sales_service_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.35（C类份额）" /></div>
        </div>
        <div>
          <label class="block text-sm mb-1">赎回费规则（阶梯）</label>
          <div class="space-y-1.5">
            <div v-for="(r, i) in poolForm.redeem_rules" :key="i" class="flex items-center gap-2">
              <span class="text-xs text-text-muted w-16 shrink-0">持有天数</span>
              <input v-model.number="r.days" type="number" min="1" class="w-24 px-2 py-1.5 text-sm border border-border-default rounded-md" placeholder="空=兜底" />
              <span class="text-xs text-text-muted">天以内</span>
              <input v-model.number="r.fee_rate" type="number" step="0.05" min="0" class="w-24 px-2 py-1.5 text-sm border border-border-default rounded-md" placeholder="费率%" />
              <span class="text-xs text-text-muted">%</span>
              <button v-if="poolForm.redeem_rules.length > 1" @click="poolForm.redeem_rules.splice(i, 1)" class="p-1 text-text-muted hover:text-expense-color"><Trash2 :size="13" /></button>
              <button v-else class="p-1 opacity-0" disabled><Trash2 :size="13" /></button>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-1.5">
            <button @click="addRedeemRule()" class="text-xs px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1"><Plus :size="12" /> 加一档</button>
            <span class="text-xs text-text-muted">末档留空天数 = 兜底费率；预览：{{ rulesPreview }}</span>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-sm mb-1">起购金额（元）</label><input v-model.number="poolForm.min_purchase" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 10" /></div>
          <div><label class="block text-sm mb-1">赎回到账 T+N</label><input v-model.number="poolForm.redeem_t_days" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 2" /></div>
          <div>
            <label class="block text-sm mb-1">数据质量</label>
            <select v-model="poolForm.data_quality" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="">未标注</option>
              <option value="良好">良好</option>
              <option value="一般">一般</option>
              <option value="差">差</option>
            </select>
          </div>
        </div>
        <div><label class="block text-sm mb-1">流动性备注</label><input v-model.trim="poolForm.liquidity_note" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 QDII 赎回 T+10，额度紧张" /></div>
        <div class="text-xs text-text-muted">入池将触发后台全量历史净值拉取（iFinD / 东财 / akshare 多源降级），完成后可在数据列看到行数</div>
      </div>
      <template #footer>
        <button @click="poolTarget = null" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="submitPool" :disabled="pooling" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-50">{{ pooling ? '入池中…' : '确认入池' }}</button>
      </template>
    </BaseModal>

    <!-- 编辑弹窗（已入池） -->
    <BaseModal v-if="editTarget" :title="`编辑：${editTarget.name}`" @close="editTarget = null">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-sm mb-1">名称</label><input v-model="editForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">分类</label><input v-model="editForm.category" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 核心-宽基" /></div>
          <div><label class="block text-sm mb-1">管理费 %/年</label><input v-model.number="editForm.mgmt_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">托管费 %/年</label><input v-model.number="editForm.custody_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">申购费 %</label><input v-model.number="editForm.purchase_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">销售服务费 %/年</label><input v-model.number="editForm.sales_service_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        </div>
        <div>
          <label class="block text-sm mb-1">赎回费规则（阶梯）</label>
          <div class="space-y-1.5">
            <div v-for="(r, i) in editForm.redeem_rules" :key="i" class="flex items-center gap-2">
              <input v-model.number="r.days" type="number" min="1" class="w-24 px-2 py-1.5 text-sm border border-border-default rounded-md" placeholder="空=兜底" />
              <span class="text-xs text-text-muted">天以内 ·</span>
              <input v-model.number="r.fee_rate" type="number" step="0.05" min="0" class="w-24 px-2 py-1.5 text-sm border border-border-default rounded-md" placeholder="费率%" />
              <span class="text-xs text-text-muted">%</span>
              <button v-if="editForm.redeem_rules.length > 1" @click="editForm.redeem_rules.splice(i, 1)" class="p-1 text-text-muted hover:text-expense-color"><Trash2 :size="13" /></button>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-1.5">
            <button @click="editForm.redeem_rules.push({ days: null, fee_rate: 0 })" class="text-xs px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1"><Plus :size="12" /> 加一档</button>
            <span class="text-xs text-text-muted">预览：{{ editRulesPreview }}</span>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-3">
          <div><label class="block text-sm mb-1">起购金额（元）</label><input v-model.number="editForm.min_purchase" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">赎回到账 T+N</label><input v-model.number="editForm.redeem_t_days" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div>
            <label class="block text-sm mb-1">数据质量</label>
            <select v-model="editForm.data_quality" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="">未标注</option>
              <option value="良好">良好</option>
              <option value="一般">一般</option>
              <option value="差">差</option>
            </select>
          </div>
        </div>
        <div><label class="block text-sm mb-1">流动性备注</label><input v-model.trim="editForm.liquidity_note" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
      </div>
      <template #footer>
        <button @click="editTarget = null" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="submitEdit" :disabled="editing" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-50">{{ editing ? '保存中…' : '保存' }}</button>
      </template>
    </BaseModal>

    <Teleport to="body">
      <div v-if="detail" class="fixed inset-0 z-50">
        <div class="absolute inset-0 bg-black/40" @click="detail = null"></div>
        <div class="absolute right-0 top-0 h-full w-full max-w-[680px] bg-bg-primary shadow-2xl overflow-y-auto">
          <div class="flex items-center justify-between p-4 border-b border-border-default sticky top-0 bg-bg-primary z-10">
            <div>
              <h3 class="font-semibold">{{ detail.name }}</h3>
              <div class="text-xs text-text-muted">{{ detail.symbol }} · {{ EXCHANGE_LABELS[detail.exchange] || detail.exchange }} · {{ TYPE_LABELS[detail.asset_type] || detail.asset_type }}</div>
            </div>
            <button @click="detail = null" class="p-1 text-text-secondary hover:text-text-primary"><X :size="16" /></button>
          </div>
          <div class="p-6 space-y-5">
            <div class="flex items-center gap-2 flex-wrap">
              <span :class="['px-2 py-0.5 text-xs rounded-md', detail.status === 'pooled' ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary']">{{ detail.status === 'pooled' ? '已入池' : '自选' }}</span>
              <span v-if="detail.category" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary text-text-secondary">{{ detail.category }}</span>
              <span v-if="detail.is_money_market" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary text-text-secondary">货币基金</span>
              <span v-if="detail.data_quality" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary text-text-secondary">数据质量：{{ detail.data_quality }}</span>
            </div>

            <!-- Metric cards (InvestmentDetailDrawer style) -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">最新净值</div>
                <div class="text-base font-semibold mt-1">{{ detail.indicators.latest_close != null ? fmt4(detail.indicators.latest_close) : '—' }}</div>
                <div class="text-xs text-text-muted mt-0.5">{{ detail.indicators.last_date || '' }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">近1月</div>
                <div class="text-base font-semibold mt-1" :class="colorClassNullable(detail.indicators.ret_1m)">{{ pct(detail.indicators.ret_1m) }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">近1年</div>
                <div class="text-base font-semibold mt-1" :class="colorClassNullable(detail.indicators.ret_1y)">{{ pct(detail.indicators.ret_1y) }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">年化波动</div>
                <div class="text-base font-semibold mt-1">{{ pct(detail.indicators.ann_volatility) }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">夏普</div>
                <div class="text-base font-semibold mt-1">{{ detail.indicators.sharpe != null ? detail.indicators.sharpe.toFixed(2) : '—' }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">最大回撤</div>
                <div class="text-base font-semibold mt-1" :class="colorClassNullable(detail.indicators.max_drawdown)">{{ pct(detail.indicators.max_drawdown) }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">数据行数</div>
                <div class="text-base font-semibold mt-1">{{ detail.indicators.points ?? 0 }}</div>
              </div>
              <div class="bg-white rounded-lg p-3 shadow-sm">
                <div class="text-xs text-text-muted">数据新鲜度</div>
                <div class="text-base font-semibold mt-1" :class="lagClass(detail)">{{ lagText(detail) }}</div>
              </div>
            </div>

            <div>
              <div class="flex items-center justify-between mb-2">
                <h4 class="text-sm font-medium">净值曲线</h4>
                <div class="flex gap-1.5">
                  <button v-for="p in PERIODS" :key="p.days" @click="changePeriod(p.days)"
                    :class="['px-2 py-0.5 text-xs rounded-md border', detailDays === p.days ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default hover:bg-bg-tertiary']">
                    {{ p.label }}
                  </button>
                </div>
              </div>
              <div v-if="navLoading" class="text-sm text-text-muted py-8 text-center">加载中…</div>
              <div v-else-if="!navSeries.length" class="text-sm text-text-muted py-8 text-center border border-dashed border-border-default rounded-md">尚未入池，无历史净值数据</div>
              <div v-else>
                <div class="bg-white rounded-lg p-3 shadow-sm">
                  <div style="height: 240px; position: relative">
                    <Line v-if="navSeries.length >= 2" :data="detailChartData" :options="detailChartOpts" />
                  </div>
                  <div class="text-xs text-text-muted mt-1 flex justify-between">
                    <span>MA20/MA60/基准（{{ benchmarkName }}）均已归一化（起点 1.0）</span>
                    <span>{{ navSeries.length }} 个数据点</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 持仓穿透 -->
            <div v-if="canShowHoldings">
              <div class="flex items-center justify-between mb-2">
                <h4 class="text-sm font-medium">持仓穿透（季报）</h4>
                <div class="flex items-center gap-2">
                  <span v-if="holdings.report_date" class="text-xs text-text-muted">截至 {{ holdings.report_date }}</span>
                  <button @click="refreshHoldings" :disabled="holdingsLoading" class="btn-secondary !px-2 !py-1 text-xs disabled:opacity-50">
                    <RefreshCw :size="12" :class="holdingsLoading ? 'animate-spin' : ''" /> {{ holdingsLoading ? '拉取中…' : '刷新' }}
                  </button>
                </div>
              </div>
              <div v-if="holdingsLoading" class="text-sm text-text-muted py-4 text-center">拉取季报持仓数据…</div>
              <div v-else-if="!holdings.top_holdings.length && !holdings.asset_classes.length" class="text-sm text-text-muted py-4 text-center border border-dashed border-border-default rounded-md">
                暂无穿透数据，点击「刷新」拉取
              </div>
              <div v-else class="space-y-3">
                <div v-if="holdings.fund_type" class="text-xs text-text-muted">基金类型：{{ holdings.fund_type }}</div>
                <div v-if="holdings.asset_classes.length" class="bg-white rounded-lg p-3 shadow-sm">
                  <div class="text-xs text-text-muted mb-2">资产类别占比</div>
                  <div class="space-y-1.5">
                    <div v-for="c in holdings.asset_classes" :key="c.name" class="flex items-center gap-2 text-sm">
                      <span class="w-10 text-text-secondary">{{ c.name }}</span>
                      <div class="flex-1 bg-bg-tertiary rounded-full h-2">
                        <div class="bg-accent-primary h-2 rounded-full" :style="{ width: Math.min(c.ratio ?? 0, 100) + '%' }"></div>
                      </div>
                      <span class="text-xs w-12 text-right">{{ c.ratio?.toFixed(1) }}%</span>
                    </div>
                  </div>
                </div>
                <div v-if="holdings.top_holdings.length" class="bg-white rounded-lg p-3 shadow-sm">
                  <div class="text-xs text-text-muted mb-2">前十大重仓</div>
                  <table class="w-full text-sm">
                    <tbody>
                      <tr v-for="h in holdings.top_holdings" :key="h.name" class="border-t border-border-default first:border-t-0">
                        <td class="px-2 py-1.5">{{ h.name }}</td>
                        <td class="px-2 py-1.5 text-right">
                          <span class="inline-block bg-bg-tertiary rounded-full h-1.5 align-middle mr-2" style="width: 80px">
                            <span class="block bg-accent-primary h-1.5 rounded-full" :style="{ width: Math.min(h.ratio ?? 0, 100) + '%' }"></span>
                          </span>
                          {{ h.ratio?.toFixed(2) }}%
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div v-if="holdings.asset_classes.length && !holdings.top_holdings.length" class="text-xs text-text-muted">
                  该基金无股票重仓（商品/ETF/货币类基金通常仅披露资产配置）
                </div>
              </div>
            </div>

            <!-- AI 分析 -->
            <div>
              <div class="flex items-center justify-between mb-2">
                <h4 class="text-sm font-medium">AI 分析</h4>
                <button @click="runAiAnalysis" :disabled="aiLoading" class="btn-primary !px-2.5 !py-1 text-xs disabled:opacity-50">
                  <Sparkles :size="12" :class="aiLoading ? 'animate-pulse' : ''" /> {{ aiLoading ? '分析中…' : 'AI 分析' }}
                </button>
              </div>
              <div v-if="aiLoading" class="text-sm text-text-muted py-4 text-center">搜索最新资讯并生成分析…</div>
              <div v-else-if="aiError" class="text-sm text-expense-color bg-expense-bg rounded-md px-3 py-2">{{ aiError }}</div>
              <div v-else-if="aiReport">
                <div class="bg-white rounded-lg p-3 shadow-sm space-y-2 text-sm">
                  <div class="flex items-center gap-2">
                    <span class="text-xs px-2 py-0.5 rounded" :class="sentimentCls(aiReport.analysis?.sentiment)">{{ sentimentLabel(aiReport.analysis?.sentiment) }}</span>
                    <span v-if="aiReport.analysis?.sentiment_confidence" class="text-xs text-text-muted">置信度 {{ (aiReport.analysis.sentiment_confidence * 100).toFixed(0) }}%</span>
                    <span class="text-xs text-text-muted ml-auto">{{ fmtDate(aiReport.generated_at) }}</span>
                  </div>
                  <div v-if="aiReport.analysis?.summary" class="text-text-secondary leading-6">{{ aiReport.analysis.summary }}</div>
                  <div v-if="aiReport.analysis?.key_findings?.length" class="space-y-1">
                    <div v-for="f in aiReport.analysis.key_findings" :key="f" class="flex gap-1.5 text-text-secondary"><span class="text-income-color">▸</span>{{ f }}</div>
                  </div>
                  <div v-if="aiReport.analysis?.key_risks?.length" class="space-y-1">
                    <div v-for="r in aiReport.analysis.key_risks" :key="r" class="flex gap-1.5 text-text-secondary"><span class="text-expense-color">▸</span>{{ r }}</div>
                  </div>
                  <div v-if="aiReport.analysis?.suggested_action" class="text-xs bg-bg-tertiary rounded-md px-2 py-1.5">
                    <span class="text-text-muted">建议：</span>{{ aiReport.analysis.suggested_action }}
                  </div>
                </div>
                <div v-if="aiReport.raw_articles?.length" class="mt-2">
                  <div class="text-xs text-text-muted mb-1.5">参考资讯（{{ aiReport.raw_articles.length }} 条）</div>
                  <div class="space-y-1">
                    <a v-for="a in aiReport.raw_articles" :key="a.url || a.title" :href="a.url" target="_blank" rel="noopener"
                      class="block text-xs text-text-secondary hover:text-accent-primary truncate">
                      {{ a.title }} <span v-if="a.date" class="text-text-muted">· {{ a.date }}</span>
                    </a>
                  </div>
                </div>
                <div v-if="aiHistory.length > 0" class="mt-3">
                  <div class="text-xs text-text-muted mb-1">历史报告（{{ aiHistory.length }} 条）</div>
                  <div class="space-y-1">
                    <div v-for="h in aiHistory" :key="h.report_id"
                      :class="['flex items-center gap-1 text-xs px-2 py-1.5 rounded border', h.report_id === aiReport.report_id ? 'border-accent-primary bg-accent-light' : 'border-border-default hover:bg-bg-tertiary']">
                      <button class="flex-1 text-left min-w-0" @click="selectAiHistory(h.report_id)">
                        {{ fmtDate(h.generated_at) }} · {{ h.query || h.asset_name }}
                      </button>
                      <button @click.stop="deleteAiReport(h.report_id)" title="删除该报告"
                        class="text-text-muted hover:text-expense-color shrink-0">
                        <Trash2 :size="12" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-sm text-text-muted py-4 text-center border border-dashed border-border-default rounded-md">
                点击「AI 分析」搜索最新资讯并生成深度分析
              </div>
            </div>

            <div>
              <h4 class="text-sm font-medium mb-2">费率与规则</h4>
              <div class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <div class="flex justify-between"><span class="text-text-muted">管理费</span><span>{{ detail.mgmt_fee != null ? detail.mgmt_fee + ' %/年' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">托管费</span><span>{{ detail.custody_fee != null ? detail.custody_fee + ' %/年' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">申购费</span><span>{{ detail.purchase_fee != null ? detail.purchase_fee + ' %' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">销售服务费</span><span>{{ detail.sales_service_fee != null ? detail.sales_service_fee + ' %/年' : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">起购金额</span><span>{{ detail.min_purchase != null ? '¥' + detail.min_purchase : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">赎回到账</span><span>{{ detail.redeem_t_days != null ? 'T+' + detail.redeem_t_days : '—' }}</span></div>
                <div class="flex justify-between"><span class="text-text-muted">赎回费</span><span class="text-right">{{ detail.redeem_fee_note || '—' }}</span></div>
              </div>
              <div v-if="detail.liquidity_note" class="mt-2 text-xs text-text-muted">流动性：{{ detail.liquidity_note }}</div>
              <div v-if="detail.notes" class="mt-2 text-xs text-text-muted">备注：{{ detail.notes }}</div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Plus, RefreshCw, Search, X, Eye, PackagePlus, Trash2, Edit2, ChevronUp, ChevronDown, ChevronsUpDown, Sparkles } from 'lucide-vue-next'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import AssetStatsTab from './AssetStatsTab.vue'
import type { ResearchAsset, ResearchPricePoint, SyncResult, AssetPriceStatus } from '@/types'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const api = useApi()
const { show } = useToast()

const TYPE_LABELS: Record<string, string> = { fund: '基金', stock: '股票', index: '指数', gold: '黄金', other: '其他' }
const EXCHANGE_LABELS: Record<string, string> = { SH: '沪市', SZ: '深市', FUND_CN: '场外基金', US: '美股', HK: '港股' }

interface AssetRow extends ResearchAsset { _syncing?: boolean }

const assets = ref<AssetRow[]>([])
const activeTab = ref<'watchlist' | 'pooled' | 'stats'>('watchlist')
const search = ref('')
const categoryFilter = ref('')
const loading = ref(false)
const refreshing = ref(false)

const watchCount = computed(() => assets.value.filter(a => a.status === 'watchlist').length)
const pooledCount = computed(() => assets.value.filter(a => a.status === 'pooled').length)
const categories = computed(() => [...new Set(assets.value.map(a => a.category).filter(Boolean))] as string[])

// ---- sorting ----
type SortKey = 'name' | 'category' | 'latest_close' | 'ret_1m' | 'ret_1y' | 'ann_volatility' | 'sharpe' | 'sharpe_1y' | 'max_drawdown' | 'points'
const sortKey = ref<SortKey>('name')
const sortDir = ref<'asc' | 'desc'>('asc')

function sortBy(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'name' || key === 'category' ? 'asc' : 'desc'
  }
}

function sortVal(a: AssetRow, key: SortKey): number | string | null | undefined {
  switch (key) {
    case 'name': return a.name
    case 'category': return a.category || null
    case 'latest_close': return a.indicators.latest_close
    case 'ret_1m': return a.indicators.ret_1m
    case 'ret_1y': return a.indicators.ret_1y
    case 'ann_volatility': return a.indicators.ann_volatility
    case 'sharpe': return a.indicators.sharpe
    case 'sharpe_1y': return a.indicators.sharpe_1y
    case 'max_drawdown': return a.indicators.max_drawdown
    case 'points': return a.indicators.points
  }
}

const filteredAssets = computed(() => {
  const kw = search.value.trim().toLowerCase()
  const list = assets.value.filter(a => {
    if (a.status !== activeTab.value) return false
    if (categoryFilter.value && a.category !== categoryFilter.value) return false
    if (kw && !(a.name.toLowerCase().includes(kw) || a.symbol.toLowerCase().includes(kw))) return false
    return true
  })
  return [...list].sort((x, y) => {
    const vx = sortVal(x, sortKey.value)
    const vy = sortVal(y, sortKey.value)
    if (vx == null && vy == null) return 0
    if (vx == null) return 1          // null/— always last
    if (vy == null) return -1
    let c: number
    if (typeof vx === 'string' && typeof vy === 'string') c = vx.localeCompare(vy, 'zh-CN')
    else c = (vx as number) - (vy as number)
    return sortDir.value === 'asc' ? c : -c
  })
})

function feePct(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(2) + '%'
}
function shortNote(note: string): string {
  if (!note) return '—'
  return note.length > 14 ? note.slice(0, 14) + '…' : note
}

// Inline sort-arrow icon component (usable in template)
import { h } from 'vue'
const SortIcon = (props: { dir: 'asc' | 'desc'; active: boolean }) => {
  if (!props.active) return h(ChevronsUpDown, { size: 12, class: 'text-text-muted' })
  return props.dir === 'asc'
    ? h(ChevronUp, { size: 12, class: 'text-accent-primary' })
    : h(ChevronDown, { size: 12, class: 'text-accent-primary' })
}

function fmt4(n: number): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 }) }
function pct(v: number | null | undefined): string { return v === null || v === undefined ? '—' : (v * 100).toFixed(2) + '%' }
function colorClassNullable(v: number | null | undefined): string { return v === null || v === undefined ? '' : (v >= 0 ? 'text-income-color' : 'text-expense-color') }
function lagText(a: ResearchAsset): string {
  const p = a.indicators.points
  if (!p) return ''
  const d = a.indicators.last_date
  if (!d) return ''
  const lag = Math.floor((Date.now() - new Date(d + 'T00:00:00').getTime()) / 86400000)
  return lag <= 7 ? `最新 ${d.slice(5)}` : `落后 ${lag} 天`
}
function lagClass(a: ResearchAsset): string {
  const d = a.indicators.last_date
  if (!d) return ''
  const lag = Math.floor((Date.now() - new Date(d + 'T00:00:00').getTime()) / 86400000)
  return lag > 7 ? 'text-expense-color' : ''
}

function errDetail(e: unknown): string {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  return err?.response?.data?.detail || err?.message || '请求失败'
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/research/assets')
    assets.value = res.data as ResearchAsset[]
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    loading.value = false
  }
}

const showAddModal = ref(false)
const adding = ref(false)
const addForm = ref({ symbol: '', exchange: 'FUND_CN', asset_type: 'fund', category: '', name: '' })

function openAddModal() {
  addForm.value = { symbol: '', exchange: 'FUND_CN', asset_type: 'fund', category: '', name: '' }
  showAddModal.value = true
}

async function submitAdd() {
  adding.value = true
  try {
    const res = await api.post('/research/assets', addForm.value)
    show(`已添加自选：${(res.data as ResearchAsset).name}`, 'success')
    showAddModal.value = false
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    adding.value = false
  }
}

const poolTarget = ref<ResearchAsset | null>(null)
const pooling = ref(false)
interface RedeemRuleForm { days: number | null; fee_rate: number }
const poolForm = ref<{
  mgmt_fee: number | null; custody_fee: number | null; purchase_fee: number | null;
  sales_service_fee: number | null; redeem_rules: RedeemRuleForm[]; redeem_fee_note: string;
  min_purchase: number | null; redeem_t_days: number | null; liquidity_note: string; data_quality: string;
}>({
  mgmt_fee: null, custody_fee: null, purchase_fee: null, sales_service_fee: null,
  redeem_rules: [{ days: 7, fee_rate: 1.5 }, { days: 30, fee_rate: 0.5 }, { days: null, fee_rate: 0 }],
  redeem_fee_note: '', min_purchase: null, redeem_t_days: null, liquidity_note: '', data_quality: '',
})

const rulesPreview = computed(() => {
  return poolForm.value.redeem_rules.map(r =>
    r.days == null ? `其余 ${r.fee_rate}%` : `<${r.days}天 ${r.fee_rate}%`
  ).join('，')
})

function addRedeemRule() {
  poolForm.value.redeem_rules.push({ days: null, fee_rate: 0 })
}

function openPoolModal(a: ResearchAsset) {
  poolTarget.value = a
  poolForm.value = {
    mgmt_fee: null, custody_fee: null, purchase_fee: null, sales_service_fee: null,
    redeem_rules: [{ days: 7, fee_rate: 1.5 }, { days: 30, fee_rate: 0.5 }, { days: null, fee_rate: 0 }],
    redeem_fee_note: '', min_purchase: null, redeem_t_days: null, liquidity_note: '', data_quality: '',
  }
}

// ---- edit modal (pooled assets) ----
const editTarget = ref<ResearchAsset | null>(null)
const editing = ref(false)
const editForm = ref<{
  name: string; category: string; mgmt_fee: number | null; custody_fee: number | null;
  purchase_fee: number | null; sales_service_fee: number | null; redeem_rules: RedeemRuleForm[];
  min_purchase: number | null; redeem_t_days: number | null; liquidity_note: string; data_quality: string;
}>({
  name: '', category: '', mgmt_fee: null, custody_fee: null, purchase_fee: null, sales_service_fee: null,
  redeem_rules: [], min_purchase: null, redeem_t_days: null, liquidity_note: '', data_quality: '',
})

const editRulesPreview = computed(() => {
  return editForm.value.redeem_rules.map(r =>
    r.days == null ? `其余 ${r.fee_rate}%` : `<${r.days}天 ${r.fee_rate}%`
  ).join('，')
})

function openEditModal(a: ResearchAsset) {
  editTarget.value = a
  editForm.value = {
    name: a.name, category: a.category || '',
    mgmt_fee: a.mgmt_fee, custody_fee: a.custody_fee, purchase_fee: a.purchase_fee,
    sales_service_fee: a.sales_service_fee,
    redeem_rules: (a.redeem_rules?.length ? a.redeem_rules : []).map(r => ({ days: r.days ?? null, fee_rate: r.fee_rate })),
    min_purchase: a.min_purchase, redeem_t_days: a.redeem_t_days,
    liquidity_note: a.liquidity_note || '', data_quality: a.data_quality || '',
  }
}

async function submitEdit() {
  if (!editTarget.value) return
  editing.value = true
  try {
    const target = editTarget.value
    const payload: Record<string, unknown> = {
      name: editForm.value.name,
      category: editForm.value.category,
      mgmt_fee: editForm.value.mgmt_fee,
      custody_fee: editForm.value.custody_fee,
      purchase_fee: editForm.value.purchase_fee,
      sales_service_fee: editForm.value.sales_service_fee,
      redeem_rules: editForm.value.redeem_rules,
      min_purchase: editForm.value.min_purchase,
      redeem_t_days: editForm.value.redeem_t_days,
      liquidity_note: editForm.value.liquidity_note,
      data_quality: editForm.value.data_quality,
    }
    await api.put(`/research/assets/${target.id}`, payload)
    show('已保存', 'success')
    editTarget.value = null
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    editing.value = false
  }
}

let pollTimer: ReturnType<typeof setTimeout> | null = null

async function submitPool() {
  if (!poolTarget.value) return
  pooling.value = true
  try {
    const target = poolTarget.value
    await api.post(`/research/assets/${target.id}/pool`, poolForm.value)
    show('已入池，后台正在拉取全量历史净值…', 'success')
    poolTarget.value = null
    await load()
    pollPriceStatus(target.id, 10)
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    pooling.value = false
  }
}

function pollPriceStatus(assetId: string, remaining: number) {
  if (remaining <= 0) return
  pollTimer = setTimeout(async () => {
    try {
      const res = await api.get('/research/assets/price-status')
      const st = (res.data as AssetPriceStatus[]).find(s => s.asset_id === assetId)
      if (st && st.rows > 0) {
        show(`历史净值拉取完成（${st.rows} 行，${st.last_date}）`, 'success')
        await load()
        return
      }
    } catch { /* transient — keep polling */ }
    pollPriceStatus(assetId, remaining - 1)
  }, 3000)
}

async function syncOne(a: AssetRow) {
  a._syncing = true
  try {
    const res = await api.post(`/research/assets/${a.id}/sync`)
    const r = res.data as SyncResult
    show(`同步成功：${r.rows} 行（${r.begin} ~ ${r.end}，${r.source}）`, 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    a._syncing = false
  }
}

async function refreshAll() {
  refreshing.value = true
  try {
    const res = await api.post('/research/assets/refresh-prices')
    const results = res.data as SyncResult[]
    const ok = results.filter(r => !r.error)
    const fail = results.filter(r => r.error)
    show(`刷新完成：成功 ${ok.length}（共 ${ok.reduce((s, r) => s + r.rows, 0)} 行）${fail.length ? ` / 失败 ${fail.length}` : ''}`, fail.length ? 'warning' : 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    refreshing.value = false
  }
}

async function removeAsset(a: ResearchAsset) {
  if (!confirm(`确认删除「${a.name}」及其全部历史净值数据？`)) return
  try {
    await api.delete(`/research/assets/${a.id}`)
    show('已删除', 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  }
}

const detail = ref<ResearchAsset | null>(null)
const navSeries = ref<{ date: string; close: number; ma20: number | null; ma60: number | null }[]>([])
const benchmarkData = ref<{ name: string; symbol: string; exchange: string; series: { date: string; close: number }[] } | null>(null)
const navLoading = ref(false)
const PERIODS = [
  { label: '1月', days: 30 }, { label: '3月', days: 90 }, { label: '6月', days: 180 },
  { label: '1年', days: 365 }, { label: '3年', days: 1095 },
]
const detailDays = ref(365)

const benchmarkName = computed(() => benchmarkData.value?.name || '')

const canShowHoldings = computed(() =>
  !!detail.value && detail.value.exchange === 'FUND_CN' && detail.value.asset_type === 'fund')

async function openDetail(a: ResearchAsset) {
  detail.value = a
  detailDays.value = 365
  holdings.value = { report_date: null, asset_classes: [], top_holdings: [], fund_type: null }
  aiReport.value = null
  aiError.value = ''
  aiHistory.value = []
  await Promise.all([loadNav(), loadHoldings(), loadAiHistory()])
}

async function changePeriod(days: number) {
  if (detailDays.value === days) return
  detailDays.value = days
  await loadNav()
}

async function loadNav() {
  if (!detail.value) return
  navLoading.value = true
  try {
    const res = await api.get(`/research/assets/${detail.value.id}/nav-history`, {
      params: { days: detailDays.value, with_benchmark: true, with_ma: true },
    })
    navSeries.value = res.data.series ?? []
    benchmarkData.value = res.data.benchmark ?? null
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    navLoading.value = false
  }
}

// chart.js Line datasets (normalized start=1.0, like the holdings drawer)
const detailChartData = computed(() => {
  const labels = navSeries.value.map(p => p.date)
  const closes = navSeries.value.map(p => p.close)
  const start = closes.length && closes[0] !== 0 ? closes[0] : 1
  const norm = (v: number | null) => (v == null ? null : v / start)
  const datasets: any[] = [
    { label: '净值', data: closes.map(v => v / start), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.06)', borderWidth: 1.5, tension: 0.25, pointRadius: 0, fill: true, yAxisID: 'y' },
  ]
  if (navSeries.value.some(p => p.ma20 != null)) {
    datasets.push({ label: 'MA20', data: navSeries.value.map(p => norm(p.ma20)), borderColor: '#f59e0b', borderDash: [5, 5], borderWidth: 1.2, tension: 0.25, pointRadius: 0, fill: false, yAxisID: 'y' })
  }
  if (navSeries.value.some(p => p.ma60 != null)) {
    datasets.push({ label: 'MA60', data: navSeries.value.map(p => norm(p.ma60)), borderColor: '#a855f7', borderDash: [5, 5], borderWidth: 1.2, tension: 0.25, pointRadius: 0, fill: false, yAxisID: 'y' })
  }
  const bm = benchmarkData.value
  if (bm?.series?.length && bm.series[0]?.close) {
    const b0 = bm.series[0].close
    const bCloseByDate = new Map(bm.series.map(s => [s.date, s.close] as const))
    let last = b0
    const aligned = navSeries.value.map(p => {
      const c = bCloseByDate.get(p.date)
      if (c !== undefined) last = c
      return last / b0
    })
    datasets.push({ label: `${bm.name}（起点归一）`, data: aligned, borderColor: '#9ca3af', borderDash: [5, 4], borderWidth: 1.2, tension: 0.25, pointRadius: 0, fill: false, yAxisID: 'y' })
  }
  return { labels, datasets }
})

const detailChartOpts = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: 'index' as const, intersect: false },
  plugins: {
    legend: { display: true, labels: { boxWidth: 12, font: { size: 10 } } },
    tooltip: {
      callbacks: {
        label: (ctx: any) => {
          const v = ctx.parsed.y as number
          const p = navSeries.value[ctx.dataIndex]
          const prefix = ctx.dataset.label === `${benchmarkName.value}（起点归一）` ? '基准' : ctx.dataset.label
          if (!p) return `${prefix}: ${v.toFixed(4)}`
          if (ctx.dataset.label === '净值') return [`净值 ${p.close.toFixed(4)}（归一 ${v.toFixed(4)}）`]
          return `${prefix}: ${v.toFixed(4)}`
        },
      },
    },
  },
  scales: {
    x: { ticks: { maxTicksLimit: 8, font: { size: 10 }, maxRotation: 0, autoSkipPadding: 20 }, grid: { display: false } },
    y: { ticks: { font: { size: 10 } }, grid: { color: 'rgba(0,0,0,0.05)' } },
  },
}

// ---- holdings transparency ----
const holdings = ref<{ report_date: string | null; asset_classes: { name: string; ratio: number | null }[]; top_holdings: { name: string; ratio: number | null }[]; fund_type: string | null }>({
  report_date: null, asset_classes: [], top_holdings: [], fund_type: null,
})
const holdingsLoading = ref(false)

async function loadHoldings() {
  if (!detail.value || !canShowHoldings.value) return
  try {
    const res = await api.get(`/research/assets/${detail.value.id}/holdings`)
    if (res.data?.status === 'ok') holdings.value = res.data
  } catch { /* ignore */ }
}

async function refreshHoldings() {
  if (!detail.value) return
  holdingsLoading.value = true
  try {
    const res = await api.post(`/research/assets/${detail.value.id}/holdings/refresh`)
    if (res.data?.status === 'ok') {
      holdings.value = res.data
      show('持仓穿透数据已更新', 'success')
    }
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    holdingsLoading.value = false
  }
}

// ---- AI analysis ----
const aiReport = ref<any | null>(null)
const aiLoading = ref(false)
const aiError = ref('')
const aiHistory = ref<any[]>([])

async function loadAiHistory() {
  if (!detail.value) return
  try {
    const res = await api.get(`/research/assets/${detail.value.id}/ai-reports`)
    aiHistory.value = res.data ?? []
    // Auto-select the newest report so reopening the drawer shows it immediately
    if (aiHistory.value.length && !aiReport.value) {
      await selectAiHistory(aiHistory.value[0].report_id)
    }
  } catch { aiHistory.value = [] }
}

async function deleteAiReport(reportId: string) {
  try {
    await api.delete(`/research/assets/ai-reports/${reportId}`)
    aiHistory.value = aiHistory.value.filter(h => h.report_id !== reportId)
    if (aiReport.value?.report_id === reportId) {
      aiReport.value = null
      // show the next newest report if any remain
      if (aiHistory.value.length) await selectAiHistory(aiHistory.value[0].report_id)
    }
    show('报告已删除', 'success')
  } catch (e: any) {
    show(errDetail(e), 'error')
  }
}

async function runAiAnalysis() {
  if (!detail.value) return
  aiLoading.value = true
  aiError.value = ''
  try {
    const res = await api.post(`/research/assets/${detail.value.id}/ai-analysis`, { days: 30, max_results: 8 })
    aiReport.value = res.data
    await loadAiHistory()
  } catch (e: any) {
    aiError.value = e?.response?.data?.detail || 'AI 分析失败'
  } finally {
    aiLoading.value = false
  }
}

async function selectAiHistory(reportId: string) {
  try {
    const res = await api.get(`/research/assets/ai-reports/${reportId}`)
    aiReport.value = res.data
  } catch { /* ignore */ }
}

function sentimentLabel(s?: string): string {
  const m: Record<string, string> = { positive: '看多', negative: '看空', neutral: '中性', mixed: '分歧' }
  return s ? (m[s] ?? s) : '—'
}
function sentimentCls(s?: string): string {
  const m: Record<string, string> = {
    positive: 'bg-income-bg text-income-color', negative: 'bg-expense-bg text-expense-color',
    neutral: 'bg-bg-tertiary text-text-secondary', mixed: 'bg-warning-bg text-warning',
  }
  return s ? (m[s] ?? 'bg-bg-tertiary text-text-secondary') : 'bg-bg-tertiary text-text-secondary'
}
function fmtDate(v?: string): string {
  return v ? v.slice(0, 10) : '—'
}

onMounted(load)
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>
