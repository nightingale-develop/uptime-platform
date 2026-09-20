<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AppHeader from '@/components/AppHeader.vue'
import { useOrganizationStore } from '@/stores/organizations'

const organizationStore = useOrganizationStore()

const loadError = ref<string | null>(null)

onMounted(async () => {
  try {
    await organizationStore.loadOrganizations()
  } catch {
    loadError.value = 'Unable to load organizations'
  }
})
</script>

<template>
  <div class="app-layout">
    <AppHeader />

    <main class="app-layout__content">
      <p v-if="loadError" class="app-layout__error">
        {{ loadError }}
      </p>

      <p v-else-if="!organizationStore.initialized">Loading...</p>

      <p v-else-if="!organizationStore.currentOrganization" class="app-layout__empty">
        No organizations available.
      </p>

      <RouterView v-else :key="organizationStore.currentOrganizationId ?? 'no-organization'" />
    </main>
  </div>
</template>

<style lang="scss">
@use '@/assets/scss/components/app-layout';
</style>
