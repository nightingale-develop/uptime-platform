<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMaintenanceStore } from '@/stores/maintenance'
import type { MaintenanceWindow } from '@/types/maintenance'
import { getMaintenanceWindowStatus } from '@/utils/maintenance'

import { useMonitorStore } from '@/stores/monitors'
import { useOrganizationStore } from '@/stores/organizations'
import type {
  Check,
  Monitor,
  MonitorStatistics,
  MonitorStatus,
  StatisticsPeriod,
} from '@/types/monitor'

import { useIncidentStore } from '@/stores/incidents'
import type { Incident } from '@/types/incident'

const route = useRoute()
const router = useRouter()

const monitorStore = useMonitorStore()
const incidentStore = useIncidentStore()
const organizationStore = useOrganizationStore()
const maintenanceStore = useMaintenanceStore()

const monitorIncidents = ref<Incident[]>([])
const incidentsLoading = ref(false)
const incidentsError = ref<string | null>(null)
const maintenanceWindows = ref<MaintenanceWindow[]>([])
const maintenanceLoading = ref(false)
const maintenanceError = ref<string | null>(null)

const now = ref(Date.now())

let clockIntervalId: number | null = null

const monitor = ref<Monitor | null>(null)
const lastManualCheck = ref<Check | null>(null)

const checks = ref<Check[]>([])

const statistics = ref<MonitorStatistics | null>(null)
const statisticsPeriod = ref<StatisticsPeriod>('24h')

const statisticsLoading = ref(false)
const statisticsError = ref<string | null>(null)

const checksLoading = ref(false)
const checksError = ref<string | null>(null)

const loading = ref(true)
const loadError = ref<string | null>(null)

const isRunningCheck = ref(false)
const checkError = ref<string | null>(null)

const canManageMonitor = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin' || role === 'member'
})

const relevantMaintenanceWindows = computed(() => {
  return maintenanceWindows.value
    .filter((maintenanceWindow) => {
      const status = getMaintenanceWindowStatus(maintenanceWindow, now.value)

      return status !== 'expired'
    })
    .sort((first, second) => {
      return new Date(first.starts_at).getTime() - new Date(second.starts_at).getTime()
    })
    .slice(0, 3)
})

function getMonitorId(): string | null {
  const monitorId = route.params.monitorId

  if (typeof monitorId !== 'string') {
    return null
  }

  return monitorId
}

async function loadMonitorMaintenance(): Promise<void> {
  const monitorId = getMonitorId()

  if (!monitorId) {
    return
  }

  maintenanceLoading.value = true
  maintenanceError.value = null

  try {
    maintenanceWindows.value = await maintenanceStore.getMaintenanceWindows({
      monitor_id: monitorId,
    })
  } catch {
    maintenanceWindows.value = []
    maintenanceError.value = 'Unable to load maintenance windows'
  } finally {
    maintenanceLoading.value = false
  }
}

function getMonitorTarget(monitor: Monitor): string {
  switch (monitor.monitor_type) {
    case 'http':
      return monitor.config.url

    case 'tcp':
    case 'tls':
      return `${monitor.config.host}:${monitor.config.port}`

    case 'dns':
      return `${monitor.config.host} (${monitor.config.record_type})`

    case 'icmp':
      return monitor.config.host
  }
}

function getStatusLabel(status: MonitorStatus): string {
  switch (status) {
    case 'up':
      return 'Up'

    case 'down':
      return 'Down'

    case 'pending':
      return 'Pending'

    case 'paused':
      return 'Paused'
  }
}

async function loadMonitor(): Promise<void> {
  const monitorId = getMonitorId()

  if (!monitorId) {
    loadError.value = 'Invalid monitor ID'
    loading.value = false
    return
  }

  loading.value = true
  loadError.value = null

  try {
    monitor.value = await monitorStore.getMonitor(monitorId)
  } catch {
    monitor.value = null
    loadError.value = 'Unable to load monitor'
  } finally {
    loading.value = false
  }
}

async function loadChecks(): Promise<void> {
  const monitorId = getMonitorId()

  if (!monitorId) {
    return
  }

  checksLoading.value = true
  checksError.value = null

  try {
    checks.value = await monitorStore.getMonitorChecks(monitorId, 50)
  } catch {
    checks.value = []
    checksError.value = 'Unable to load check history'
  } finally {
    checksLoading.value = false
  }
}

async function runCheck(): Promise<void> {
  if (!monitor.value) {
    return
  }

  checkError.value = null
  isRunningCheck.value = true

  try {
    lastManualCheck.value = await monitorStore.runMonitorCheck(monitor.value.id)

    await loadMonitor()

    await Promise.all([loadChecks(), loadStatistics(), loadMonitorIncidents()])
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail

      if (typeof detail === 'string') {
        checkError.value = detail
      } else {
        checkError.value = 'Unable to run monitor check'
      }
    } else {
      checkError.value = 'Unable to run monitor check'
    }
  } finally {
    isRunningCheck.value = false
  }
}

async function loadStatistics(): Promise<void> {
  const monitorId = getMonitorId()

  if (!monitorId) {
    return
  }

  statisticsLoading.value = true
  statisticsError.value = null

  try {
    statistics.value = await monitorStore.getMonitorStatistics(monitorId, statisticsPeriod.value)
  } catch {
    statistics.value = null
    statisticsError.value = 'Unable to load statistics'
  } finally {
    statisticsLoading.value = false
  }
}

async function loadMonitorIncidents(): Promise<void> {
  const monitorId = getMonitorId()

  if (!monitorId) {
    return
  }

  incidentsLoading.value = true
  incidentsError.value = null

  try {
    monitorIncidents.value = await incidentStore.getIncidents({
      monitor_id: monitorId,
      limit: 5,
    })
  } catch {
    monitorIncidents.value = []
    incidentsError.value = 'Unable to load incidents'
  } finally {
    incidentsLoading.value = false
  }
}

onMounted(async () => {
  clockIntervalId = window.setInterval(() => {
    now.value = Date.now()
  }, 60_000)

  await loadMonitor()

  if (monitor.value) {
    await Promise.all([
      loadChecks(),
      loadStatistics(),
      loadMonitorIncidents(),
      loadMonitorMaintenance(),
    ])
  }
})

onUnmounted(() => {
  if (clockIntervalId !== null) {
    window.clearInterval(clockIntervalId)
  }
})

watch(
  () => organizationStore.currentOrganizationId,
  async (currentOrganizationId, previousOrganizationId) => {
    if (previousOrganizationId && currentOrganizationId !== previousOrganizationId) {
      await router.push('/monitors')
    }
  },
)

watch(statisticsPeriod, async () => {
  await loadStatistics()
})
</script>

<template>
  <section class="monitor-details">
    <div class="monitor-details__top">
      <RouterLink class="monitor-details__back" to="/monitors"> ← Back to monitors </RouterLink>
    </div>

    <p v-if="loading">Loading monitor...</p>

    <div v-else-if="loadError" class="message-error">
      {{ loadError }}
    </div>

    <template v-else-if="monitor">
      <div class="monitor-details__header">
        <div>
          <div class="monitor-details__title">
            <h1>{{ monitor.name }}</h1>

            <span class="monitor-status" :class="`monitor-status--${monitor.status}`">
              {{ getStatusLabel(monitor.status) }}
            </span>
          </div>

          <p class="monitor-details__target">
            {{ getMonitorTarget(monitor) }}
          </p>
        </div>

        <div class="monitor-details__actions">
          <RouterLink
            v-if="canManageMonitor"
            class="button-secondary"
            :to="`/monitors/${monitor.id}/edit`"
          >
            Edit
          </RouterLink>

          <button
            v-if="canManageMonitor"
            class="button-primary"
            type="button"
            :disabled="isRunningCheck"
            @click="runCheck"
          >
            {{ isRunningCheck ? 'Running...' : 'Run check' }}
          </button>
        </div>
      </div>

      <div class="monitor-summary">
        <div class="summary-card">
          <span class="summary-card__label"> Type </span>

          <strong>
            {{ monitor.monitor_type.toUpperCase() }}
          </strong>
        </div>

        <div class="summary-card">
          <span class="summary-card__label"> Interval </span>

          <strong> {{ monitor.interval_seconds }}s </strong>
        </div>

        <div class="summary-card">
          <span class="summary-card__label"> Timeout </span>

          <strong> {{ monitor.timeout_seconds }}s </strong>
        </div>

        <div class="summary-card">
          <span class="summary-card__label"> Next check </span>

          <strong>
            {{ new Date(monitor.next_check_at).toLocaleString() }}
          </strong>
        </div>
      </div>

      <div class="monitor-details__grid">
        <div class="details-card">
          <h2>Check settings</h2>

          <dl>
            <div>
              <dt>Failure threshold</dt>
              <dd>{{ monitor.failure_threshold }}</dd>
            </div>

            <div>
              <dt>Recovery threshold</dt>
              <dd>{{ monitor.recovery_threshold }}</dd>
            </div>

            <div>
              <dt>Consecutive failures</dt>
              <dd>{{ monitor.consecutive_failures }}</dd>
            </div>

            <div>
              <dt>Consecutive successes</dt>
              <dd>{{ monitor.consecutive_successes }}</dd>
            </div>

            <div>
              <dt>Created</dt>
              <dd>
                {{ new Date(monitor.created_at).toLocaleString() }}
              </dd>
            </div>
          </dl>
        </div>

        <div class="details-card">
          <h2>Configuration</h2>

          <dl v-if="monitor.monitor_type === 'http'">
            <div>
              <dt>URL</dt>
              <dd>{{ monitor.config.url }}</dd>
            </div>

            <div>
              <dt>Method</dt>
              <dd>{{ monitor.config.method }}</dd>
            </div>

            <div>
              <dt>Expected status codes</dt>
              <dd>
                {{ monitor.config.expected_status_codes?.join(', ') ?? 'Default' }}
              </dd>
            </div>

            <div>
              <dt>Body contains</dt>
              <dd>{{ monitor.config.body_contains ?? '—' }}</dd>
            </div>

            <div>
              <dt>Follow redirects</dt>
              <dd>
                {{ monitor.config.follow_redirects ? 'Yes' : 'No' }}
              </dd>
            </div>

            <div>
              <dt>Verify TLS</dt>
              <dd>
                {{ monitor.config.verify_tls ? 'Yes' : 'No' }}
              </dd>
            </div>
          </dl>

          <dl v-else-if="monitor.monitor_type === 'tcp'">
            <div>
              <dt>Host</dt>
              <dd>{{ monitor.config.host }}</dd>
            </div>

            <div>
              <dt>Port</dt>
              <dd>{{ monitor.config.port }}</dd>
            </div>
          </dl>

          <dl v-else-if="monitor.monitor_type === 'dns'">
            <div>
              <dt>Host</dt>
              <dd>{{ monitor.config.host }}</dd>
            </div>

            <div>
              <dt>Record type</dt>
              <dd>{{ monitor.config.record_type }}</dd>
            </div>
          </dl>

          <dl v-else-if="monitor.monitor_type === 'tls'">
            <div>
              <dt>Host</dt>
              <dd>{{ monitor.config.host }}</dd>
            </div>

            <div>
              <dt>Port</dt>
              <dd>{{ monitor.config.port }}</dd>
            </div>

            <div>
              <dt>Expiry threshold</dt>
              <dd>{{ monitor.config.expiry_threshold_days }} days</dd>
            </div>
          </dl>

          <dl v-else-if="monitor.monitor_type === 'icmp'">
            <div>
              <dt>Host</dt>
              <dd>{{ monitor.config.host }}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div v-if="checkError" class="message-error">
        {{ checkError }}
      </div>

      <div
        v-if="lastManualCheck"
        class="check-result"
        :class="{
          'check-result--success': lastManualCheck.success,
          'check-result--failure': !lastManualCheck.success,
        }"
      >
        <div class="check-result__header">
          <h2>Manual check result</h2>

          <strong>
            {{ lastManualCheck.success ? 'Successful' : 'Failed' }}
          </strong>
        </div>

        <dl>
          <div>
            <dt>Response time</dt>
            <dd>{{ lastManualCheck.response_time_ms.toFixed(2) }} ms</dd>
          </div>

          <div>
            <dt>Status code</dt>
            <dd>
              {{ lastManualCheck.status_code ?? '—' }}
            </dd>
          </div>

          <div>
            <dt>Checked at</dt>
            <dd>
              {{ new Date(lastManualCheck.checked_at).toLocaleString() }}
            </dd>
          </div>

          <div v-if="lastManualCheck.error">
            <dt>Error</dt>
            <dd>{{ lastManualCheck.error }}</dd>
          </div>
        </dl>
      </div>

      <div class="statistics">
        <div class="statistics__header">
          <div>
            <h2>Statistics</h2>

            <p>Monitor performance for the selected period.</p>
          </div>

          <div class="statistics__periods">
            <button
              type="button"
              class="period-button"
              :class="{
                'period-button--active': statisticsPeriod === '24h',
              }"
              @click="statisticsPeriod = '24h'"
            >
              24 hours
            </button>

            <button
              type="button"
              class="period-button"
              :class="{
                'period-button--active': statisticsPeriod === '7d',
              }"
              @click="statisticsPeriod = '7d'"
            >
              7 days
            </button>

            <button
              type="button"
              class="period-button"
              :class="{
                'period-button--active': statisticsPeriod === '30d',
              }"
              @click="statisticsPeriod = '30d'"
            >
              30 days
            </button>
          </div>
        </div>

        <p
          v-if="statistics?.is_partial && !statisticsError"
          class="statistics__coverage"
          role="status"
        >
          <template v-if="statistics.first_check_at && statistics.last_check_at">
            Incomplete history for this period. Figures use available checks from
            {{ new Date(statistics.first_check_at).toLocaleString() }} to
            {{ new Date(statistics.last_check_at).toLocaleString() }}.
          </template>
          <template v-else>No check data is available for this period.</template>
        </p>

        <p v-if="statisticsLoading && !statistics" class="statistics__message">
          Loading statistics...
        </p>

        <div v-else-if="statisticsError" class="message-error">
          {{ statisticsError }}
        </div>

        <div v-else-if="statistics" class="statistics__cards">
          <div class="statistics-card">
            <span>{{ statistics.is_partial ? 'Uptime (available checks)' : 'Uptime' }}</span>

            <strong>
              {{
                statistics.uptime_percentage !== null
                  ? `${statistics.uptime_percentage.toFixed(2)}%`
                  : '—'
              }}
            </strong>
          </div>

          <div class="statistics-card">
            <span>Total checks</span>

            <strong>
              {{ statistics.total_checks }}
            </strong>
          </div>

          <div class="statistics-card">
            <span>Successful</span>

            <strong>
              {{ statistics.successful_checks }}
            </strong>
          </div>

          <div class="statistics-card">
            <span>Failed</span>

            <strong>
              {{ statistics.failed_checks }}
            </strong>
          </div>

          <div class="statistics-card">
            <span>Average response</span>

            <strong>
              {{
                statistics.average_response_time_ms !== null
                  ? `${statistics.average_response_time_ms.toFixed(2)} ms`
                  : '—'
              }}
            </strong>
          </div>
        </div>
      </div>

      <div class="section-card monitor-maintenance">
        <div class="section-header">
          <div>
            <h2>Maintenance</h2>

            <p>Active and upcoming maintenance windows.</p>
          </div>

          <RouterLink class="text-link" to="/maintenance"> View maintenance </RouterLink>
        </div>

        <p v-if="maintenanceLoading && maintenanceWindows.length === 0" class="text-muted">
          Loading maintenance...
        </p>

        <div v-else-if="maintenanceError" class="message-error">
          {{ maintenanceError }}
        </div>

        <p v-else-if="relevantMaintenanceWindows.length === 0" class="text-muted">
          No active or upcoming maintenance.
        </p>

        <div v-else class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Starts</th>
                <th>Ends</th>
                <th>Reason</th>
              </tr>
            </thead>

            <tbody>
              <tr
                v-for="maintenanceWindow in relevantMaintenanceWindows"
                :key="maintenanceWindow.id"
              >
                <td>
                  <span
                    class="maintenance-status"
                    :class="`maintenance-status--${getMaintenanceWindowStatus(
                      maintenanceWindow,
                      now,
                    )}`"
                  >
                    {{
                      getMaintenanceWindowStatus(maintenanceWindow, now) === 'active'
                        ? 'Active'
                        : 'Upcoming'
                    }}
                  </span>
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
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="section-card monitor-incidents">
        <div class="section-header">
          <div>
            <h2>Incidents</h2>

            <p>Incidents associated with this monitor.</p>
          </div>

          <RouterLink class="text-link" to="/incidents"> View all </RouterLink>
        </div>

        <p v-if="incidentsLoading && monitorIncidents.length === 0" class="text-muted">
          Loading incidents...
        </p>

        <div v-else-if="incidentsError" class="message-error">
          {{ incidentsError }}
        </div>

        <p v-else-if="monitorIncidents.length === 0" class="text-muted">
          No incidents have been recorded for this monitor.
        </p>

        <div v-else class="table-wrapper">
          <table class="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Started</th>
                <th>Resolved</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="incident in monitorIncidents" :key="incident.id">
                <td>
                  <RouterLink :to="`/incidents/${incident.id}`">
                    <span class="incident-status" :class="`incident-status--${incident.status}`">
                      {{ incident.status === 'open' ? 'Open' : 'Resolved' }}
                    </span>
                  </RouterLink>
                </td>

                <td>
                  {{ new Date(incident.started_at).toLocaleString() }}
                </td>

                <td>
                  {{ incident.resolved_at ? new Date(incident.resolved_at).toLocaleString() : '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="check-history">
        <div class="check-history__header">
          <div>
            <h2>Check history</h2>

            <p>Latest monitor checks.</p>
          </div>

          <button
            class="button-secondary"
            type="button"
            :disabled="checksLoading"
            @click="loadChecks"
          >
            {{ checksLoading ? 'Refreshing...' : 'Refresh' }}
          </button>
        </div>

        <p v-if="checksLoading && checks.length === 0" class="check-history__message">
          Loading check history...
        </p>

        <div v-else-if="checksError" class="message-error">
          {{ checksError }}
        </div>

        <div v-else-if="checks.length === 0" class="check-history__empty">
          No checks have been recorded yet.
        </div>

        <div v-else class="check-history__table-wrapper">
          <table class="check-history__table">
            <thead>
              <tr>
                <th>Checked at</th>
                <th>Result</th>
                <th>Response time</th>
                <th>Status code</th>
                <th>Error</th>
              </tr>
            </thead>

            <tbody>
              <tr v-for="check in checks" :key="check.id">
                <td>
                  {{ new Date(check.checked_at).toLocaleString() }}
                </td>

                <td>
                  <span
                    class="check-status"
                    :class="{
                      'check-status--success': check.success,
                      'check-status--failure': !check.success,
                    }"
                  >
                    {{ check.success ? 'Success' : 'Failed' }}
                  </span>
                </td>

                <td>{{ check.response_time_ms.toFixed(2) }} ms</td>

                <td>
                  {{ check.status_code ?? '—' }}
                </td>

                <td class="check-history__error-cell">
                  {{ check.error ?? '—' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/monitor-details';
</style>
