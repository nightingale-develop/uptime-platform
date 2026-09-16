<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { useMaintenanceStore } from '@/stores/maintenance'
import { useMonitorStore } from '@/stores/monitors'
import { useOrganizationStore } from '@/stores/organizations'
import type {
  MaintenanceWindow,
  MaintenanceWindowCreate,
  MaintenanceWindowStatus,
} from '@/types/maintenance'

import { getMaintenanceWindowStatus } from '@/utils/maintenance'

import AppSelect from '@/components/AppSelect.vue'
import type { SelectOption } from '@/types/select'

const monitorOptions = computed<SelectOption<string>[]>(() => {
  return [
    {
      value: '',
      label: 'Select monitor',
      disabled: true,
    },
    ...monitorStore.monitors.map((monitor) => {
      return {
        value: monitor.id,
        label: monitor.name,
      }
    }),
  ]
})

const monitorFilterOptions = computed<SelectOption<string>[]>(() => {
  return [
    {
      value: '',
      label: 'All monitors',
    },
    ...monitorStore.monitors.map((monitor) => {
      return {
        value: monitor.id,
        label: monitor.name,
      }
    }),
  ]
})

const maintenanceStore = useMaintenanceStore()
const monitorStore = useMonitorStore()
const organizationStore = useOrganizationStore()

const monitorFilter = ref('')

const monitorId = ref('')
const startsAt = ref('')
const endsAt = ref('')
const reason = ref('')

const isCreating = ref(false)
const createError = ref<string | null>(null)

const deletingWindowId = ref<string | null>(null)

const canManageMaintenance = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin' || role === 'member'
})

async function loadWindows(): Promise<void> {
  try {
    await maintenanceStore.loadMaintenanceWindows({
      monitor_id: monitorFilter.value || null,
    })
  } catch {
    // Store already contains the error.
  }
}

async function loadPageData(): Promise<void> {
  await Promise.all([monitorStore.loadMonitors(), loadWindows()])
}

function getMonitorName(monitorId: string): string {
  const monitor = monitorStore.monitors.find((monitor) => {
    return monitor.id === monitorId
  })

  return monitor?.name ?? monitorId
}

function getStatusLabel(status: MaintenanceWindowStatus): string {
  switch (status) {
    case 'upcoming':
      return 'Upcoming'

    case 'active':
      return 'Active'

    case 'expired':
      return 'Expired'
  }
}

function resetForm(): void {
  monitorId.value = ''
  startsAt.value = ''
  endsAt.value = ''
  reason.value = ''
}

async function handleCreate(): Promise<void> {
  createError.value = null

  if (!monitorId.value || !startsAt.value || !endsAt.value) {
    createError.value = 'Monitor, start time and end time are required'
    return
  }

  const startDate = new Date(startsAt.value)
  const endDate = new Date(endsAt.value)

  if (endDate <= startDate) {
    createError.value = 'End time must be later than start time'
    return
  }

  const data: MaintenanceWindowCreate = {
    monitor_id: monitorId.value,
    starts_at: startDate.toISOString(),
    ends_at: endDate.toISOString(),
    reason: reason.value.trim() || null,
  }

  isCreating.value = true

  try {
    await maintenanceStore.createMaintenanceWindow(data)

    resetForm()
    await loadWindows()
  } catch {
    createError.value = 'Unable to create maintenance window'
  } finally {
    isCreating.value = false
  }
}

async function handleDelete(maintenanceWindow: MaintenanceWindow): Promise<void> {
  const confirmed = window.confirm('Delete this maintenance window?')

  if (!confirmed) {
    return
  }

  deletingWindowId.value = maintenanceWindow.id

  try {
    await maintenanceStore.deleteMaintenanceWindow(maintenanceWindow.id)
  } finally {
    deletingWindowId.value = null
  }
}

onMounted(async () => {
  await loadPageData()
})

watch(monitorFilter, async () => {
  await loadWindows()
})

watch(
  () => organizationStore.currentOrganizationId,
  async (currentOrganizationId, previousOrganizationId) => {
    if (previousOrganizationId && currentOrganizationId !== previousOrganizationId) {
      monitorFilter.value = ''
      resetForm()

      await loadPageData()
    }
  },
)
</script>

<template>
  <section class="maintenance-page">
    <div class="maintenance-page__header">
      <div>
        <h1>Maintenance</h1>

        <p>Schedule periods when monitor state changes should be suppressed.</p>
      </div>
    </div>

    <div v-if="canManageMaintenance" class="section-card maintenance-form-card">
      <div class="section-header">
        <div>
          <h2>Schedule maintenance</h2>

          <p>Create a maintenance window for a monitor.</p>
        </div>
      </div>

      <form class="maintenance-form" @submit.prevent="handleCreate">
        <div class="form-grid">
          <div class="form-field">
            <label for="maintenance-monitor"> Monitor </label>
            <AppSelect id="maintenance-monitor" v-model="monitorId" :options="monitorOptions" />
          </div>

          <div />

          <div class="form-field">
            <label for="maintenance-start"> Starts at </label>

            <input id="maintenance-start" v-model="startsAt" type="datetime-local" required />
          </div>

          <div class="form-field">
            <label for="maintenance-end"> Ends at </label>

            <input id="maintenance-end" v-model="endsAt" type="datetime-local" required />
          </div>
        </div>

        <div class="form-field">
          <label for="maintenance-reason"> Reason </label>

          <textarea
            id="maintenance-reason"
            v-model="reason"
            maxlength="500"
            rows="3"
            placeholder="Database maintenance, deployment..."
          />

          <small> {{ reason.length }}/500 </small>
        </div>

        <p v-if="createError" class="form-error">
          {{ createError }}
        </p>

        <div class="maintenance-form__actions">
          <button class="button-primary" type="submit" :disabled="isCreating">
            {{ isCreating ? 'Creating...' : 'Schedule maintenance' }}
          </button>
        </div>
      </form>
    </div>

    <div class="maintenance-filters">
      <div class="filter-field">
        <label for="maintenance-filter-monitor"> Monitor </label>
        <AppSelect
          id="maintenance-filter-monitor"
          v-model="monitorFilter"
          :options="monitorFilterOptions"
        />
      </div>
    </div>

    <div v-if="maintenanceStore.error" class="message-error">
      {{ maintenanceStore.error }}
    </div>

    <p v-else-if="maintenanceStore.loading" class="text-muted">Loading maintenance windows...</p>

    <div v-else-if="maintenanceStore.windows.length === 0" class="maintenance-page__empty">
      <h2>No maintenance windows</h2>

      <p>No maintenance windows match the selected monitor.</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Monitor</th>
            <th>Starts</th>
            <th>Ends</th>
            <th>Reason</th>

            <th v-if="canManageMaintenance">Actions</th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="maintenanceWindow in maintenanceStore.windows" :key="maintenanceWindow.id">
            <td>
              <span
                class="maintenance-status"
                :class="`maintenance-status--${getMaintenanceWindowStatus(maintenanceWindow)}`"
              >
                {{ getStatusLabel(getMaintenanceWindowStatus(maintenanceWindow)) }}
              </span>
            </td>

            <td>
              <RouterLink class="text-link" :to="`/monitors/${maintenanceWindow.monitor_id}`">
                {{ getMonitorName(maintenanceWindow.monitor_id) }}
              </RouterLink>
            </td>

            <td>
              {{ new Date(maintenanceWindow.starts_at).toLocaleString() }}
            </td>

            <td>
              {{ new Date(maintenanceWindow.ends_at).toLocaleString() }}
            </td>

            <td>
              {{ maintenanceWindow.reason ?? '—' }}
            </td>

            <td v-if="canManageMaintenance">
              <button
                class="button-danger"
                type="button"
                :disabled="deletingWindowId === maintenanceWindow.id"
                @click="handleDelete(maintenanceWindow)"
              >
                {{ deletingWindowId === maintenanceWindow.id ? 'Deleting...' : 'Delete' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/maintenance';
</style>
