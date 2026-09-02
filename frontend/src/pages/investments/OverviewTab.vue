<template>
  <div>
<!-- Toolbar -->
    <div class="flex items-center justify-end gap-2 mb-4 flex-wrap">
      <button :disabled="refreshingAll || !activeInvestments.length" @click="refreshAllPrices"
        :class="['px-3 py-2 border border-border-default rounded-md flex items-center gap-1 text-sm', refreshingAll || !activeInvestments.length ? 'text-text-muted' : 'text-text-secondary hover:bg-bg-tertiary']">
        <RefreshCw v-if="!refreshingAll" :size="14" />
        <span>{{ refreshingAll ? '刷新中…' : '刷新所有现价' }}</span>
      </button>
      <button @click="openFlowModal()" class="px-3 py-2 border border-border-default rounded-md text-sm text-text-secondary hover:bg-bg-tertiary flex items-center gap-1">
        <Plus :size="14" /> 记入金/出金
      </button>
      <button @click="syncFromBookkeeping" :disabled="syncingFlows"
        :class="['px-3 py-2 border border-border-default rounded-md text-sm flex items-center gap-1', syncingFlows ? 'text-text-muted' : 'text-text-secondary hover:bg-bg-tertiary']">
        <RefreshCw :size="14" /> {{ syncingFlows ? '同步中…' : '从记账同步' }}
      </button>
      <button @click="syncPnlToBookkeeping" :disabled="syncingPnl"
        :class="['px-3 py-2 border border-border-default rounded-md text-sm flex items-center gap-1', syncingPnl ? 'text-text-muted' : 'text-text-secondary hover:bg-bg-tertiary']">
        <RefreshCw :size="14" /> {{ syncingPnl ? '同步中…' : '同步盈亏到记账' }}
      </button>
      <button @click="openProductModal()" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover flex items-center gap-1">
        <Plus :size="16" /> 添加投资
      </button>
    </div>

    <!-- Portfolio summary cards -->
    <div class="bg-white rounded-lg shadow-sm p-4 mb-4">
      <h3 class="font-semibold text-sm mb-3">组合总览</h3>
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-3 text-sm">
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">本金（当前持仓成本）</div>
          <div class="font-semibold text-base">{{ sym }}{{ fmt(overview?.principal ?? 0) }}</div>
          <div class="text-xs text-text-muted mt-0.5">入 {{ sym }}{{ fmt(overview?.total_deposits ?? 0) }} / 出 {{ sym }}{{ fmt(overview?.total_withdrawals ?? 0) }}</div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">当前市值</div>
          <div class="font-semibold text-base">{{ sym }}{{ fmt(overview?.current_market_value ?? 0) }}</div>
          <div class="text-xs text-text-muted mt-0.5">未投资现金（推算）{{ sym }}{{ fmt(overview?.idle_cash ?? 0) }}</div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">已落袋盈亏（含分红）</div>
          <div class="font-semibold text-base" :class="colorClass((overview?.realized_pnl ?? 0) + (overview?.dividend_total ?? 0))">{{ signed((overview?.realized_pnl ?? 0) + (overview?.dividend_total ?? 0)) }}</div>
          <div class="text-xs text-text-muted mt-0.5">已平仓 {{ signed(overview?.realized_pnl ?? 0) }} · 其中分红 {{ signed(overview?.dividend_total ?? 0) }}</div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">当前浮盈浮亏</div>
          <div class="font-semibold text-base" :class="colorClass(overview?.floating_pnl ?? 0)">{{ signed(overview?.floating_pnl ?? 0) }}</div>
          <div class="text-xs text-text-muted mt-0.5">未平仓产品的市值 − 持仓成本</div>
        </div>
        <div class="p-2 rounded-md bg-bg-secondary">
          <div class="text-xs text-text-muted">整体年化 XIRR</div>
          <div class="font-semibold text-base" :class="colorClassNullable(overview?.xirr_annualized)">{{ xirrLabel(overview?.xirr_annualized) }}</div>
          <div class="text-xs text-text-muted mt-0.5">{{ overview?.days_held ? `持有 ${overview.days_held} 天` : '暂无入金记录' }}</div>
        </div>
      </div>
    </div>

<!-- Health Panel -->
    <HealthPanel />

    <!-- Holdings Table -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden mb-4">
      <div class="p-4 border-b border-border-default flex items-center justify-between">
        <h3 class="font-semibold text-sm">当前持仓 ({{ activeInvestments.length }})</h3>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">名称 / 代码</th>
            <th class="px-3 py-2 font-medium text-right">份额</th>
            <th class="px-3 py-2 font-medium text-right">摊薄单价</th>
            <th class="px-3 py-2 font-medium text-right">现价/净值</th>
            <th class="px-3 py-2 font-medium text-right">距成本</th>
            <th class="px-3 py-2 font-medium text-right">市值</th>
            <th class="px-3 py-2 font-medium text-right">盈亏</th>
            <th class="px-3 py-2 font-medium text-right">年化波动</th>
            <th class="px-3 py-2 font-medium text-right">夏普</th>
            <th class="px-3 py-2 font-medium text-right">年化 XIRR</th>
            <th class="px-3 py-2 font-medium text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="inv in activeInvestments" :key="inv.id">
            <tr class="border-t border-border-default hover:bg-bg-secondary cursor-pointer" :title="expandedIds.has(inv.id) ? '点击收起流水' : '点击展开流水'" @click="onRowClick(inv)">
              <td class="px-3 py-2" @click.stop>
                <div class="font-medium cursor-pointer hover:text-accent-primary" @click="openDetail(inv)" title="查看净值曲线与买卖点">{{ inv.name }}</div>
                <div class="text-xs text-text-muted">
                  {{ TYPE_LABELS[inv.investment_type] || inv.investment_type }}
                  <span v-if="inv.symbol"> · {{ inv.exchange }} {{ inv.symbol }}</span>
                  <span v-if="inv.last_price_update"> · 更新于 {{ formatDateShort(inv.last_price_update) }}</span>
                </div>
              </td>
              <td class="px-3 py-2 text-right">{{ priceFmt(inv, inv.quantity) }}</td>
              <td class="px-3 py-2 text-right" title="摊薄单价 =（累计买入 + 累计费用 − 卖出回款）÷ 当前份额">{{ sym }}{{ priceFmt(inv, inv.purchase_price) }}</td>
              <td class="px-3 py-2 text-right" :title="inv.is_money_market ? '货币基金：七日年化收益率（净值恒为 1.0）' : ''">{{ inv.is_money_market ? (inv.seven_day_yield != null ? inv.seven_day_yield.toFixed(2) + '%' : '—') : sym + priceFmt(inv, inv.current_price) }}</td>
              <td class="px-3 py-2 text-right font-medium" :class="costDist(inv) >= 0 ? 'text-income-color' : 'text-expense-color'">{{ costDist(inv) >= 0 ? '+' : '' }}{{ costDist(inv).toFixed(1) }}%</td>
              <td class="px-3 py-2 text-right font-medium">{{ sym }}{{ fmt(inv.total_value) }}</td>
              <td class="px-3 py-2 text-right font-medium" :class="colorClass(inv.profit_loss)">{{ signed(inv.profit_loss) }}</td>
              <td class="px-3 py-2 text-right" :title="`净值序列年化波动率（${inv.symbol || '—'}）`">{{ inv.ann_volatility != null ? (inv.ann_volatility * 100).toFixed(2) + '%' : '—' }}</td>
              <td class="px-3 py-2 text-right" :title="`净值序列夏普比率（无风险利率 2%）`">{{ inv.sharpe_ratio != null ? inv.sharpe_ratio.toFixed(2) : '—' }}</td>
              <td class="px-3 py-2 text-right" :class="colorClassNullable(productMetricMap[inv.id]?.xirr_annualized)">{{ xirrLabel(productMetricMap[inv.id]?.xirr_annualized) }}</td>
              <td class="px-3 py-2 text-center whitespace-nowrap" @click.stop>
                <div class="flex items-center justify-center gap-2">
                  <button @click="openDetail(inv)" title="净值曲线、指标与买卖点" class="text-text-secondary hover:text-accent-primary"><LineChart :size="14" /></button>
                  <button @click="onRowClick(inv)" :title="expandedIds.has(inv.id) ? '收起流水' : '展开流水'" class="text-text-secondary hover:text-accent-primary"><ListPlus :size="14" /></button>
                  <button :disabled="refreshingId === inv.id" @click="refreshPrice(inv)" :title="supportsAutoRefresh(inv.exchange) ? '刷新现价' : '该市场不支持自动刷新，请手动编辑'"
                    :class="supportsAutoRefresh(inv.exchange) ? 'text-accent-primary hover:text-accent-hover' : 'text-text-muted cursor-not-allowed'">
                    <RefreshCw :size="14" />
                  </button>
                  <button @click="openProductModal(inv)" title="编辑" class="text-text-secondary hover:text-accent-primary"><Edit2 :size="14" /></button>
                  <button @click="removeItem(inv.id)" title="删除" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
                </div>
              </td>
            </tr>
            <tr v-if="expandedIds.has(inv.id)" class="bg-bg-secondary">
              <td colspan="11" class="px-4 py-3">
                <div class="flex items-center justify-between mb-2">
                  <div class="text-xs font-medium text-text-secondary">流水记录（{{ txMap[inv.id]?.length || 0 }} 条）</div>
                  <button @click="openTxModal(inv)" class="px-2 py-1 text-xs rounded border border-border-default text-text-secondary hover:bg-bg-tertiary flex items-center gap-1">
                    <Plus :size="12" /> 添加流水
                  </button>
                </div>
                <table class="w-full text-xs">
                  <thead><tr class="text-text-muted"><th class="px-2 py-1 text-left">日期</th><th class="px-2 py-1 text-left">类型</th><th class="px-2 py-1 text-right">数量</th><th class="px-2 py-1 text-right">单价</th><th class="px-2 py-1 text-right">金额</th><th class="px-2 py-1 text-right">费用</th><th class="px-2 py-1 text-left">备注</th></tr></thead>
                  <tbody>
                    <tr v-for="tx in txMap[inv.id] || []" :key="tx.id" class="border-t border-border-default cursor-pointer hover:bg-bg-tertiary" @click="openTxModal(inv, tx)">
                      <td class="px-2 py-1">{{ tx.event_date }}</td>
                      <td class="px-2 py-1">{{ TX_LABELS[tx.event_type] }}</td>
                      <td class="px-2 py-1 text-right">{{ tx.quantity || '—' }}</td>
                      <td class="px-2 py-1 text-right">{{ sym }}{{ fmt(tx.unit_price) }}</td>
                      <td class="px-2 py-1 text-right">{{ signed(tx.amount) }}</td>
                      <td class="px-2 py-1 text-right">{{ tx.fee ? sym + fmt(tx.fee) : '—' }}</td>
                      <td class="px-2 py-1 text-text-muted">{{ tx.notes }}</td>
                    </tr>
                    <tr v-if="!txMap[inv.id]?.length"><td colspan="7" class="px-2 py-2 text-text-muted text-center">暂无流水（点击行可添加）</td></tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
          <tr v-if="!activeInvestments.length"><td colspan="11" class="px-4 py-6 text-center text-text-muted">暂无持仓</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Sold positions: realized P&L + annualized return per fully-closed product -->
    <div v-if="store.closedPositions && store.closedPositions.positions.length" class="bg-white rounded-lg shadow-sm overflow-hidden mb-4">
      <div class="p-4 border-b border-border-default">
        <h3 class="font-semibold text-sm">已平仓 ({{ store.closedPositions.count }})</h3>
        <div class="text-xs text-text-muted mt-0.5">实现盈亏 = 回款(卖出+分红) − 成本(买入+费用)；年化 = (1+收益率)^(365/持有天数)−1</div>
      </div>
      <table class="w-full text-sm">
        <thead class="bg-bg-tertiary text-left">
          <tr>
            <th class="px-3 py-2 font-medium">名称</th>
            <th class="px-3 py-2 font-medium text-right">买入金额</th>
            <th class="px-3 py-2 font-medium text-right">回款</th>
            <th class="px-3 py-2 font-medium text-right">费用</th>
            <th class="px-3 py-2 font-medium text-right">成本</th>
            <th class="px-3 py-2 font-medium text-right">盈亏</th>
            <th class="px-3 py-2 font-medium text-right">收益率</th>
            <th class="px-3 py-2 font-medium text-right">年化</th>
            <th class="px-3 py-2 font-medium text-right">年化波动</th>
            <th class="px-3 py-2 font-medium text-right">夏普</th>
            <th class="px-3 py-2 font-medium text-right">持有天数</th>
            <th class="px-3 py-2 font-medium text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="p in store.closedPositions.positions" :key="p.id">
            <tr class="border-t border-border-default text-text-muted hover:bg-bg-secondary cursor-pointer" :title="expandedIds.has(p.id) ? '点击收起流水' : '点击展开流水'" @click="toggleExpand(p.id)">
              <td class="px-3 py-2" @click.stop>
                <div class="font-medium text-text-primary">{{ p.name }}</div>
                <div class="text-xs">{{ p.purchase_date }} → {{ p.sell_date }}<span v-if="p.symbol"> · {{ p.exchange }} {{ p.symbol }}</span></div>
              </td>
              <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(p.buy_amount) }}</td>
              <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(p.proceeds) }}</td>
              <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(p.total_fee) }}</td>
              <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(p.cost) }}</td>
              <td class="px-3 py-2 text-right" :class="colorClass(p.realized_pnl)">{{ signed(p.realized_pnl) }}</td>
              <td class="px-3 py-2 text-right" :class="colorClassNullable(p.return_rate)">{{ p.return_rate != null ? (p.return_rate * 100).toFixed(2) + '%' : '—' }}</td>
              <td class="px-3 py-2 text-right" :class="colorClassNullable(p.ann_return)">{{ p.ann_return != null ? (p.ann_return * 100).toFixed(2) + '%' : '—' }}</td>
              <td class="px-3 py-2 text-right" :title="`持有期净值序列年化波动率`">{{ p.ann_volatility != null ? (p.ann_volatility * 100).toFixed(2) + '%' : '—' }}</td>
              <td class="px-3 py-2 text-right" :title="`持有期夏普（无风险利率 2%）`">{{ p.sharpe_ratio != null ? p.sharpe_ratio.toFixed(2) : '—' }}</td>
              <td class="px-3 py-2 text-right">{{ p.days_held }}</td>
              <td class="px-3 py-2 text-center whitespace-nowrap" @click.stop>
                <div class="flex items-center justify-center gap-2">
                  <button v-if="soldInvById[p.id]" @click="openDetail(soldInvById[p.id]!)" title="净值曲线、指标与买卖点" class="text-text-secondary hover:text-accent-primary"><LineChart :size="14" /></button>
                  <button @click="toggleExpand(p.id)" :title="expandedIds.has(p.id) ? '收起流水' : '展开流水'" class="text-text-secondary hover:text-accent-primary"><ListPlus :size="14" /></button>
                  <button v-if="soldInvById[p.id]" @click="openProductModal(soldInvById[p.id]!)" title="编辑" class="text-text-secondary hover:text-accent-primary"><Edit2 :size="14" /></button>
                </div>
              </td>
            </tr>
            <tr v-if="expandedIds.has(p.id)" class="bg-bg-secondary">
              <td colspan="12" class="px-4 py-3">
                <div class="flex items-center justify-between mb-2">
                  <div class="text-xs font-medium text-text-secondary">平仓产品流水（{{ txMap[p.id]?.length || 0 }} 条）</div>
                  <div class="text-xs text-text-muted">已平仓产品的流水仅供查看，编辑请使用右侧「编辑」按钮</div>
                </div>
                <table class="w-full text-xs">
                  <thead><tr class="text-text-muted"><th class="px-2 py-1 text-left">日期</th><th class="px-2 py-1 text-left">类型</th><th class="px-2 py-1 text-right">数量</th><th class="px-2 py-1 text-right">单价</th><th class="px-2 py-1 text-right">金额</th><th class="px-2 py-1 text-right">费用</th><th class="px-2 py-1 text-left">备注</th></tr></thead>
                  <tbody>
                    <tr v-for="tx in txMap[p.id] || []" :key="tx.id" class="border-t border-border-default">
                      <td class="px-2 py-1">{{ tx.event_date }}</td>
                      <td class="px-2 py-1">{{ TX_LABELS[tx.event_type] }}</td>
                      <td class="px-2 py-1 text-right">{{ tx.quantity || '—' }}</td>
                      <td class="px-2 py-1 text-right">{{ sym }}{{ fmt(tx.unit_price) }}</td>
                      <td class="px-2 py-1 text-right">{{ signed(tx.amount) }}</td>
                      <td class="px-2 py-1 text-right">{{ tx.fee ? sym + fmt(tx.fee) : '—' }}</td>
                      <td class="px-2 py-1 text-text-muted">{{ tx.notes }}</td>
                    </tr>
                    <tr v-if="!txMap[p.id]?.length"><td colspan="7" class="px-2 py-2 text-text-muted text-center">暂无流水记录</td></tr>
                  </tbody>
                </table>
              </td>
            </tr>
          </template>
          <tr class="border-t-2 border-border-default bg-bg-secondary font-medium">
            <td class="px-3 py-2">合计</td>
            <td class="px-3 py-2 text-right" colspan="3"></td>
            <td class="px-3 py-2 text-right">{{ sym }}{{ fmt(store.closedPositions.total_cost) }}</td>
            <td class="px-3 py-2 text-right" :class="colorClass(store.closedPositions.total_realized)">{{ signed(store.closedPositions.total_realized) }}</td>
            <td class="px-3 py-2 text-right" :class="colorClassNullable(store.closedPositions.total_return_rate)">{{ store.closedPositions.total_return_rate != null ? (store.closedPositions.total_return_rate * 100).toFixed(2) + '%' : '—' }}</td>
            <td class="px-3 py-2 text-right"></td>
            <td class="px-3 py-2 text-right text-text-muted">—</td>
            <td class="px-3 py-2 text-right text-text-muted">—</td>
            <td class="px-3 py-2 text-right">{{ totalDaysHeld }}</td>
            <td class="px-3 py-2"></td>
          </tr>
</tbody>
      </table>
    </div>

    <!-- 出入金账本（默认折叠） -->
    <div class="bg-white rounded-lg shadow-sm overflow-hidden mb-4">
      <div class="p-4 border-b border-border-default flex items-center justify-between cursor-pointer select-none" @click="cashFlowsCollapsed = !cashFlowsCollapsed">
        <div>
          <h3 class="font-semibold text-sm flex items-center gap-1">
            <ChevronRight v-if="cashFlowsCollapsed" :size="14" />
            <ChevronDown v-else :size="14" />
            出入金账本（{{ store.cashFlows.length }} 笔）
          </h3>
          <div class="text-xs text-text-muted mt-0.5">与记账 tab 投资账户的转入/转出一一对应</div>
        </div>
      </div>
      <div v-if="!cashFlowsCollapsed">
        <div class="px-4 py-2 bg-bg-secondary text-xs text-text-muted border-b border-border-default">
          「从记账同步」会扫描记账 tab 中投资账户的转入/转出转账自动生成入金/出金流水（同日同额跳过），并把投资账户的初始余额作为首笔入金同步
        </div>
        <table class="w-full text-sm">
          <thead class="bg-bg-tertiary text-left">
            <tr><th class="px-3 py-2 font-medium">日期</th><th class="px-3 py-2 font-medium">类型</th><th class="px-3 py-2 font-medium text-right">金额</th><th class="px-3 py-2 font-medium">备注</th><th class="px-3 py-2 font-medium text-center">操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="f in store.cashFlows" :key="f.id" class="border-t border-border-default">
              <td class="px-3 py-2">{{ f.flow_date }}</td>
              <td class="px-3 py-2">
                <span :class="f.flow_type === 'deposit' ? 'text-income-color' : 'text-expense-color'">{{ f.flow_type === 'deposit' ? '入金' : '出金' }}</span>
              </td>
              <td class="px-3 py-2 text-right font-medium">{{ sym }}{{ fmt(f.amount) }}</td>
              <td class="px-3 py-2 text-text-muted">{{ f.notes }}</td>
              <td class="px-3 py-2 text-center whitespace-nowrap">
                <button @click="openFlowModal(f)" class="text-text-secondary hover:text-accent-primary mr-2"><Edit2 :size="14" /></button>
                <button @click="removeFlow(f.id)" class="text-text-muted hover:text-expense-color"><Trash2 :size="14" /></button>
              </td>
            </tr>
            <tr v-if="!store.cashFlows.length"><td colspan="5" class="px-4 py-6 text-center text-text-muted">暂无入金/出金记录。记账 tab 里每笔「转入投资账户」都应在这里记一笔入金。</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 投资账户一致性校验 -->
    <div v-if="consistency" class="bg-white rounded-lg shadow-sm p-4 mb-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="font-semibold text-sm">投资账户一致性校验</h3>
        <span :class="['text-xs px-2 py-0.5 rounded', consistency.status === 'ok' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800']">
          {{ consistency.status === 'ok' ? '一致' : '有差异' }}
        </span>
      </div>
      <div class="grid grid-cols-2 lg:grid-cols-6 gap-3 text-sm">
        <div><div class="text-xs text-text-muted">记账 tab 投资账户余额</div><div class="font-medium">{{ sym }}{{ fmt(consistency.total_account_balance) }}</div></div>
        <div><div class="text-xs text-text-muted">投资 tab 本金（持仓成本）</div><div class="font-medium">{{ sym }}{{ fmt(consistency.principal) }}</div></div>
        <div><div class="text-xs text-text-muted">当前市值</div><div class="font-medium">{{ sym }}{{ fmt(consistency.total_current) }}</div></div>
        <div>
          <div class="text-xs text-text-muted">落袋盈亏(含分红)</div>
          <div class="font-medium" :class="colorClass((consistency.realized_pnl || 0) + (consistency.dividend_total || 0))">{{ signed((consistency.realized_pnl || 0) + (consistency.dividend_total || 0)) }}</div>
          <div class="text-xs mt-0.5 text-text-muted">已平仓 {{ signed(consistency.realized_pnl || 0) }} · 分红 {{ signed(consistency.dividend_total || 0) }}</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">当月实时盈亏</div>
          <div class="font-medium" :class="colorClassNullable(consistency.current_month_pnl)">{{ signed(consistency.current_month_pnl || 0) }}</div>
          <div class="text-xs mt-0.5 text-text-muted">未同步到记账的部分</div>
        </div>
        <div>
          <div class="text-xs text-text-muted">闲置现金（余额 + 当月盈亏 − 市值）</div>
          <div class="font-medium" :class="consistency.idle_cash >= 0 ? '' : 'text-expense-color'">{{ sym }}{{ fmt(consistency.idle_cash) }}</div>
          <div class="text-xs mt-0.5" :class="consistency.floating_pnl >= 0 ? 'text-income-color' : 'text-expense-color'">浮动盈亏 {{ signed(consistency.floating_pnl) }}</div>
        </div>
      </div>
      <div v-if="consistency.accounts.length" class="text-xs text-text-muted mt-2">
        {{ consistency.accounts.map(a => `${a.name} ${fmt(a.balance)}`).join(' · ') }}
      </div>
      <ul v-if="consistency.warnings.length" class="mt-2 space-y-1">
        <li v-for="(w, i) in consistency.warnings" :key="i" class="text-xs text-expense-color">{{ w }}</li>
      </ul>
    </div>

    <!-- Product Add/Edit Modal -->
    <BaseModal v-if="showProductModal" :title="editingProduct ? '编辑投资' : '添加投资'" @close="showProductModal = false">
      <div class="space-y-3">
        <div v-if="!editingProduct" class="flex gap-1 border-b border-border-default -mx-4 px-4">
          <button @click="productModalTab = 'create'"
            :class="['px-3 py-2 text-sm border-b-2 -mb-px', productModalTab === 'create' ? 'border-accent-primary text-accent-primary font-medium' : 'border-transparent text-text-muted hover:text-text-secondary']">
            申购新资产
          </button>
          <button @click="productModalTab = 'redeem'"
            :class="['px-3 py-2 text-sm border-b-2 -mb-px', productModalTab === 'redeem' ? 'border-accent-primary text-accent-primary font-medium' : 'border-transparent text-text-muted hover:text-text-secondary']">
            赎回已有资产
          </button>
        </div>

        <!-- Redeem tab: sell an existing position -->
        <div v-if="productModalTab === 'redeem' && !editingProduct" class="space-y-3">
          <div>
            <label class="block text-sm mb-1">选择持仓</label>
            <select v-model="redeemForm.investment_id" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="">请选择</option>
              <option v-for="i in openInvestments" :key="i.id" :value="i.id">
                {{ i.name }}（{{ fmt(i.quantity) }} 份 · 现价 {{ sym }}{{ priceFmt(i, i.current_price) }}）
              </option>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="block text-sm mb-1">赎回份额</label><input v-model.number="redeemForm.quantity" type="number" min="0" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
            <div>
              <label class="block text-sm mb-1">赎回单位净值<span class="text-text-muted font-normal">（可留空）</span></label>
              <input v-model.number="redeemForm.unit_price" type="number" min="0" step="0.0001" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="留空自动取当日净值" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div><label class="block text-sm mb-1">赎回费用</label><input v-model.number="redeemForm.fee" type="number" min="0" step="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="0.00" /></div>
            <div><label class="block text-sm mb-1">赎回日期</label><input v-model="redeemForm.redeem_date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          </div>
          <div class="text-xs text-text-muted">赎回记录会写入交易流水；当累计赎回份额等于持仓份额时，产品自动标记为已平仓。净值留空时系统自动取赎回日（或此前最近交易日）的收盘净值，回款金额 = 份额 × 净值。</div>
        </div>

        <!-- Create tab: existing form -->
        <div v-if="productModalTab === 'create' || editingProduct" class="space-y-3">
        <div>
          <label class="block text-sm mb-1">代码（推荐，自动查询名称与现价）</label>
          <div class="flex gap-2">
            <input v-model="productForm.symbol" class="flex-1 px-3 py-2 border border-border-default rounded-md" :placeholder="symbolPlaceholder" @keyup.enter="lookupCode" />
            <button :disabled="lookingUp || !productForm.symbol" @click="lookupCode"
              :class="['px-3 py-2 rounded-md text-sm border border-border-default', lookingUp || !productForm.symbol ? 'text-text-muted' : 'text-text-secondary hover:bg-bg-tertiary']">
              {{ lookingUp ? '查询中…' : '查询' }}
            </button>
          </div>
          <div class="text-xs text-text-muted mt-1">同一代码可能在多个市场存在，查询后按候选选择</div>
        </div>
        <div v-if="lookupCandidates.length" class="space-y-1">
          <div class="text-xs text-text-muted">请选择匹配的市场：</div>
          <button v-for="c in lookupCandidates" :key="c.exchange" @click="pickCandidate(c)"
            :class="['w-full text-left px-3 py-2 rounded-md border text-sm', productForm.exchange === c.exchange ? 'border-accent-primary bg-bg-secondary' : 'border-border-default hover:bg-bg-tertiary']">
            <span class="font-medium">{{ c.name }}</span>
            <span class="text-xs text-text-muted ml-2">{{ EXCHANGE_LABELS[c.exchange] || c.exchange }} · {{ sym }}{{ priceFmtRaw(productForm.investment_type === 'fund', c.price) }}</span>
          </button>
        </div>
        <div><label class="block text-sm mb-1">名称</label><input v-model="productForm.name" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="如：易方达黄金ETF联接" /></div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="productForm.investment_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="stock">股票</option><option value="fund">基金</option><option value="bond">债券</option>
              <option value="crypto">加密货币</option><option value="deposit">存款</option><option value="other">其他</option>
            </select>
          </div>
          <div>
            <label class="block text-sm mb-1">市场</label>
            <select v-model="productForm.exchange" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="">未指定（手动输入价格）</option>
              <option value="SH">沪市A股 / 沪市ETF (SH)</option>
              <option value="SZ">深市A股 / 深市ETF (SZ)</option>
              <option value="HK">港股 (HK)</option>
              <option value="FUND_CN">中国开放式基金</option>
              <option value="US">美股（仅手动输入）</option>
              <option value="CRYPTO">加密货币（仅手动输入）</option>
            </select>
          </div>
        </div>
        <div>
          <label class="block text-sm mb-1">底层资产类型</label>
          <select v-model="productForm.underlying_asset_type" class="w-full px-3 py-2 border border-border-default rounded-md">
            <option value="">请选择</option>
            <option v-for="u in UNDERLYING_OPTIONS" :key="u" :value="u">{{ u }}</option>
            <option value="_custom">自定义...</option>
          </select>
        </div>
        <div v-if="productForm.underlying_asset_type === '_custom'">
          <input v-model="productForm.underlying_asset_type_custom" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="输入底层资产类型" />
        </div>
        <div class="grid grid-cols-4 gap-3">
          <div><label class="block text-sm mb-1">{{ qtyLabel }}</label><input v-model.number="productForm.quantity" type="number" :step="qtyStep" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">{{ isFund ? '买入单位净值' : '买入均价' }}</label><input v-model.number="productForm.purchase_price" type="number" :step="priceStep" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">买入费用</label><input v-model.number="productForm.purchase_fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="0.00" /></div>
          <div><label class="block text-sm mb-1">{{ isFund ? '当前单位净值' : '现价' }}</label><input v-model.number="productForm.current_price" type="number" :step="priceStep" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        </div>
        <div class="text-xs text-text-muted">买入费用会计入摊薄成本；有流水后，份额与摊薄单价按流水自动重算，此处初始值仅作首笔快照</div>
        <div class="grid grid-cols-2 gap-3">
          <div><label class="block text-sm mb-1">买入日期</label><input v-model="productForm.purchase_date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
          <div><label class="block text-sm mb-1">卖出日期（可选）</label><input v-model="productForm.sell_date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        </div>
        <div><label class="block text-sm mb-1">备注</label><textarea v-model="productForm.notes" class="w-full px-3 py-2 border border-border-default rounded-md" rows="2" placeholder="可选"></textarea></div>
        </div>
      </div>
      <template #footer>
        <button @click="showProductModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button v-if="productModalTab === 'create' || editingProduct" @click="saveProduct" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">{{ editingProduct ? '更新' : '添加' }}</button>
        <button v-else @click="redeemSubmit" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">确认赎回</button>
      </template>
    </BaseModal>

    <!-- Cash flow (deposit/withdrawal) modal -->
    <BaseModal v-if="showFlowModal" :title="editingFlow ? '编辑入金/出金' : '记入金/出金'" @close="showFlowModal = false">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="flowForm.flow_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="deposit">入金（转入投资账户）</option>
              <option value="withdrawal">出金（从投资账户转出）</option>
            </select>
          </div>
          <div>
            <label class="block text-sm mb-1">日期</label>
            <input v-model="flowForm.flow_date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
        </div>
        <div><label class="block text-sm mb-1">金额</label><input v-model.number="flowForm.amount" type="number" step="0.01" min="0.01" class="w-full px-3 py-2 border border-border-default rounded-md" /></div>
        <div><label class="block text-sm mb-1">备注</label><input v-model="flowForm.notes" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="可选，如：工资卡转入中行投资" /></div>
      </div>
      <template #footer>
        <button @click="showFlowModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="saveFlow" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">保存</button>
      </template>
    </BaseModal>

    <!-- Transaction Add/Edit Modal -->
    <BaseModal v-if="showTxModal" :title="editingTx ? '编辑流水' : '记录流水'" @close="showTxModal = false">
      <div class="space-y-3">
        <div><label class="block text-sm mb-1">产品</label>
          <div class="px-3 py-2 bg-bg-secondary rounded-md text-sm">{{ txForm.investment_name }}</div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">类型</label>
            <select v-model="txForm.event_type" class="w-full px-3 py-2 border border-border-default rounded-md">
              <option value="buy">买入</option>
              <option value="sell">卖出</option>
              <option value="dividend">分红 / 派息</option>
              <option value="fee">费用 / 税费（补录）</option>
              <option value="adjustment">调整（手动补正）</option>
            </select>
          </div>
          <div>
            <label class="block text-sm mb-1">日期</label>
            <input v-model="txForm.event_date" type="date" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm mb-1">{{ quantityFieldLabel }}</label>
            <input v-model.number="txForm.quantity" type="number" :step="txQtyStep" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
          <div>
            <label class="block text-sm mb-1">{{ priceFieldLabel }}</label>
            <input v-model.number="txForm.unit_price" type="number" :step="txPriceStep" class="w-full px-3 py-2 border border-border-default rounded-md" />
          </div>
        </div>
        <div v-if="txForm.event_type === 'buy' || txForm.event_type === 'sell'">
          <label class="block text-sm mb-1">交易费用（可选，计入摊薄成本）</label>
          <input v-model.number="txForm.fee" type="number" step="0.01" min="0" class="w-full px-3 py-2 border border-border-default rounded-md" placeholder="0.00" />
        </div>
        <div class="text-xs text-text-muted" v-if="txForm.event_type === 'buy' || txForm.event_type === 'sell'">
          金额 = 数量 × 单价{{ txForm.fee ? `，另加费用 ${sym}${fmt(txForm.fee || 0)}` : '' }}（{{ sym }}{{ fmt((txForm.quantity || 0) * (txForm.unit_price || 0)) }}{{ txForm.fee ? ` + ${fmt(txForm.fee)}` : '' }}）
        </div>
        <div><label class="block text-sm mb-1">备注</label><textarea v-model="txForm.notes" class="w-full px-3 py-2 border border-border-default rounded-md" rows="2" placeholder="可选"></textarea></div>
      </div>
      <template #footer>
        <button v-if="editingTx" @click="deleteTx" class="px-4 py-2 text-expense-color hover:bg-red-50 rounded-md">删除</button>
        <button @click="showTxModal = false" class="px-4 py-2 text-text-secondary">取消</button>
        <button @click="saveTx" class="px-4 py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover">{{ editingTx ? '更新' : '保存' }}</button>
      </template>
    </BaseModal>

    <!-- Per-product detail drawer (NAV curve + buy/sell markers) -->
    <InvestmentDetailDrawer v-if="drawerInvestment" :investment="drawerInvestment" @close="drawerInvestment = null" @updated="onInvestmentUpdated" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Plus, Edit2, Trash2, RefreshCw, ListPlus, LineChart, ChevronRight, ChevronDown } from 'lucide-vue-next'
import { useInvestmentsStore } from '@/stores/investments'
import { useSettingsStore } from '@/stores/settings'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/components/common/BaseModal.vue'
import InvestmentDetailDrawer from './InvestmentDetailDrawer.vue'
import HealthPanel from './HealthPanel.vue'
import type { Investment, InvestmentTransaction, InvestmentEventType, InvestmentMetrics, InvestmentConsistency, InvestmentCashFlow, CashFlowType, LookupCandidate, RefreshResult } from '@/types'

const store = useInvestmentsStore()
const settingsStore = useSettingsStore()
const api = useApi()
const { show } = useToast()
const sym = computed(() => settingsStore.settings.currency_symbol)
const overview = computed(() => store.portfolioOverview)

const TYPE_LABELS: Record<string, string> = { stock: '股票', fund: '基金', bond: '债券', crypto: '加密货币', deposit: '存款', other: '其他' }
const TX_LABELS: Record<InvestmentEventType, string> = { buy: '买入', sell: '卖出', dividend: '分红', fee: '费用', adjustment: '调整' }
const EXCHANGE_LABELS: Record<string, string> = { SH: '沪市', SZ: '深市', HK: '港股', FUND_CN: '场外基金', US: '美股', CRYPTO: '加密货币' }
const UNDERLYING_OPTIONS = ['债券', '股票', '大宗商品', '黄金', '原油', '货币市场', '混合']
const AUTO_EXCHANGES = ['SH', 'SZ', 'HK', 'FUND_CN']

function fmt(n: number): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmt4(n: number): string { return (n ?? 0).toLocaleString('zh-CN', { minimumFractionDigits: 4, maximumFractionDigits: 4 }) }
function priceFmtRaw(isFund: boolean, n: number): string { return isFund ? fmt4(n) : fmt(n) }
function priceFmt(inv: Investment, n: number): string { return priceFmtRaw(inv.investment_type === 'fund', n) }
function signed(n: number): string { return (n >= 0 ? '+' : '') + sym.value + fmt(Math.abs(n)) }
function xirrLabel(n: number | null | undefined): string { return n === null || n === undefined ? '—' : (n * 100).toFixed(1) + '%' }
function colorClass(n: number): string { return n >= 0 ? 'text-income-color' : 'text-expense-color' }
function colorClassNullable(n: number | null | undefined): string { return n === null || n === undefined ? '' : (n >= 0 ? 'text-income-color' : 'text-expense-color') }
function supportsAutoRefresh(ex: string): boolean { return AUTO_EXCHANGES.includes(ex) }
function costDist(inv: Investment): number { const cb = inv.purchase_price || 0; const cur = inv.current_price || 0; if (cb <= 0) return 0; return ((cur - cb) / cb) * 100 }
function formatDateShort(s: string) { return new Date(s).toLocaleDateString('zh-CN') }

// Aggregate state
const productMetricMap = ref<Record<string, InvestmentMetrics>>({})
const consistency = ref<InvestmentConsistency | null>(null)
const cashFlowsCollapsed = ref(true)
const expandedIds = ref<Set<string>>(new Set())
const drawerInvestment = ref<Investment | null>(null)
function openDetail(inv: Investment) { drawerInvestment.value = inv }
async function onInvestmentUpdated() {
  await store.fetchInvestments()
  const current = drawerInvestment.value
  if (current) {
    const fresh = store.investments.find(i => i.id === current.id)
    if (fresh) drawerInvestment.value = fresh
  }
  await loadAggregates()
}

async function loadConsistency() {
  try {
    const res = await api.get('/investments/consistency')
    consistency.value = res.data
  } catch { consistency.value = null }
}
const txMap = ref<Record<string, InvestmentTransaction[]>>({})

const activeInvestments = computed(() => store.investments.filter(i => !i.sell_date))
const soldInvestments = computed(() => store.investments.filter(i => !!i.sell_date))
// Map investment_id → Investment for closed-position rows (detail/edit actions)
const soldInvById = computed<Record<string, Investment>>(() => {
  const m: Record<string, Investment> = {}
  for (const i of soldInvestments.value) m[i.id] = i
  return m
})

const totalDaysHeld = computed(() => {
  const positions = store.closedPositions?.positions ?? []
  return positions.reduce((s, p) => s + (p.days_held || 0), 0)
})

// Data loading
async function loadAggregates() {
  try {
    const [metricsRes] = await Promise.all([
      api.get('/investments/metrics/all'),
      store.fetchPortfolioOverview(),
      store.fetchClosedPositions(),
      loadConsistency(),
    ])
    const items: { investment_id: string; metrics: InvestmentMetrics }[] = metricsRes.data
    const map: Record<string, InvestmentMetrics> = {}
    for (const it of items) {
      map[it.investment_id] = it.metrics
    }
    productMetricMap.value = map
  } catch (e) {
    console.warn('Failed to load metrics', e)
  }
}

async function loadTxsFor(invId: string, force = false) {
  if (!force && txMap.value[invId]) return
  try { const res = await api.get(`/investments/${invId}/transactions`); txMap.value = { ...txMap.value, [invId]: res.data } }
  catch { txMap.value = { ...txMap.value, [invId]: [] } }
}

async function toggleExpand(invId: string) {
  if (expandedIds.value.has(invId)) { const s = new Set(expandedIds.value); s.delete(invId); expandedIds.value = s }
  else { await loadTxsFor(invId); const s = new Set(expandedIds.value); s.add(invId); expandedIds.value = s }
}

const refreshingId = ref<string | null>(null)
const refreshingAll = ref(false)

async function refreshPrice(inv: Investment) {
  if (!supportsAutoRefresh(inv.exchange)) {
    show('该市场不支持自动刷新，请手动编辑现价', 'warning')
    return
  }
  refreshingId.value = inv.id
  try {
    const res = await api.post(`/investments/${inv.id}/refresh-price`)
    const idx = store.investments.findIndex(i => i.id === inv.id)
    if (idx !== -1) store.investments[idx] = res.data
    show('已更新现价', 'success')
    await loadAggregates()
  } catch (e: any) {
    show(e.response?.data?.detail || '刷新失败', 'error')
  } finally { refreshingId.value = null }
}

async function refreshAllPrices() {
  refreshingAll.value = true
  try {
    const res = await api.post('/investments/refresh-prices/all')
    const results: RefreshResult[] = res.data
    const okItems = results.filter(r => r.ok)
    const failedItems = results.filter(r => !r.ok)
    await store.fetchInvestments()
    if (failedItems.length === 0) {
      show(`已刷新 ${okItems.length} 个现价`, 'success')
    } else {
      const detail = failedItems.slice(0, 3).map(r => `${r.name}：${r.error}`).join('\n')
      const more = failedItems.length > 3 ? `\n…等 ${failedItems.length} 个未成功` : ''
      show(`刷新成功 ${okItems.length} 个，未成功 ${failedItems.length} 个：\n${detail}${more}`, 'warning', { duration: 8000 })
    }
    await loadAggregates()
  } catch (e: any) {
    show(e.response?.data?.detail || '批量刷新失败', 'error')
  } finally { refreshingAll.value = false }
}

// Product modal
const showProductModal = ref(false)
const productModalTab = ref<'create' | 'redeem'>('create')
const redeemForm = ref<{ investment_id: string; quantity: number; unit_price: number; fee: number; redeem_date: string }>({
  investment_id: '', quantity: 0, unit_price: 0, fee: 0, redeem_date: new Date().toISOString().substring(0, 10),
})
const openInvestments = computed(() =>
  store.investments.filter(i => !i.sell_date && (i.quantity || 0) > 0))
const editingProduct = ref<Investment | null>(null)
const productForm = ref({ name: '', investment_type: 'fund' as Investment['investment_type'], underlying_asset_type: '', underlying_asset_type_custom: '', exchange: '', symbol: '', quantity: 0, purchase_price: 0, purchase_fee: 0, current_price: 0, purchase_date: '', sell_date: '', notes: '' })
const lookingUp = ref(false)
const lookupCandidates = ref<LookupCandidate[]>([])

const isFund = computed(() => productForm.value.investment_type === 'fund')
const qtyLabel = computed(() => isFund.value ? '初始份额' : '初始数量')
const qtyStep = computed(() => isFund.value ? '0.0001' : '0.01')
const priceStep = computed(() => isFund.value ? '0.0001' : '0.01')

const symbolPlaceholder = computed(() => {
  switch (productForm.value.exchange) {
    case 'SH': return '如 600519、510300'
    case 'SZ': return '如 000001、159915'
    case 'HK': return '如 00700'
    case 'FUND_CN': return '如 000001、519983'
    case 'US': return '如 AAPL、TSLA'
    case 'CRYPTO': return '如 BTC、ETH'
    default: return '如 000217、600519、00700'
  }
})

async function lookupCode() {
  const code = (productForm.value.symbol || '').trim()
  if (!code) return
  lookingUp.value = true
  lookupCandidates.value = []
  try {
    lookupCandidates.value = await store.lookupSymbol(code)
    if (lookupCandidates.value.length === 1) {
      pickCandidate(lookupCandidates.value[0])
    } else if (lookupCandidates.value.length === 0) {
      show('未查询到该代码，请检查代码或手动填写', 'warning')
    }
  } catch (e: any) {
    show(e.response?.data?.detail || '代码查询失败', 'error')
  } finally { lookingUp.value = false }
}

function pickCandidate(c: LookupCandidate) {
  productForm.value.exchange = c.exchange
  if (c.name) productForm.value.name = c.name
  if (c.price > 0) productForm.value.current_price = c.price
  if (c.exchange === 'FUND_CN' && productForm.value.investment_type !== 'fund') productForm.value.investment_type = 'fund'
  lookupCandidates.value = []
}

function openProductModal(inv?: Investment) {
  editingProduct.value = inv || null
  productModalTab.value = 'create'
  redeemForm.value = { investment_id: '', quantity: 0, unit_price: 0, fee: 0, redeem_date: new Date().toISOString().substring(0, 10) }
  lookupCandidates.value = []
  if (inv) {
    productForm.value = {
      name: inv.name, investment_type: inv.investment_type,
      underlying_asset_type: inv.underlying_asset_type || '', underlying_asset_type_custom: '',
      exchange: inv.exchange || (inv.investment_type === 'fund' && inv.symbol ? 'FUND_CN' : ''), symbol: inv.symbol || '',
      quantity: inv.quantity, purchase_price: inv.purchase_price, purchase_fee: 0, current_price: inv.current_price,
      purchase_date: inv.purchase_date, sell_date: inv.sell_date || '', notes: inv.notes || ''
    }
  } else {
    productForm.value = { name: '', investment_type: 'fund', underlying_asset_type: '', underlying_asset_type_custom: '', exchange: '', symbol: '', quantity: 0, purchase_price: 0, purchase_fee: 0, current_price: 0, purchase_date: '', sell_date: '', notes: '' }
  }
  showProductModal.value = true
}

async function redeemSubmit() {
  if (!redeemForm.value.investment_id) { show('请选择持仓', 'error'); return }
  if (!(redeemForm.value.quantity > 0)) { show('赎回份额需大于 0', 'error'); return }
  if (!redeemForm.value.redeem_date) { show('请选择赎回日期', 'error'); return }
  try {
    await api.post(`/investments/${redeemForm.value.investment_id}/transactions`, {
      event_type: 'sell', event_date: redeemForm.value.redeem_date,
      quantity: redeemForm.value.quantity, unit_price: Number(redeemForm.value.unit_price) || 0,
      fee: redeemForm.value.fee || 0, notes: '',
    })
    show('赎回已记录', 'success')
    showProductModal.value = false
    await loadAggregates()
  } catch (e: any) { show(e.response?.data?.detail || '赎回失败', 'error') }
}

async function saveProduct() {
  try {
    const data: any = { ...productForm.value }
    if (data.underlying_asset_type === '_custom' && data.underlying_asset_type_custom) data.underlying_asset_type = data.underlying_asset_type_custom
    else if (data.underlying_asset_type === '_custom') data.underlying_asset_type = ''
    delete data.underlying_asset_type_custom
    if (data.investment_type === 'fund' && !data.exchange) data.exchange = 'FUND_CN'
    let res: any
    if (editingProduct.value) { await store.updateInvestment(editingProduct.value.id, data) }
    else res = await store.createInvestment(data)
    showProductModal.value = false
    if (res?.merged_into) {
      show(res.merged_message || '已合并到现有持仓', 'info')
    } else {
      show('保存成功', 'success')
    }
    await loadAggregates()
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function removeItem(id: string) {
  if (!confirm('确定删除？此操作会同时删除该产品的所有流水。')) return
  try { await store.deleteInvestment(id); show('已删除', 'success'); await loadAggregates() }
  catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

// Cash flow modal
const showFlowModal = ref(false)
const editingFlow = ref<InvestmentCashFlow | null>(null)
const flowForm = ref<{ flow_type: CashFlowType; amount: number; flow_date: string; notes: string }>({
  flow_type: 'deposit', amount: 0, flow_date: new Date().toISOString().substring(0, 10), notes: ''
})

function openFlowModal(f?: InvestmentCashFlow) {
  editingFlow.value = f || null
  if (f) {
    flowForm.value = { flow_type: f.flow_type, amount: f.amount, flow_date: f.flow_date, notes: f.notes || '' }
  } else {
    flowForm.value = { flow_type: 'deposit', amount: 0, flow_date: new Date().toISOString().substring(0, 10), notes: '' }
  }
  showFlowModal.value = true
}

async function saveFlow() {
  if (!(flowForm.value.amount > 0)) { show('金额必须大于 0', 'warning'); return }
  try {
    if (editingFlow.value) await store.updateCashFlow(editingFlow.value.id, flowForm.value)
    else await store.createCashFlow(flowForm.value)
    showFlowModal.value = false
    show('保存成功', 'success')
    await Promise.all([store.fetchPortfolioOverview(), loadConsistency()])
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function removeFlow(id: string) {
  if (!confirm('确定删除这条入金/出金记录？')) return
  try {
    await store.deleteCashFlow(id)
    show('已删除', 'success')
    await Promise.all([store.fetchPortfolioOverview(), loadConsistency()])
  } catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

const syncingFlows = ref(false)
const syncingPnl = ref(false)

async function syncFromBookkeeping() {
  syncingFlows.value = true
  try {
    const res = await api.post('/investments/cash-flows/sync-from-bookkeeping')
    const d = res.data
    show(d.message || `已同步 ${d.created} 笔`, d.created > 0 ? 'success' : 'info')
    await Promise.all([store.fetchCashFlows(), store.fetchPortfolioOverview(), loadConsistency()])
  } catch (e: any) {
    show(e.response?.data?.detail || '同步失败', 'error')
  } finally { syncingFlows.value = false }
}

async function syncPnlToBookkeeping() {
  syncingPnl.value = true
  try {
    const res = await api.post('/investments/sync-pnl-to-bookkeeping')
    const d = res.data
    show(d.message || '同步完成', d.ok ? (d.adjusted ? 'success' : 'info') : 'warning', { duration: 6000 })
    await Promise.all([store.fetchPortfolioOverview(), loadConsistency()])
  } catch (e: any) {
    show(e.response?.data?.detail || '同步失败', 'error')
  } finally { syncingPnl.value = false }
}

// Transaction modal
const showTxModal = ref(false)
const editingTx = ref<InvestmentTransaction | null>(null)
const txForm = ref<{ investment_id: string; investment_name: string; investment_type: string; event_type: InvestmentEventType; event_date: string; quantity: number; unit_price: number; fee: number; notes: string }>({
  investment_id: '', investment_name: '', investment_type: 'fund', event_type: 'buy', event_date: new Date().toISOString().substring(0, 10), quantity: 0, unit_price: 0, fee: 0, notes: ''
})

const txIsFund = computed(() => txForm.value.investment_type === 'fund')
const txQtyStep = computed(() => txIsFund.value ? '0.0001' : '0.01')
const txPriceStep = computed(() => txIsFund.value ? '0.0001' : '0.001')
const quantityFieldLabel = computed(() => txForm.value.event_type === 'buy' || txForm.value.event_type === 'sell' || txForm.value.event_type === 'adjustment' ? (txIsFund.value ? '份额' : '数量') : '（不适用）')
const priceFieldLabel = computed(() => {
  if (txForm.value.event_type === 'dividend') return '分红总金额'
  if (txForm.value.event_type === 'fee') return '费用总金额'
  return txIsFund.value ? '单位净值' : '单价'
})

function openTxModal(inv: Investment, tx?: InvestmentTransaction) {
  if (tx) {
    editingTx.value = tx
    txForm.value = { investment_id: inv.id, investment_name: inv.name, investment_type: inv.investment_type, event_type: tx.event_type, event_date: tx.event_date, quantity: tx.quantity, unit_price: tx.unit_price, fee: tx.fee || 0, notes: tx.notes || '' }
  } else {
    editingTx.value = null
    txForm.value = { investment_id: inv.id, investment_name: inv.name, investment_type: inv.investment_type, event_type: 'buy', event_date: new Date().toISOString().substring(0, 10), quantity: 0, unit_price: 0, fee: 0, notes: '' }
  }
  showTxModal.value = true
}

async function saveTx() {
  try {
    const isBuySell = txForm.value.event_type === 'buy' || txForm.value.event_type === 'sell'
    const payload = {
      event_type: txForm.value.event_type, event_date: txForm.value.event_date,
      quantity: txForm.value.quantity, unit_price: Number(txForm.value.unit_price) || 0,
      fee: isBuySell ? (txForm.value.fee || 0) : 0, notes: txForm.value.notes
    }
    if (editingTx.value) {
      await api.put(`/investments/${txForm.value.investment_id}/transactions/${editingTx.value.id}`, payload)
    } else {
      await api.post(`/investments/${txForm.value.investment_id}/transactions`, payload)
    }
    showTxModal.value = false
    show('保存成功', 'success')
    await Promise.all([store.fetchInvestments(), loadAggregates(), loadTxsFor(txForm.value.investment_id, true)])
  } catch (e: any) { show(e.response?.data?.detail || '保存失败', 'error') }
}

async function deleteTx() {
  if (!editingTx.value || !confirm('确定删除此流水？')) return
  try {
    await api.delete(`/investments/${txForm.value.investment_id}/transactions/${editingTx.value.id}`)
    showTxModal.value = false
    show('已删除', 'success')
    await Promise.all([store.fetchInvestments(), loadAggregates(), loadTxsFor(txForm.value.investment_id, true)])
  } catch (e: any) { show(e.response?.data?.detail || '删除失败', 'error') }
}

function onRowClick(inv: Investment) { toggleExpand(inv.id) }

onMounted(async () => {
  await store.fetchInvestments()
  await Promise.all([loadAggregates(), store.fetchCashFlows()])
  // Auto-refresh prices on tab enter so displayed values are never stale
  refreshAllPrices()
})
</script>

