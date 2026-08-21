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
        { path: 'admin', name: 'admin', component: () => import('@/pages/admin/AdminPage.vue') },
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
            { path: 'ai', name: 'investments-ai', component: () => import('@/pages/investments/AIAnalysisTab.vue') },
          ]
        },
        { path: 'reports', name: 'reports', component: () => import('@/pages/reports/ReportsPage.vue') },
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

export default router
