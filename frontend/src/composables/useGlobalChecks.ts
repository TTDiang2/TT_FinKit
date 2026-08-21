import { ref, watch } from 'vue'
import { useAccountsStore } from '@/stores/accounts'
import { useInvestmentsStore } from '@/stores/investments'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import type { InvestmentConsistency } from '@/types'

const shownKeys = ref<Set<string>>(new Set())

export function useGlobalChecks() {
  const accountsStore = useAccountsStore()
  const investmentsStore = useInvestmentsStore()
  const api = useApi()
  const { show } = useToast()

  function warnOnce(key: string, message: string) {
    if (shownKeys.value.has(key)) return
    shownKeys.value.add(key)
    show(message, 'warning', { position: 'bottom', duration: 10000 })
  }

  async function checkNegativeBalances() {
    for (const acc of accountsStore.accounts) {
      const bal = acc.current_balance ?? 0
      if (bal < -0.01) {
        warnOnce(
          `neg:${acc.id}:${bal.toFixed(2)}`,
          `账户「${acc.name}」余额为负（${bal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}）。\n` +
          '请检查：① 期初余额是否填错；② 转账方向是否记反；③ 是否有支出/退款漏记或误记。'
        )
      }
    }
  }

  async function checkInvestmentConsistency() {
    let c: InvestmentConsistency
    try {
      const res = await api.get('/investments/consistency')
      c = res.data
    } catch { return }
    if (!c || c.status !== 'diff') return
    for (const w of c.warnings) {
      warnOnce(`cons:${w.slice(0, 80)}`, `【投资对账】${w}`)
    }
  }

  async function runChecks() {
    await Promise.all([checkNegativeBalances(), checkInvestmentConsistency()])
  }

  return { runChecks }
}

export function useGlobalChecksAuto() {
  const accountsStore = useAccountsStore()
  const investmentsStore = useInvestmentsStore()
  const { runChecks } = useGlobalChecks()

  let timer: ReturnType<typeof setTimeout> | null = null
  const debounced = () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => { runChecks() }, 1500)
  }

  watch(() => accountsStore.accounts, debounced)
  watch(() => investmentsStore.cashFlows, debounced)
  watch(() => investmentsStore.investments, debounced)
  runChecks()
}
