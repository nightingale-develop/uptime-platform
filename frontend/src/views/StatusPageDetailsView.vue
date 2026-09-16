<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMonitorStore } from '@/stores/monitors'
import { useOrganizationStore } from '@/stores/organizations'
import { useStatusPageStore } from '@/stores/status-pages'
import type { StatusPage, StatusPageMonitor } from '@/types/status-page'

import AppSelect from '@/components/AppSelect.vue'
import type { SelectOption } from '@/types/select'

const route = useRoute()
const router = useRouter()

const statusPageStore = useStatusPageStore()
const monitorStore = useMonitorStore()
const organizationStore = useOrganizationStore()

const page = ref<StatusPage | null>(null)
const pageMonitors = ref<StatusPageMonitor[]>([])

const name = ref('')
const published = ref(false)
const monitorToAdd = ref('')

const loading = ref(true)
const loadError = ref<string | null>(null)
const formError = ref<string | null>(null)

const isSaving = ref(false)
const isAddingMonitor = ref(false)
const removingMonitorId = ref<string | null>(null)
const isDeleting = ref(false)

const canManageStatusPage = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin'
})

const availableMonitors = computed(() => {
  const existingIds = new Set(pageMonitors.value.map((monitor) => monitor.id))

  return monitorStore.monitors.filter((monitor) => {
    return !existingIds.has(monitor.id)
  })
})

const availableMonitorOptions =
  computed<SelectOption<string>[]>(() => {
    return [
      {
        value: '',
        label: 'Select monitor',
      },
      ...availableMonitors.value.map((monitor) => {
        return {
          value: monitor.id,
          label: monitor.name,
        }
      }),
    ]
  })

function getPageId(): string | null {
  const pageId = route.params.pageId

  return typeof pageId === 'string' ? pageId : null
}

async function loadPage(): Promise<void> {
  const pageId = getPageId()

  if (!pageId) {
    loadError.value = 'Invalid status page ID'
    loading.value = false
    return
  }

  loading.value = true
  loadError.value = null

  try {
    const [loadedPage, loadedPageMonitors] = await Promise.all([
      statusPageStore.getPage(pageId),
      statusPageStore.getPageMonitors(pageId),
      monitorStore.loadMonitors(),
    ])

    page.value = loadedPage
    pageMonitors.value = loadedPageMonitors

    name.value = loadedPage.name
    published.value = loadedPage.published
  } catch {
    page.value = null
    loadError.value = 'Unable to load status page'
  } finally {
    loading.value = false
  }
}

async function handleSave(): Promise<void> {
  if (!page.value) return

  const trimmedName = name.value.trim()

  if (!trimmedName) {
    formError.value = 'Name is required'
    return
  }

  formError.value = null
  isSaving.value = true

  try {
    page.value = await statusPageStore.updatePage(page.value.id, {
      name: trimmedName,
      published: published.value,
    })
  } catch {
    formError.value = 'Unable to update status page'
  } finally {
    isSaving.value = false
  }
}

async function handleAddMonitor(): Promise<void> {
  if (!page.value || !monitorToAdd.value) {
    return
  }

  isAddingMonitor.value = true
  formError.value = null

  try {
    await statusPageStore.addMonitor(page.value.id, monitorToAdd.value)

    pageMonitors.value = await statusPageStore.getPageMonitors(page.value.id)

    monitorToAdd.value = ''
  } catch {
    formError.value = 'Unable to add monitor'
  } finally {
    isAddingMonitor.value = false
  }
}

async function handleRemoveMonitor(monitor: StatusPageMonitor): Promise<void> {
  if (!page.value) return

  removingMonitorId.value = monitor.id

  try {
    await statusPageStore.removeMonitor(page.value.id, monitor.id)

    pageMonitors.value = pageMonitors.value.filter((item) => {
      return item.id !== monitor.id
    })
  } finally {
    removingMonitorId.value = null
  }
}

async function handleDelete(): Promise<void> {
  if (!page.value) return

  const confirmed = window.confirm(`Delete "${page.value.name}"?`)

  if (!confirmed) return

  isDeleting.value = true

  try {
    await statusPageStore.deletePage(page.value.id)
    await router.push('/status-pages')
  } finally {
    isDeleting.value = false
  }
}

onMounted(async () => {
  await loadPage()
})

watch(
  () => organizationStore.currentOrganizationId,
  async (currentOrganizationId, previousOrganizationId) => {
    if (previousOrganizationId && currentOrganizationId !== previousOrganizationId) {
      await router.push('/status-pages')
    }
  },
)
</script>

<template>
  <section class="status-page-details">
    <RouterLink class="status-page-details__back" to="/status-pages">
      ← Back to status pages
    </RouterLink>

    <p v-if="loading">Loading status page...</p>

    <div v-else-if="loadError" class="message-error">
      {{ loadError }}
    </div>

    <template v-else-if="page">
      <div class="status-page-details__header">
        <div>
          <h1>{{ page.name }}</h1>

          <p>
            Public path:
            <code>/status/{{ page.slug }}</code>
          </p>
        </div>

        <RouterLink
          v-if="page.published"
          class="button-secondary"
          :to="`/status/${page.slug}`"
          target="_blank"
        >
          Open public page
        </RouterLink>
      </div>

      <div v-if="canManageStatusPage" class="section-card">
        <div class="section-header">
          <div>
            <h2>Settings</h2>
            <p>Update page visibility and name.</p>
          </div>
        </div>

        <form class="status-page-form" @submit.prevent="handleSave">
          <div class="form-field">
            <label for="status-page-edit-name"> Name </label>

            <input id="status-page-edit-name" v-model="name" maxlength="100" required />
          </div>

          <div class="form-field">
            <label>Slug</label>

            <input :value="page.slug" disabled />

            <small> Slug cannot be changed after creation. </small>
          </div>

          <label class="form-checkbox">
            <input v-model="published" type="checkbox" />

            Published
          </label>

          <p v-if="formError" class="form-error">
            {{ formError }}
          </p>

          <div class="status-page-form__actions">
            <button
              class="button-danger"
              type="button"
              :disabled="isDeleting"
              @click="handleDelete"
            >
              {{ isDeleting ? 'Deleting...' : 'Delete page' }}
            </button>

            <button class="button-primary" type="submit" :disabled="isSaving">
              {{ isSaving ? 'Saving...' : 'Save changes' }}
            </button>
          </div>
        </form>
      </div>

      <div class="section-card">
        <div class="section-header">
          <div>
            <h2>Monitors</h2>

            <p>Services shown on this status page.</p>
          </div>
        </div>

        <div v-if="canManageStatusPage" class="status-page-monitor-add">
          <AppSelect
            id="status-page-monitor"
            v-model="monitorToAdd"
            :options="availableMonitorOptions"
          />
          <button
            class="button-primary"
            type="button"
            :disabled="!monitorToAdd || isAddingMonitor"
            @click="handleAddMonitor"
          >
            {{ isAddingMonitor ? 'Adding...' : 'Add monitor' }}
          </button>
        </div>

        <p v-if="pageMonitors.length === 0" class="text-muted">No monitors added.</p>

        <div v-else class="status-page-monitor-list">
          <div v-for="monitor in pageMonitors" :key="monitor.id" class="status-page-monitor">
            <div>
              <RouterLink class="text-link" :to="`/monitors/${monitor.id}`">
                {{ monitor.name }}
              </RouterLink>

              <span class="monitor-status" :class="`monitor-status--${monitor.status}`">
                {{ monitor.status }}
              </span>
            </div>

            <button
              v-if="canManageStatusPage"
              class="button-danger"
              type="button"
              :disabled="removingMonitorId === monitor.id"
              @click="handleRemoveMonitor(monitor)"
            >
              {{ removingMonitorId === monitor.id ? 'Removing...' : 'Remove' }}
            </button>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/status-pages';
</style>
