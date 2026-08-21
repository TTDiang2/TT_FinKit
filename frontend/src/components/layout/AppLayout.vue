<template>
  <div class="flex h-screen overflow-hidden">
    <AppSidebar />
    <main class="flex-1 overflow-y-auto bg-bg-secondary">
      <RouterView />
    </main>
    <ToastContainer />
  </div>
</template>
<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import ToastContainer from '@/components/common/ToastContainer.vue'
import { useAccountsStore } from '@/stores/accounts'
import { useCategoriesStore } from '@/stores/categories'
import { useTagsStore } from '@/stores/tags'
import { useSettingsStore } from '@/stores/settings'
import { useGlobalChecksAuto } from '@/composables/useGlobalChecks'

const accountsStore = useAccountsStore()
const categoriesStore = useCategoriesStore()
const tagsStore = useTagsStore()
const settingsStore = useSettingsStore()

useGlobalChecksAuto()

onMounted(async () => {
  await Promise.all([
    accountsStore.fetchAccounts(),
    categoriesStore.fetchCategories(),
    tagsStore.fetchTags(),
    settingsStore.fetchSettings(),
  ])
})
</script>
