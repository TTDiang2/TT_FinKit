<template>
  <div class="min-h-screen flex items-center justify-center bg-bg-secondary">
    <div class="bg-white rounded-lg shadow-lg w-full max-w-sm p-8">
      <h1 class="text-2xl font-bold text-center mb-6">注册 FinKit</h1>
      <form @submit.prevent="handleRegister" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">名字</label>
          <input v-model="form.name" type="text" class="w-full px-3 py-2 border border-border-default rounded-md focus:outline-none focus:ring-2 focus:ring-accent-primary" placeholder="你的名字" />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">邮箱</label>
          <input v-model="form.email" type="email" required class="w-full px-3 py-2 border border-border-default rounded-md focus:outline-none focus:ring-2 focus:ring-accent-primary" placeholder="you@example.com" />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">密码</label>
          <input v-model="form.password" type="password" required minlength="6" class="w-full px-3 py-2 border border-border-default rounded-md focus:outline-none focus:ring-2 focus:ring-accent-primary" placeholder="至少6位" />
        </div>
        <div>
          <label class="block text-sm font-medium text-text-secondary mb-1">确认密码</label>
          <input v-model="form.confirm" type="password" required class="w-full px-3 py-2 border border-border-default rounded-md focus:outline-none focus:ring-2 focus:ring-accent-primary" placeholder="再次输入密码" />
        </div>
        <button type="submit" :disabled="loading || form.password !== form.confirm" class="w-full py-2 bg-accent-primary text-white rounded-md hover:bg-accent-hover transition-colors disabled:opacity-50">
          {{ loading ? '注册中...' : '注册' }}
        </button>
        <p class="text-center text-sm text-text-secondary mt-4">
          已有账号？<router-link to="/login" class="text-accent-primary hover:underline">登录</router-link>
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
const form = ref({ name: '', email: '', password: '', confirm: '' })
const loading = ref(false)

async function handleRegister() {
  if (form.value.password !== form.value.confirm) {
    show('两次密码不一致', 'error')
    return
  }
  loading.value = true
  try {
    await authStore.register(form.value.email, form.value.password, form.value.name)
    show('注册成功', 'success')
    router.push('/')
  } catch (e: any) {
    show(e.response?.data?.detail || '注册失败', 'error')
  } finally {
    loading.value = false
  }
}
</script>
