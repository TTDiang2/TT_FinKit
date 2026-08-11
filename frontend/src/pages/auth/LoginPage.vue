<template>
  <div class="min-h-screen flex items-center justify-center bg-bg-secondary">
    <div class="bg-white rounded-lg shadow-lg w-full max-w-sm p-8">
      <h1 class="text-2xl font-bold text-center mb-6">登录 FinKit</h1>
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">邮箱</label>
          <input v-model="form.email" type="email" required class="w-full px-3 py-2 border border-border-default rounded-md focus:outline-none focus:ring-2 focus:ring-accent-primary" placeholder="you@example.com" />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">密码</label>
          <input v-model="form.password" type="password" required class="w-full px-3 py-2 border border-border-default rounded-md focus:outline-none focus:ring-2 focus:ring-accent-primary" placeholder="••••••••" />
        </div>
        <button type="submit" :disabled="loading" class="w-full py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover transition-colors disabled:opacity-50">
          {{ loading ? '登录中...' : '登录' }}
        </button>
        <p class="text-center text-sm text-text-secondary mt-4">
          还没有账号？<router-link to="/register" class="text-accent-primary hover:underline">注册</router-link>
        </p>
      </form>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const authStore = useAuthStore()
const { show } = useToast()
const form = ref({ email: '', password: '' })
const loading = ref(false)

async function handleLogin() {
  loading.value = true
  try {
    await authStore.login(form.value.email, form.value.password)
    show('登录成功', 'success')
    router.push('/')
  } catch (e: any) {
    show(e.response?.data?.detail || '登录失败', 'error')
  } finally {
    loading.value = false
  }
}
</script>
