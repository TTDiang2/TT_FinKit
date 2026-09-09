import { createRouter, createWebHistory } from 'vue-router'
import { watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/pages/auth/LoginPage.vue'), meta: { requiresAuth: false } },
    { path: '/register', name: 'register', component: () => import('@/pages/auth/RegisterPage.vue'), meta: { requiresAuth: false } },
    {
      path: '/', component: () => import('@/components/layout/AppLayout.vue'), meta: { requiresAuth: true },
      children: [
        { path: '', name: 'home', component: () => import('@/pages/home/HomePage.vue') },
        { path: 'bookkeeping', name: 'bookkeeping', component: () => import('@/pages/bookkeeping/BookkeepingPage.vue') },
        { path: 'statistics', name: 'statistics', component: () => import('@/pages/statistics/StatisticsPage.vue') },
        { path: 'assets', name: 'assets', component: () => import('@/pages/assets/AssetsPage.vue') },
        {
          path: 'investments', component: () => import('@/pages/investments/InvestmentsLayout.vue'),
          children: [
            { path: '', name: 'investments', component: () => import('@/pages/investments/OverviewTab.vue') },
            {
              path: 'strategies',
              name: 'investments-strategies',
              component: () => import('@/pages/investments/StrategyLibraryPage.vue'),
            },
            // /investments/backtests -> /investments/strategies?sub=backtest (回测 is a sub-tab of 策略)
            { path: 'backtests', redirect: (to) => ({ path: '/investments/strategies', query: { sub: 'backtest' } }) },
            { path: 'backtests/:id', name: 'investments-backtests-detail', component: () => import('@/pages/investments/BacktestDetailPage.vue') },
            { path: 'assets', name: 'investments-assets', component: () => import('@/pages/investments/AssetPoolPage.vue') },
            { path: 'factors', name: 'investments-factors', component: () => import('@/pages/investments/FactorPage.vue') },
            // /investments/signals -> /investments/monitor?sub=signal (信号 is a sub-tab of 监控)
            { path: 'signals', redirect: (to) => ({ path: '/investments/monitor', query: { sub: 'signal' } }) },
            { path: 'monitor', name: 'investments-monitor', component: () => import('@/pages/investments/MonitorPage.vue') },
            { path: 'ai', name: 'investments-ai', component: () => import('@/pages/investments/AIAnalysisTab.vue') },
          ],
        },
        { path: 'reports', name: 'reports', component: () => import('@/pages/reports/ReportsPage.vue') },
        { path: 'ai-advisor', name: 'ai-advisor', component: () => import('@/pages/advisor/AiAdvisorPage.vue') },
        { path: 'settings', name: 'settings', component: () => import('@/pages/settings/SettingsPage.vue') },
      ]
    }
  ]
})

function waitForReady(): Promise<void> {
  const authStore = useAuthStore()
  if (authStore.isReady) return Promise.resolve()
  return new Promise((resolve) => {
    const stop = watch(() => authStore.isReady, (ready) => {
      if (ready) { stop(); resolve() }
    })
  })
}

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await waitForReady()

  if (to.meta.requiresAuth !== false && !authStore.token) return '/login'
  if ((to.name === 'login' || to.name === 'register') && authStore.token) return '/'
})

// 重建 dist 后旧 chunk 文件名失效：浏览器若还持有旧主包，点懒加载路由会 404，
// 表现为「页面打不开」。捕获动态 import 失败后整页重载一次，拿新 index.html 的
// 新 chunk；10s 冷却防止真 404 时无限刷新。
const CHUNK_RELOAD_KEY = 'finkit:chunk-reload-at'
const CHUNK_RELOAD_COOLDOWN_MS = 10_000

router.onError((error, to) => {
  const message = error?.message || ''
  if (!/dynamically imported module|module script failed/i.test(message)) return
  const lastAt = Number(sessionStorage.getItem(CHUNK_RELOAD_KEY) || 0)
  if (Date.now() - lastAt < CHUNK_RELOAD_COOLDOWN_MS) return
  sessionStorage.setItem(CHUNK_RELOAD_KEY, String(Date.now()))
  window.location.assign(to.fullPath)
})

export default router
