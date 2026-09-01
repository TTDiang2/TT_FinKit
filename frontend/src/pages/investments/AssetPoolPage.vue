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
        <button
          :class="['px-4 py-2 text-sm font-medium border-b-2 -mb-px', activeTab === 'hot' ? 'border-accent-primary text-accent-primary' : 'border-transparent text-text-secondary hover:text-text-primary']"
          @click="activeTab = 'hot'"
        >热点</button>
        <select v-if="activeTab !== 'stats'" v-model="serverSort"
          @change="page = 1; load()"
          class="ml-auto px-2 py-1.5 text-xs border border-border-default rounded-md text-text-secondary"
          title="全库级排序（基于预计算指标）">
          <option value="">默认排序</option>
          <option value="sharpe_1y">近1年夏普 高→低</option>
          <option value="ret_252d">近1年收益 高→低</option>
          <option value="ret_63d">近3月收益 高→低</option>
          <option value="ret_21d">近1月收益 高→低</option>
          <option value="mdd_1y">近1年回撤 小→大</option>
          <option value="vol_1y">近1年波动 低→高</option>
        </select>
      </div>
      <div class="flex gap-2 pb-2" v-if="activeTab !== 'stats'">
        <button @click="refreshAll" :disabled="refreshing" class="px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1 disabled:opacity-50">
          <RefreshCw :size="14" :class="refreshing ? 'animate-spin' : ''" /> 刷新行情
        </button>
        <button @click="showImportModal = true" class="px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1">
          <Download :size="14" /> 天天基金导入
        </button>
        <button @click="openBatchModal" :disabled="!selectedIds.size"
          :class="['px-4 py-2 text-sm rounded-md flex items-center gap-1', selectedIds.size ? 'bg-accent-primary text-white hover:bg-accent-hover' : 'border border-border-default text-text-muted cursor-not-allowed']">
          <ListChecks :size="14" /> 批量操作 ({{ selectedIds.size }})
        </button>
        <button @click="openGroupsModal" class="px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1">
          <FolderOpen :size="14" /> 组合管理
        </button>
        <button @click="openAddModal" class="px-4 py-2 text-sm rounded-md bg-accent-primary text-white hover:bg-accent-hover flex items-center gap-1">
          <Plus :size="14" /> 添加自选
        </button>
      </div>
    </div>

    <!-- 统计子 tab -->
    <AssetStatsTab v-if="activeTab === 'stats'" />
    <HotTab v-if="activeTab === 'hot'" />

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
      <select v-model="kindFilter" class="px-3 py-2 text-sm border border-border-default rounded-md" title="类型：ETF/指数跟踪/主动管理等">
        <option value="">全部类型</option>
        <option v-for="v in kindOptions" :key="v" :value="v">{{ v }}</option>
      </select>
      <select v-model="classFilter" class="px-3 py-2 text-sm border border-border-default rounded-md" title="资产类别：偏股/偏债/另类等">
        <option value="">全部资产类别</option>
        <option v-for="v in classOptions" :key="v" :value="v">{{ v }}</option>
      </select>
      <select v-model="regionFilter" class="px-3 py-2 text-sm border border-border-default rounded-md" title="地区：境内/QDII细分">
        <option value="">全部地区</option>
        <option v-for="v in regionOptions" :key="v" :value="v">{{ v }}</option>
      </select>
      <select v-model="limitFilter" class="px-3 py-2 text-sm border border-border-default rounded-md" title="日累计申购限额">
        <option value="">全部限购情况</option>
        <option value="limited">限购中</option>
        <option value="unlimited">不限购</option>
      </select>
      <select v-model="groupFilter" class="px-3 py-2 text-sm border border-border-default rounded-md" title="按标的组合过滤">
        <option value="">全部组合</option>
        <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.asset_ids.length }}）</option>
      </select>
      <div class="text-xs text-text-muted ml-auto flex items-center gap-2">
        <button @click="selectAllFiltered" class="px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary">全选筛选结果</button>
        <button v-if="selectedIds.size" @click="clearSelection" class="px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary">清空选择</button>
        <span>已选 {{ selectedIds.size }}</span>
      </div>
    </div>

    <div class="bg-white rounded-lg shadow-sm overflow-hidden">
      <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-2 py-2 w-8">
              <input type="checkbox" :checked="pageAllChecked" @change="toggleAllPage" title="全选/取消本页" />
            </th>
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
              <th class="px-3 py-2 font-medium text-right min-w-[90px]" title="日累计申购限额（元），空=不限/未设置">限额额度</th>
            </template>
            <th class="px-3 py-2 font-medium text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filteredAssets" :key="a.id" :class="['border-t border-border-default hover:bg-bg-tertiary/40 cursor-pointer', selectedIds.has(a.id) ? 'bg-accent-primary/5' : '']" @dblclick="openDetail(a)">
            <td class="px-2 py-2 w-8" @click.stop>
              <input type="checkbox" :checked="selectedIds.has(a.id)" @change="toggleSelect(a.id)" />
            </td>
            <td class="px-3 py-2">
              <div class="font-medium text-text-primary">{{ a.name }}<span v-if="a.is_money_market" class="ml-1 text-xs text-text-muted">货币</span></div>
              <div class="text-xs text-text-muted">{{ a.symbol }} · {{ EXCHANGE_LABELS[a.exchange] || a.exchange || '—' }}</div>
            </td>
            <td class="px-3 py-2 min-w-[110px]">
              <span v-if="a.purchase_status && a.purchase_status !== '开放申购'"
                :title="`申购状态：${a.purchase_status}（天天基金）`"
                class="px-1.5 py-0.5 text-xs rounded-md bg-income-bg text-income-color font-medium">{{ a.purchase_status }}</span>
              <span v-if="limitShort(a.purchase_limit)" :title="`日累计申购限额 ${a.purchase_limit} 元（天天基金）`"
                class="px-1.5 py-0.5 text-xs rounded-md bg-income-bg text-income-color font-medium">{{ limitShort(a.purchase_limit) }}</span>
              <button v-if="a.category" @click="categoryFilter = a.category" class="px-2 py-0.5 text-xs rounded-md bg-bg-tertiary hover:bg-bg-secondary">{{ a.category }}</button>
              <span v-if="!a.category && !a.fund_kind && !a.asset_class && !a.region && !(a.auto_tags && a.auto_tags.length)" class="text-text-muted">—</span>
              <div v-if="a.fund_kind || a.asset_class || a.region || (a.auto_tags && a.auto_tags.length)" class="flex flex-wrap gap-1 mt-0.5">
                <span v-if="a.fund_kind" class="px-1.5 py-0.5 text-xs rounded-md bg-purple-50 text-purple-700">{{ a.fund_kind }}</span>
                <span v-if="a.asset_class" class="px-1.5 py-0.5 text-xs rounded-md bg-sky-50 text-sky-700">{{ a.asset_class }}</span>
                <span v-if="a.region" :class="['px-1.5 py-0.5 text-xs rounded-md', a.region === '境内' ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700']">{{ a.region }}</span>
                <span v-for="t in (a.auto_tags || [])" :key="t" :title="`主题标签（来自持仓/名称推断）· 点击筛选`" @click="themeTagFilter = themeTagFilter === t ? '' : t"
                  :class="['px-1.5 py-0.5 text-xs rounded-md cursor-pointer', themeTagFilter === t ? 'bg-accent-primary text-white' : 'bg-bg-tertiary text-text-secondary hover:bg-bg-secondary']">{{ t }}</span>
              </div>
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
              <div v-if="isStaleNav(a)" class="text-expense-color font-medium" title="净值长期恒定、近1年收益与年化波动均为0——疑似清盘/停牌/口径异常，建议核查后删除">⚠ 疑似停更</div>
            </td>
            <template v-if="activeTab === 'pooled'">
              <td class="px-3 py-2 text-right">{{ feePct(a.mgmt_fee) }}</td>
              <td class="px-3 py-2 text-right">{{ feePct(a.purchase_fee) }}</td>
              <td class="px-3 py-2 text-right text-xs" :title="a.redeem_fee_note || ''">{{ shortNote(a.redeem_fee_note) }}</td>
              <td class="px-3 py-2 text-right">{{ feePct(a.custody_fee) }}</td>
              <td class="px-3 py-2 text-right">{{ feePct(a.sales_service_fee) }}</td>
              <td class="px-3 py-2 text-right" :class="a.purchase_limit ? 'text-text-primary' : 'text-text-muted'">
                <span :title="a.profile_synced_at ? `档案更新于 ${a.profile_synced_at.slice(0, 16)}` : '未从天天基金同步过档案'">
                  {{ limitText(a.purchase_limit) }}
                </span>
              </td>
            </template>
            <td class="px-3 py-2 text-right whitespace-nowrap">
              <div class="flex items-center justify-end gap-2">
                <button @click="openDetail(a)" title="查看详情与净值曲线（双击行亦可）" class="text-text-secondary hover:text-accent-primary"><Eye :size="14" /></button>
                <button v-if="a.status === 'watchlist'" @click="openPoolModal(a)" title="入池" class="text-text-secondary hover:text-accent-primary"><PackagePlus :size="14" /></button>
                <template v-if="a.status === 'pooled'">
                  <button @click="openEditModal(a)" title="编辑" class="text-text-secondary hover:text-accent-primary"><Edit2 :size="14" /></button>
                  <button @click="unpoolOne(a)" title="踢出入池（退回自选，保留数据）" class="text-text-secondary hover:text-warning"><PackageMinus :size="14" /></button>
                </template>
                <button @click="syncOne(a)" :disabled="a._syncing" title="同步历史净值" class="text-accent-primary hover:text-accent-hover disabled:opacity-50">
                  <RefreshCw :size="14" :class="a._syncing ? 'animate-spin' : ''" />
                </button>
                <button v-if="a.status === 'watchlist'" @click="removeAsset(a)" title="删除（连同历史净值）" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && !filteredAssets.length">
            <td :colspan="activeTab === 'pooled' ? 18 : 12" class="px-4 py-8 text-center text-text-muted">{{ activeTab === 'watchlist' ? '暂无自选标的，点击右上角「添加自选」或「天天基金导入」' : '暂无入池标的，从自选列表点击「入池」' }}</td>
          </tr>
          <tr v-if="loading">
            <td :colspan="activeTab === 'pooled' ? 18 : 12" class="px-4 py-8 text-center text-text-muted">加载中…</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <!-- 分页器 -->
    <div v-if="pages > 1" class="flex items-center justify-between mt-4 px-2">
      <div class="text-sm text-text-secondary">
        共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页 · 每页
        <select v-model="pageSize" class="px-2 py-1 text-sm border border-border-default rounded-md ml-1"
                @change="page = 1; load()">
          <option value="25">25</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
      </div>
      <div class="flex items-center gap-1">
        <button @click="page--" :disabled="page <= 1" class="px-3 py-1 text-sm border border-border-default rounded-md disabled:opacity-50 disabled:cursor-not-allowed hover:bg-bg-tertiary">上一页</button>
        <template v-for="p in visiblePages" :key="p">
          <button v-if="p === '...'" class="px-3 py-1 text-sm text-text-muted cursor-default">…</button>
          <button v-else @click="page = p"
            :class="['px-3 py-1 text-sm rounded-md border', page === p ? 'bg-accent-primary text-white border-accent-primary' : 'border-border-default hover:bg-bg-tertiary']">
            {{ p }}
          </button>
        </template>
        <button @click="page++" :disabled="page >= pages" class="px-3 py-1 text-sm border border-border-default rounded-md disabled:opacity-50 disabled:cursor-not-allowed hover:bg-bg-tertiary">下一页</button>
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

        <div class="border-t border-border-default pt-3">
          <div class="text-xs text-text-muted mb-2">费用与限额（可留空，入池或批量更新时从天天基金自动拉取）</div>
          <div class="grid grid-cols-4 gap-3">
            <div><label class="block text-sm mb-1">管理费 %/年</label><input v-model.number="addForm.mgmt_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 1.5" /></div>
            <div><label class="block text-sm mb-1">托管费 %/年</label><input v-model.number="addForm.custody_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.25" /></div>
            <div><label class="block text-sm mb-1">申购费 %</label><input v-model.number="addForm.purchase_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 0.15" /></div>
            <div><label class="block text-sm mb-1">销售服务费 %/年</label><input v-model.number="addForm.sales_service_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="C类如 0.35" /></div>
          </div>
        </div>

        <div>
          <label class="block text-sm mb-1">赎回费规则（阶梯）</label>
          <div class="space-y-1.5">
            <div v-for="(r, i) in addForm.redeem_rules" :key="i" class="flex items-center gap-2">
              <span class="text-xs text-text-muted w-16 shrink-0">持有天数</span>
              <input v-model.number="r.days" type="number" min="1" class="w-24 px-2 py-1.5 text-sm border border-border-default rounded-md" placeholder="空=兜底" />
              <span class="text-xs text-text-muted">天以内</span>
              <input v-model.number="r.fee_rate" type="number" step="0.05" min="0" class="w-24 px-2 py-1.5 text-sm border border-border-default rounded-md" placeholder="费率%" />
              <span class="text-xs text-text-muted">%</span>
              <button v-if="addForm.redeem_rules.length > 1" @click="addForm.redeem_rules.splice(i, 1)" class="p-1 text-text-muted hover:text-expense-color"><Trash2 :size="13" /></button>
            </div>
          </div>
          <div class="flex items-center gap-2 mt-1.5">
            <button @click="addForm.redeem_rules.push({ days: null, fee_rate: 0 })" class="text-xs px-2 py-1 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1"><Plus :size="12" /> 加一档</button>
            <span class="text-xs text-text-muted">末档留空天数 = 兜底费率；预览：{{ addRulesPreview }}</span>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-3">
          <div><label class="block text-sm mb-1">起购金额（元）</label><input v-model.number="addForm.min_purchase" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 10" /></div>
          <div><label class="block text-sm mb-1">限额额度（元/日）</label><input v-model.number="addForm.purchase_limit" type="number" step="1000" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="限购时填，如 1000" /></div>
          <div><label class="block text-sm mb-1">赎回到账 T+N</label><input v-model.number="addForm.redeem_t_days" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 2" /></div>
          <div><label class="block text-sm mb-1">流动性备注</label><input v-model.trim="addForm.liquidity_note" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="额度/QDII时效等" /></div>
        </div>
        <div><label class="block text-sm mb-1">备注</label><input v-model.trim="addForm.notes" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="研究想法、关注理由等" /></div>
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
        <div class="grid grid-cols-4 gap-3">
          <div><label class="block text-sm mb-1">起购金额（元）</label><input v-model.number="poolForm.min_purchase" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如 10" /></div>
          <div><label class="block text-sm mb-1">限额额度（元/日）</label><input v-model.number="poolForm.purchase_limit" type="number" step="1000" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="限购时填" /></div>
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
        <div class="grid grid-cols-4 gap-3">
          <div><label class="block text-sm mb-1">起购金额（元）</label><input v-model.number="editForm.min_purchase" type="number" step="1" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">限额额度（元/日）</label><input v-model.number="editForm.purchase_limit" type="number" step="1000" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
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

    <!-- 天天基金批量导入 -->
    <BaseModal v-if="showImportModal" title="天天基金批量导入自选" width="max-w-2xl" @close="showImportModal = false">
      <div class="space-y-3">
        <div class="text-xs text-text-muted">粘贴基金代码（每行一个，也支持空格/逗号分隔）。自动拉取：名称、类型、申购状态、限额额度、费率，并按名称与类型自动打标。已存在的代码自动跳过。</div>
        <textarea v-model="importText" rows="6" class="w-full px-3 py-2 text-sm border border-border-default rounded-md font-mono" placeholder="000217&#10;006432&#10;161005"></textarea>
        <div v-if="importResults.length" class="max-h-60 overflow-y-auto border border-border-default rounded-md">
          <table class="w-full text-xs">
            <thead class="bg-bg-tertiary"><tr>
              <th class="px-2 py-1.5 text-left">代码</th><th class="px-2 py-1.5 text-left">名称</th>
              <th class="px-2 py-1.5 text-left">结果</th><th class="px-2 py-1.5 text-left">备注</th>
            </tr></thead>
            <tbody>
              <tr v-for="r in importResults" :key="r.symbol" class="border-t border-border-default">
                <td class="px-2 py-1 font-mono">{{ r.symbol }}</td>
                <td class="px-2 py-1">{{ r.name || '—' }}</td>
                <td class="px-2 py-1">
                  <span :class="['px-1.5 py-0.5 rounded', r.status === 'added' ? 'bg-income-bg text-income-color' : r.status === 'exists' ? 'bg-bg-tertiary text-text-secondary' : 'bg-expense-bg text-expense-color']">
                    {{ r.status === 'added' ? '已添加' : r.status === 'exists' ? '已存在' : '失败' }}
                  </span>
                </td>
                <td class="px-2 py-1 text-text-muted">{{ r.error || r.fund_type + (r.daily_limit != null ? ` · 限额${r.daily_limit}元` : '') }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <template #footer>
        <button @click="showImportModal = false" class="px-4 py-2 text-text-secondary">关闭</button>
        <button @click="importFromEm" :disabled="importing || !importSymbols.length" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover disabled:opacity-50">
          {{ importing ? `导入中（0/${importSymbols.length}）…` : `导入 ${importSymbols.length} 个标的` }}
        </button>
      </template>
    </BaseModal>

    <!-- 批量操作：作用于主列表勾选 -->
    <BaseModal v-if="showBatchModal" title="批量操作" width="max-w-2xl" @close="showBatchModal = false">
      <div class="space-y-3">
        <div class="flex items-center gap-2 text-sm">
          <span class="font-medium">已选 {{ selectedIds.size }} 只</span>
          <button @click="clearSelection" class="text-xs px-2 py-0.5 rounded border border-border-default text-text-secondary hover:bg-bg-tertiary">清空</button>
          <span v-if="batchBusy" class="ml-auto text-accent-primary">{{ batchMsg }}</span>
        </div>
        <div class="max-h-32 overflow-y-auto border border-border-default rounded-md p-2 flex flex-wrap gap-1.5">
          <span v-for="a in selectedAssets" :key="a.id" class="px-1.5 py-0.5 text-xs rounded bg-bg-tertiary">
            {{ a.symbol }} {{ a.name.length > 10 ? a.name.slice(0, 10) + '…' : a.name }}
          </span>
          <span v-if="selectedIds.size > selectedAssets.length" class="text-xs text-text-muted px-1 py-0.5">
            …等 {{ selectedIds.size }} 只
          </span>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <button @click="runBatchPool" :disabled="batchBusy || !selectedIds.size"
            class="px-4 py-2 rounded-md border border-border-default text-sm hover:bg-bg-tertiary disabled:opacity-40"
            title="入池前自动审查：暂停申购/限额<1000 直接拒绝；档案缺失先尝试更新，仍不完整拒绝">
            审查并入池
          </button>
          <button @click="runBatchRefresh" :disabled="batchBusy || !selectedIds.size"
            class="px-4 py-2 rounded-md bg-accent-primary text-white hover:bg-accent-hover disabled:opacity-40">
            更新档案（费率/限额/标签）
          </button>
          <button @click="runAuditPooled" :disabled="batchBusy"
            class="px-4 py-2 rounded-md border border-border-default text-sm hover:bg-bg-tertiary disabled:opacity-40"
            title="扫描全部已入池基金型标的：刷新档案后，暂停申购/限额<1000/档案仍不完整者自动退回自选">
            自动审查已入池
          </button>
          <button @click="batchRemoveSelected" :disabled="batchBusy || !selectedIds.size"
            class="px-4 py-2 rounded-md border border-border-default text-sm text-expense-color hover:bg-expense-bg disabled:opacity-40"
            title="仅自选标的可删除；已入池请先踢出">
            删除所选（仅自选）
          </button>
        </div>
        <div v-if="refreshSummary" class="text-xs text-text-muted whitespace-pre-line max-h-40 overflow-y-auto border-t border-border-default pt-2">{{ refreshSummary }}</div>

        <!-- 组合归组 -->
        <div class="border-t border-border-default pt-3 space-y-2">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium shrink-0">存为新组合</span>
            <input v-model="batchNewGroupName" placeholder="新组合名，如 全宽基指数" class="px-2 py-1.5 text-xs border border-border-default rounded-md flex-1" />
            <button @click="createGroupFromSelection" :disabled="batchBusy || !selectedIds.size || !batchNewGroupName.trim()"
              class="px-3 py-1.5 rounded-md bg-accent-primary text-white text-xs hover:bg-accent-hover disabled:opacity-40">创建</button>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium shrink-0">加入已有组合</span>
            <select v-model="batchGroupPick" class="px-2 py-1.5 text-xs border border-border-default rounded-md flex-1">
              <option value="">选择组合…</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.asset_ids.length }}）</option>
            </select>
            <button @click="addSelectedToGroup" :disabled="batchBusy || !selectedIds.size || !batchGroupPick"
              class="px-3 py-1.5 rounded-md bg-accent-primary text-white text-xs hover:bg-accent-hover disabled:opacity-40">加入</button>
          </div>
        </div>
      </div>
      <template #footer>
        <button @click="showBatchModal = false" class="px-4 py-2 text-text-secondary">关闭</button>
      </template>
    </BaseModal>

    <!-- 组合管理 -->
    <BaseModal v-if="showGroupsModal" title="组合管理" width="max-w-2xl" @close="showGroupsModal = false">
      <div class="space-y-3">
        <div class="text-xs text-text-muted">主列表勾选标的 → 「批量操作」→ 存为新组合 / 加入已有组合。此处管理组合本身。</div>
        <div class="flex items-center gap-2">
          <input v-model="newGroupName" placeholder="新组合名称" class="px-3 py-2 text-sm border border-border-default rounded-md flex-1"
                 @keyup.enter="submitNewGroup" />
          <input v-model="newGroupNote" placeholder="备注（可选）" class="px-3 py-2 text-sm border border-border-default rounded-md w-40"
                 @keyup.enter="submitNewGroup" />
          <button @click="submitNewGroup" :disabled="!newGroupName.trim()"
            class="px-4 py-2 text-sm rounded-md bg-accent-primary text-white hover:bg-accent-hover disabled:opacity-50 flex items-center gap-1"><Plus :size="14" /> 创建空组合</button>
        </div>
        <div class="flex items-start gap-2 border-t border-border-default pt-3">
          <div class="flex-1 space-y-1">
            <input v-model="codeGroupName" placeholder="按代码创建：组合名称" class="w-full px-3 py-2 text-sm border border-border-default rounded-md" />
            <textarea v-model="codeGroupSymbols" rows="2"
              placeholder="逗号/空格/换行分隔标的代码，如：000217, 006485, 023145&#10;（不存在的代码会被忽略并提示）"
              class="w-full px-3 py-2 text-sm border border-border-default rounded-md font-mono"></textarea>
          </div>
          <button @click="createGroupFromCodes" :disabled="!codeGroupName.trim() || !codeGroupSymbols.trim() || creatingFromCodes"
            class="px-4 py-2 text-sm rounded-md bg-accent-primary text-white hover:bg-accent-hover disabled:opacity-50 mt-0.5">
            {{ creatingFromCodes ? '创建中…' : '按代码创建' }}</button>
        </div>
        <div class="border border-border-default rounded-md divide-y divide-border-default max-h-80 overflow-y-auto">
          <div v-for="g in groups" :key="g.id" class="px-3 py-2">
            <div class="flex items-center gap-3">
              <button @click="viewGroupInList(g)" class="flex-1 min-w-0 text-left group">
                <div class="text-sm font-medium truncate group-hover:text-accent-primary">{{ g.name }}</div>
                <div class="text-xs text-text-muted">{{ g.asset_ids.length }} 个成员{{ g.note ? ` · ${g.note}` : '' }} · 点击在列表中查看</div>
              </button>
              <button @click="renameGroup(g)" class="p-1.5 text-text-secondary hover:text-accent-primary" title="重命名"><Edit2 :size="14" /></button>
              <button @click="removeGroup(g)" class="p-1.5 text-text-muted hover:text-expense-color" title="删除组合（不影响标的）"><Trash2 :size="14" /></button>
            </div>
            <div v-if="g.members?.length" class="mt-1 flex flex-wrap gap-1">
              <span v-for="m in g.members.slice(0, 12)" :key="m.id" class="px-1.5 py-0.5 text-xs rounded bg-bg-tertiary text-text-secondary">
                {{ m.symbol }} {{ m.name.length > 8 ? m.name.slice(0, 8) + '…' : m.name }}
              </span>
              <span v-if="g.members.length > 12" class="text-xs text-text-muted px-1 py-0.5">…等 {{ g.members.length }} 只</span>
            </div>
          </div>
          <div v-if="!groups.length" class="px-3 py-8 text-center text-sm text-text-muted">还没有组合</div>
        </div>
      </div>
      <template #footer>
        <button @click="showGroupsModal = false" class="px-4 py-2 text-text-secondary">关闭</button>
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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Plus, RefreshCw, Search, X, Eye, PackagePlus, PackageMinus, Trash2, Edit2, ChevronUp, ChevronDown, ChevronsUpDown, Sparkles, Download, ListChecks, FolderOpen } from 'lucide-vue-next'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import { useApi } from '@/composables/useApi'
import { apiLong } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import AssetStatsTab from './AssetStatsTab.vue'
import type { ResearchAsset, ResearchPricePoint, SyncResult, AssetPriceStatus, ResearchGroup } from '@/types'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const api = useApi()
const { show } = useToast()

const TYPE_LABELS: Record<string, string> = { fund: '基金', stock: '股票', index: '指数', gold: '黄金', other: '其他' }
const EXCHANGE_LABELS: Record<string, string> = { SH: '沪市', SZ: '深市', FUND_CN: '场外基金', US: '美股', HK: '港股' }

interface AssetRow extends ResearchAsset { _syncing?: boolean }

const assets = ref<AssetRow[]>([])
const activeTab = ref<'watchlist' | 'pooled' | 'stats' | 'hot'>('watchlist')
const search = ref('')
const categoryFilter = ref('')
const kindFilter = ref('')
const classFilter = ref('')
const regionFilter = ref('')
const themeTagFilter = ref('')
const limitFilter = ref<'limited' | 'unlimited' | ''>('')
const groupFilter = ref('')
const selectedIds = ref<Set<string>>(new Set())
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const pages = ref(1)
const loading = ref(false)
const statsById = ref<Record<string, any>>({})
const serverSort = ref('')
const serverOrder = ref<'asc' | 'desc'>('desc')
const refreshing = ref(false)

const watchCount = ref(0)
const pooledCount = ref(0)

async function loadCounts() {
  try {
    const w = await api.get('/research/assets', { params: { page: 1, page_size: 1, status: 'watchlist' } })
    const p = await api.get('/research/assets', { params: { page: 1, page_size: 1, status: 'pooled' } })
    watchCount.value = (w.data as { total: number }).total
    pooledCount.value = (p.data as { total: number }).total
  } catch { /* 计数失败不打扰 */ }
}

// 每日首次打开自动入池体检：刷新档案→硬违规/档案缺失踢回自选，toast 汇总

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch([activeTab, categoryFilter, kindFilter, classFilter, regionFilter, limitFilter, groupFilter], () => {
  page.value = 1
  load()
})
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; load() }, 300)
})
watch([page, pageSize], () => { load() })
const categories = computed(() => [...new Set(assets.value.map(a => a.category).filter(Boolean))] as string[])
const kindOptions = computed(() => [...new Set(assets.value.map(a => a.fund_kind).filter(Boolean))] as string[])
const classOptions = computed(() => [...new Set(assets.value.map(a => a.asset_class).filter(Boolean))] as string[])
const regionOptions = computed(() => [...new Set(assets.value.map(a => a.region).filter(Boolean))] as string[])

// 分页器可见页码（最多显示 7 个：首尾各 1 + 当前附近 3）
const visiblePages = computed((): (number | '...')[] => {
  const pagesCount = pages.value
  const cur = page.value
  if (pagesCount <= 7) return Array.from({ length: pagesCount }, (_, i) => i + 1)
  const res: (number | '...')[] = [1]
  if (cur > 3) res.push('...')
  for (let i = Math.max(2, cur - 1); i <= Math.min(pagesCount - 1, cur + 1); i++) res.push(i)
  if (cur < pagesCount - 2) res.push('...')
  res.push(pagesCount)
  return res
})

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

// 服务端已按 tab+筛选+分页返回当前页；此处仅做页内排序与主题标签页内过滤
const filteredAssets = computed(() => {
  const list = assets.value.filter(a =>
    !(themeTagFilter.value && !(a.auto_tags || []).includes(themeTagFilter.value)))
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
function limitText(v: number | null | undefined): string {
  if (v == null) return '不限'
  return v >= 10000 ? `${(v / 10000).toFixed(v % 10000 === 0 ? 0 : 1)}万` : `${v}`
}
function limitShort(v: number | null | undefined): string {
  if (v == null || v >= 100000) return ''   // ≥10万 ≈ 不限，不标
  return v >= 10000 ? `限${(v / 10000).toFixed(v % 10000 === 0 ? 0 : 1)}万` : `限${+v.toFixed(2)}`
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
    const params: Record<string, unknown> = {
      page: page.value, page_size: pageSize.value, status: activeTab.value,
      with_stats: 1,
    }
    if (serverSort.value) {
      params.sort_by = serverSort.value
      params.order = serverOrder.value
    }
    if (categoryFilter.value) params.category = categoryFilter.value
    if (kindFilter.value) params.fund_kind = kindFilter.value
    if (classFilter.value) params.asset_class = classFilter.value
    if (regionFilter.value) params.region = regionFilter.value
    if (limitFilter.value) params.limit_filter = limitFilter.value
    if (groupFilter.value) params.group_id = groupFilter.value
    if (search.value.trim()) params.search = search.value.trim()
    const res = await api.get('/research/assets', { params })
    const env = res.data as { items: ResearchAsset[]; total: number; pages: number; stats?: Record<string, any> }
    statsById.value = env.stats || {}
    assets.value = env.items as AssetRow[]
    total.value = env.total
    pages.value = env.pages
  } catch (e) {
    show(errDetail(e), 'error')
    assets.value = []
  } finally {
    loading.value = false
    loadCounts()
  }
}

const showAddModal = ref(false)
const adding = ref(false)
interface AddForm {
  symbol: string; exchange: string; asset_type: string; category: string; name: string; notes: string;
  mgmt_fee: number | null; custody_fee: number | null; purchase_fee: number | null; sales_service_fee: number | null;
  redeem_rules: RedeemRuleForm[]; min_purchase: number | null; purchase_limit: number | null;
  redeem_t_days: number | null; liquidity_note: string
}
function emptyAddForm(): AddForm {
  return {
    symbol: '', exchange: 'FUND_CN', asset_type: 'fund', category: '', name: '', notes: '',
    mgmt_fee: null, custody_fee: null, purchase_fee: null, sales_service_fee: null,
    redeem_rules: [{ days: 7, fee_rate: 1.5 }, { days: 30, fee_rate: 0.5 }, { days: null, fee_rate: 0 }],
    min_purchase: null, purchase_limit: null, redeem_t_days: null, liquidity_note: '',
  }
}
// RedeemRuleForm 在下方 poolForm 区域定义（类型提升不适用于 const）——前置声明见 interface
const addForm = ref<AddForm>(emptyAddForm())
const addRulesPreview = computed(() => addForm.value.redeem_rules.map(r => r.days == null ? `其余 ${r.fee_rate}%` : `<${r.days}天 ${r.fee_rate}%`).join('，'))

function openAddModal() {
  addForm.value = emptyAddForm()
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

// ---- 天天基金批量导入 ----
const showImportModal = ref(false)
const importing = ref(false)
const importText = ref('')
const importResults = ref<{ symbol: string; name: string; status: string; fund_type: string; daily_limit: number | null; error: string | null }[]>([])
const importSymbols = computed(() =>
  [...new Set(importText.value.split(/[\s,，;；]+/).map(s => s.trim()).filter(s => /^\d{6}$/.test(s)))]
)

async function importFromEm() {
  importing.value = true
  try {
    const { data } = await api.post('/research/assets/import-from-em', { symbols: importSymbols.value })
    importResults.value = data
    const added = data.filter((r: any) => r.status === 'added').length
    const failed = data.filter((r: any) => r.status === 'failed').length
    show(`导入完成：新增 ${added}，已存在 ${data.length - added - failed}，失败 ${failed}`, added > 0 ? 'success' : 'info')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    importing.value = false
  }
}

// ---- 批量操作（作用于主列表勾选的 selectedIds） ----
const showBatchModal = ref(false)
const batchBusy = ref(false)
const batchMsg = ref('')
const refreshSummary = ref('')

// ---- 标的组合：自定义命名池，后续策略可按组合圈定 universe ----
const groups = ref<ResearchGroup[]>([])
const showGroupsModal = ref(false)
const newGroupName = ref('')
const newGroupNote = ref('')
const codeGroupName = ref('')
const codeGroupSymbols = ref('')
const creatingFromCodes = ref(false)

async function createGroupFromCodes() {
  const name = codeGroupName.value.trim()
  const raw = codeGroupSymbols.value.trim()
  if (!name || !raw) return
  const syms = [...new Set(raw.split(/[\s,，;；]+/).map(s => s.trim()).filter(Boolean))]
  if (!syms.length) return
  creatingFromCodes.value = true
  try {
    // 当前列表（分页内）可能不含全部代码——用 ids 全集端点按代码精确解析
    const res = await api.get('/research/assets/ids', { params: { search: '' } })
    const all = res.data.items as { id: string; symbol: string; name: string }[]
    const bySym = new Map(all.map(a => [a.symbol, a]))
    const found: string[] = []
    const missing: string[] = []
    for (const s of syms) {
      const a = bySym.get(s)
      if (a) found.push(a.id); else missing.push(s)
    }
    if (!found.length) {
      show(`没有任何代码匹配到标的（缺失：${syms.slice(0, 5).join('、')}${syms.length > 5 ? '…' : ''}）`, 'error')
      return
    }
    const r = await api.post('/research/assets/groups', { name, note: `按代码创建 ${found.length} 只`, asset_ids: found })
    await loadGroups()
    show(`组合「${(r.data as ResearchGroup).name}」已创建（${found.length} 只${missing.length ? `，忽略未匹配 ${missing.length} 个代码` : ''}）`, 'success')
    codeGroupName.value = ''
    codeGroupSymbols.value = ''
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    creatingFromCodes.value = false
  }
}
const batchGroupPick = ref('')
const batchNewGroupName = ref('')

async function loadGroups() {
  try {
    const r = await api.get('/research/assets/groups')
    groups.value = r.data as ResearchGroup[]
  } catch { groups.value = [] }
}

function openGroupsModal() {
  loadGroups()
  showGroupsModal.value = true
}

async function createGroup(name: string, note = '', assetIds: string[] = []): Promise<ResearchGroup | null> {
  try {
    const r = await api.post('/research/assets/groups', { name: name.trim(), note, asset_ids: assetIds })
    await loadGroups()
    show(`已创建组合「${(r.data as ResearchGroup).name}」`, 'success')
    return r.data as ResearchGroup
  } catch (e) {
    show(errDetail(e), 'error')
    return null
  }
}

async function submitNewGroup() {
  const name = newGroupName.value.trim()
  if (!name) { show('组合名称不能为空', 'error'); return }
  const g = await createGroup(name, newGroupNote.value.trim())
  if (g) { newGroupName.value = ''; newGroupNote.value = '' }
}

async function renameGroup(g: ResearchGroup) {
  const name = window.prompt('重命名组合', g.name)?.trim()
  if (!name || name === g.name) return
  try {
    await api.put(`/research/assets/groups/${g.id}`, { name })
    await loadGroups()
  } catch (e) { show(errDetail(e), 'error') }
}

async function removeGroup(g: ResearchGroup) {
  if (!window.confirm(`删除组合「${g.name}」？（${g.asset_ids.length} 个成员，不影响标的本身）`)) return
  try {
    await api.delete(`/research/assets/groups/${g.id}`)
    await loadGroups()
  } catch (e) { show(errDetail(e), 'error') }
}

async function addSelectedToGroup() {
  const ids = [...selectedIds.value]
  if (!ids.length) { show('先在列表中勾选标的', 'error'); return }
  const g = groups.value.find(x => x.id === batchGroupPick.value)
  if (!g) { show('选择目标组合', 'error'); return }
  try {
    const merged = Array.from(new Set([...g.asset_ids, ...ids]))
    const r = await api.put(`/research/assets/groups/${g.id}`, { asset_ids: merged })
    const ng = r.data as ResearchGroup
    show(`已加入组合「${ng.name}」（共 ${(ng.asset_ids || []).length} 个成员）`, 'success')
    batchGroupPick.value = ''
    await loadGroups()
  } catch (e) { show(errDetail(e), 'error') }
}

async function createGroupFromSelection() {
  const ids = [...selectedIds.value]
  const name = batchNewGroupName.value.trim()
  if (!ids.length || !name) return
  const g = await createGroup(name, '', ids)
  if (g) batchNewGroupName.value = ''
}

const selectedAssets = computed(() =>
  assets.value.filter(a => selectedIds.value.has(a.id)))

function viewGroupInList(g: ResearchGroup) {
  groupFilter.value = g.id
  showGroupsModal.value = false
}

async function batchRemoveSelected() {
  const targets = assets.value.filter(a => selectedIds.value.has(a.id) && a.status === 'watchlist')
  if (!targets.length) { show('所选均为入池标的——请先踢出入池再删除', 'error'); return }
  if (!window.confirm(`删除 ${targets.length} 个自选标的及其历史净值？入池标的不会被删除。`)) return
  batchBusy.value = true
  batchMsg.value = '删除中…'
  let ok = 0
  try {
    for (const t of targets) {
      try { await api.delete(`/research/assets/${t.id}`); ok++ } catch { /* 单只失败继续 */ }
    }
    show(`已删除 ${ok}/${targets.length} 只`, ok === targets.length ? 'success' : 'warning')
    clearSelection()
    await load()
  } finally {
    batchBusy.value = false
  }
}

function openBatchModal() {
  if (!selectedIds.value.size) { show('先在列表中勾选标的', 'error'); return }
  refreshSummary.value = ''
  showBatchModal.value = true
}
function toggleSelect(id: string) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selectedIds.value = s
}
const pageAllChecked = computed(() =>
  filteredAssets.value.length > 0 && filteredAssets.value.every(a => selectedIds.value.has(a.id)))

async function selectAllFiltered() {
  try {
    const params: Record<string, unknown> = {}
    if (activeTab.value !== 'stats') params.status = activeTab.value
    if (categoryFilter.value) params.category = categoryFilter.value
    if (kindFilter.value) params.fund_kind = kindFilter.value
    if (classFilter.value) params.asset_class = classFilter.value
    if (regionFilter.value) params.region = regionFilter.value
    if (limitFilter.value) params.limit_filter = limitFilter.value
    if (groupFilter.value) params.group_id = groupFilter.value
    if (search.value.trim()) params.search = search.value.trim()
    const res = await api.get('/research/assets/ids', { params })
    const items = (res.data as { items: { id: string }[] }).items
    selectedIds.value = new Set(items.map(i => i.id))
    show(`已选中筛选结果全部 ${items.length} 只`, 'success')
  } catch (e) {
    show(errDetail(e), 'error')
  }
}

function clearSelection() {
  selectedIds.value = new Set()
}

function toggleAllPage() {
  if (pageAllChecked.value) {
    const s = new Set(selectedIds.value)
    filteredAssets.value.forEach(a => s.delete(a.id))
    selectedIds.value = s
  } else {
    const s = new Set(selectedIds.value)
    filteredAssets.value.forEach(a => s.add(a.id))
    selectedIds.value = s
  }
}

async function runBatchPool() {
  const ids = [...selectedIds.value]
  if (!ids.length || !confirm(`将所选 ${ids.length} 个标的入池（自动审查：暂停申购/限额过低/档案缺失者会被拒绝并保留自选）？`)) return
  batchBusy.value = true
  const CHUNK = 6
  const pooled: ResearchAsset[] = []
  const rej: string[] = []
  try {
    for (let i = 0; i < ids.length; i += CHUNK) {
      const chunk = ids.slice(i, i + CHUNK)
      batchMsg.value = `审查并入池 ${Math.min(i + CHUNK, ids.length)}/${ids.length}…`
      const { data } = await api.post('/research/assets/batch-pool',
        { ids: chunk, apply_defaults: true, skip_holdings: true }, { timeout: 120000 })
      pooled.push(...(data.pooled ?? []))
      rej.push(...(data.rejected || []).map((r: { name: string; symbol: string; reasons: string[] }) => `${r.symbol} ${r.name}: ${r.reasons.join('、')}`))
    }
    refreshSummary.value = rej.length ? `已拒绝 ${rej.length} 个：\n` + rej.join('\n') : '全部通过审查并入池'
    show(`入池完成：${pooled.length} 成功，${rej.length} 被拒绝`, pooled.length > 0 ? 'success' : 'info')
    clearSelection()
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    batchBusy.value = false
    batchMsg.value = ''
  }
}

async function runAuditPooled() {
  if (!confirm('扫描全部已入池基金型标的：刷新档案，暂停申购 / 限额<1000 / 档案仍不完整者自动退回自选。继续？')) return
  batchBusy.value = true
  batchMsg.value = '审查中…'
  try {
    const { data } = await api.post('/research/assets/batch-audit-pooled')
    const demoted: string[] = []
    let kept = 0, failed = 0
    for (const r of data as { symbol: string; name: string; status: string; reasons?: string[]; error?: string; refreshed_fields?: string[] }[]) {
      if (r.status === 'demoted') demoted.push(`${r.symbol} ${r.name}: ${(r.reasons || []).join('、')}`)
      else if (r.status === 'failed') failed++
      else kept++
    }
    refreshSummary.value = `审查完成：保留 ${kept} · 退回自选 ${demoted.length}${failed ? ` · 失败 ${failed}` : ''}`
      + (demoted.length ? '\n退回明细：\n' + demoted.join('\n') : '')
    show(`审查完成：退回自选 ${demoted.length} 个`, 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    batchBusy.value = false
    batchMsg.value = ''
  }
}

async function runBatchRefresh() {
  const ids = [...selectedIds.value]
  if (!ids.length) return
  batchBusy.value = true
  const CHUNK = 8
  const all: { symbol: string; name: string; status: string; changed_fields?: string[]; error?: string | null }[] = []
  try {
    for (let i = 0; i < ids.length; i += CHUNK) {
      const chunk = ids.slice(i, i + CHUNK)
      batchMsg.value = `更新中 ${Math.min(i + CHUNK, ids.length)}/${ids.length}…`
      const { data } = await api.post('/research/assets/batch-refresh-profiles',
        { ids: chunk, skip_holdings: true }, { timeout: 120000 })
      all.push(...data)
    }
    const updated = all.filter((r) => r.status !== 'failed' && r.status !== 'skipped').length
    refreshSummary.value = all.map((r) =>
      `${r.symbol} ${r.name}: ${r.status}${r.changed_fields?.length ? ' → ' + r.changed_fields.join('/') : ''}${r.error ? ' → ' + r.error : ''}`
    ).join('\n')
    show(`档案更新完成：${updated}/${ids.length} 只有变更`, 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  } finally {
    batchBusy.value = false
    batchMsg.value = ''
  }
}

const poolTarget = ref<ResearchAsset | null>(null)
const pooling = ref(false)
interface RedeemRuleForm { days: number | null; fee_rate: number }
const poolForm = ref<{
  mgmt_fee: number | null; custody_fee: number | null; purchase_fee: number | null;
  sales_service_fee: number | null; redeem_rules: RedeemRuleForm[]; redeem_fee_note: string;
  min_purchase: number | null; purchase_limit: number | null;
  redeem_t_days: number | null; liquidity_note: string; data_quality: string;
}>({
  mgmt_fee: null, custody_fee: null, purchase_fee: null, sales_service_fee: null,
  redeem_rules: [{ days: 7, fee_rate: 1.5 }, { days: 30, fee_rate: 0.5 }, { days: null, fee_rate: 0 }],
  redeem_fee_note: '', min_purchase: null, purchase_limit: null,
  redeem_t_days: null, liquidity_note: '', data_quality: '',
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
    // 自选阶段已存（手动填或天天基金导入）的费率限额直接带入，可改
    mgmt_fee: a.mgmt_fee ?? null,
    custody_fee: a.custody_fee ?? null,
    purchase_fee: a.purchase_fee ?? null,
    sales_service_fee: a.sales_service_fee ?? null,
    redeem_rules: (a.redeem_rules?.length ? a.redeem_rules : [{ days: 7, fee_rate: 1.5 }, { days: 30, fee_rate: 0.5 }, { days: null, fee_rate: 0 }])
      .map(r => ({ days: r.days ?? null, fee_rate: r.fee_rate })),
    redeem_fee_note: '',
    min_purchase: a.min_purchase ?? null,
    purchase_limit: a.purchase_limit ?? null,
    redeem_t_days: a.redeem_t_days ?? null,
    liquidity_note: a.liquidity_note || '', data_quality: '',
  }
}

// ---- edit modal (pooled assets) ----
const editTarget = ref<ResearchAsset | null>(null)
const editing = ref(false)
const editForm = ref<{
  name: string; category: string; mgmt_fee: number | null; custody_fee: number | null;
  purchase_fee: number | null; sales_service_fee: number | null; redeem_rules: RedeemRuleForm[];
  min_purchase: number | null; purchase_limit: number | null;
  redeem_t_days: number | null; liquidity_note: string; data_quality: string;
}>({
  name: '', category: '', mgmt_fee: null, custody_fee: null, purchase_fee: null, sales_service_fee: null,
  redeem_rules: [], min_purchase: null, purchase_limit: null,
  redeem_t_days: null, liquidity_note: '', data_quality: '',
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
    min_purchase: a.min_purchase ?? null, purchase_limit: a.purchase_limit ?? null,
    redeem_t_days: a.redeem_t_days ?? null,
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
      purchase_limit: editForm.value.purchase_limit,
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

async function unpoolOne(a: AssetRow) {
  if (!window.confirm(`将「${a.name}」踢出入池？\n状态退回自选，历史净值与档案数据全部保留。`)) return
  try {
    await api.post(`/research/assets/${a.id}/unpool`)
    show(`已踢出入池：${a.name}`, 'success')
    await load()
  } catch (e) {
    show(errDetail(e), 'error')
  }
}

function isStaleNav(a: ResearchAsset): boolean {
  const ind = a.indicators
  return !!ind.points && ind.points >= 60
    && (ind.ann_volatility ?? 0) === 0
    && (Math.abs(ind.ret_1y ?? 0) < 1e-9)
}

async function syncOne(a: AssetRow) {
  a._syncing = true
  try {
    // 场外基金：净值 + 档案（费率/T+N/限购，来自天天基金）并行刷新
    const isFund = a.exchange === 'FUND_CN' && a.asset_type === 'fund'
    const [priceRes, profRes] = await Promise.all([
      api.post(`/research/assets/${a.id}/sync`),
      isFund
        ? apiLong.post('/research/assets/batch-refresh-profiles', { ids: [a.id] }).catch(() => null)
        : Promise.resolve(null),
    ])
    const r = priceRes.data as SyncResult
    let msg = `同步成功：${r.rows} 行（${r.begin} ~ ${r.end}，${r.source}）`
    if (profRes) {
      const pr = (profRes.data as { changed_fields?: string[]; status: string }[])[0]
      if (pr?.status === 'updated' && pr.changed_fields?.length) msg += ` · 档案已更新 ${pr.changed_fields.length} 项`
      else if (pr?.status === 'failed') msg += ' · 档案刷新失败'
      else msg += ' · 档案无变化'
    }
    show(msg, profRes && (profRes.data as { status: string }[])[0]?.status === 'failed' ? 'warning' : 'success')
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
    // 行情 + 档案（费率/限购/申购状态，跳过持仓抓取提速）并行
    const [pricesRes, profRes] = await Promise.all([
      api.post('/research/assets/refresh-prices'),
      apiLong.post('/research/assets/batch-refresh-profiles', { skip_holdings: true }).catch(() => null),
    ])
    const results = pricesRes.data as SyncResult[]
    const ok = results.filter(r => !r.error)
    const fail = results.filter(r => r.error)
    let msg = `刷新完成：行情成功 ${ok.length}（共 ${ok.reduce((s, r) => s + r.rows, 0)} 行）${fail.length ? ` / 失败 ${fail.length}` : ''}`
    if (profRes) {
      const prs = profRes.data as { status: string }[]
      const updated = prs.filter(r => r.status === 'updated').length
      const pfail = prs.filter(r => r.status === 'failed').length
      msg += ` · 档案更新 ${updated}${pfail ? ` / 失败 ${pfail}` : ''}`
    }
    show(msg, fail.length ? 'warning' : 'success')
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

onMounted(() => { load(); loadGroups(); loadCounts() })
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>
