<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMonitorStore } from '@/stores/monitors'
import { useOrganizationStore } from '@/stores/organizations'
import type { DnsRecordType, HttpMethod, Monitor, MonitorUpdate } from '@/types/monitor'

import AppSelect from '@/components/AppSelect.vue'
import type { SelectOption } from '@/types/select'

const route = useRoute()
const router = useRouter()

const monitorStore = useMonitorStore()
const organizationStore = useOrganizationStore()

const monitor = ref<Monitor | null>(null)

const name = ref('')

const intervalSeconds = ref(60)
const timeoutSeconds = ref(5)
const failureThreshold = ref(3)
const recoveryThreshold = ref(2)

const httpUrl = ref('')
const httpMethod = ref<HttpMethod>('GET')
const expectedStatusCodes = ref('')
const bodyContains = ref('')
const followRedirects = ref(false)
const verifyTls = ref(true)

const tcpHost = ref('')
const tcpPort = ref(80)

const dnsHost = ref('')
const dnsRecordType = ref<DnsRecordType>('A')

const tlsHost = ref('')
const tlsPort = ref(443)
const tlsExpiryThresholdDays = ref(14)

const icmpHost = ref('')

const loading = ref(true)
const isSubmitting = ref(false)
const isDeleting = ref(false)
const loadError = ref<string | null>(null)
const errorMessage = ref<string | null>(null)

const canUpdateMonitor = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin' || role === 'member'
})

const httpMethodOptions: SelectOption<HttpMethod>[] = [
  { value: 'GET', label: 'GET' },
  { value: 'HEAD', label: 'HEAD' },
]

const dnsRecordTypeOptions: SelectOption<DnsRecordType>[] = [
  { value: 'A', label: 'A' },
  { value: 'AAAA', label: 'AAAA' },
  { value: 'CNAME', label: 'CNAME' },
  { value: 'MX', label: 'MX' },
  { value: 'TXT', label: 'TXT' },
]

watch(httpMethod, (method) => {
  if (method === 'HEAD') {
    bodyContains.value = ''
  }
})

function populateForm(loadedMonitor: Monitor): void {
  name.value = loadedMonitor.name

  intervalSeconds.value = loadedMonitor.interval_seconds
  timeoutSeconds.value = loadedMonitor.timeout_seconds
  failureThreshold.value = loadedMonitor.failure_threshold
  recoveryThreshold.value = loadedMonitor.recovery_threshold

  switch (loadedMonitor.monitor_type) {
    case 'http':
      httpUrl.value = loadedMonitor.config.url
      httpMethod.value = loadedMonitor.config.method

      expectedStatusCodes.value = loadedMonitor.config.expected_status_codes?.join(', ') ?? ''

      bodyContains.value = loadedMonitor.config.body_contains ?? ''

      followRedirects.value = loadedMonitor.config.follow_redirects

      verifyTls.value = loadedMonitor.config.verify_tls

      break

    case 'tcp':
      tcpHost.value = loadedMonitor.config.host
      tcpPort.value = loadedMonitor.config.port
      break

    case 'dns':
      dnsHost.value = loadedMonitor.config.host
      dnsRecordType.value = loadedMonitor.config.record_type
      break

    case 'tls':
      tlsHost.value = loadedMonitor.config.host
      tlsPort.value = loadedMonitor.config.port

      tlsExpiryThresholdDays.value = loadedMonitor.config.expiry_threshold_days

      break

    case 'icmp':
      icmpHost.value = loadedMonitor.config.host
      break
  }
}

async function loadMonitor(): Promise<void> {
  loading.value = true
  loadError.value = null

  const monitorId = route.params.monitorId

  if (typeof monitorId !== 'string') {
    loadError.value = 'Invalid monitor ID'
    loading.value = false
    return
  }

  try {
    const loadedMonitor = await monitorStore.getMonitor(monitorId)

    monitor.value = loadedMonitor

    populateForm(loadedMonitor)
  } catch {
    loadError.value = 'Unable to load monitor'
  } finally {
    loading.value = false
  }
}

function parseExpectedStatusCodes(): number[] | null {
  const value = expectedStatusCodes.value.trim()

  if (!value) {
    return null
  }

  const statusCodes = value.split(',').map((statusCode) => {
    return Number(statusCode.trim())
  })

  const hasInvalidStatusCode = statusCodes.some((statusCode) => {
    return !Number.isInteger(statusCode) || statusCode < 100 || statusCode > 599
  })

  if (hasInvalidStatusCode) {
    throw new Error('Expected status codes must be numbers between 100 and 599')
  }

  return statusCodes
}

function buildMonitorUpdate(): MonitorUpdate {
  if (!monitor.value) {
    throw new Error('Monitor is not loaded')
  }

  const base: MonitorUpdate = {
    name: name.value.trim(),
    interval_seconds: intervalSeconds.value,
    timeout_seconds: timeoutSeconds.value,
    failure_threshold: failureThreshold.value,
    recovery_threshold: recoveryThreshold.value,
  }

  switch (monitor.value.monitor_type) {
    case 'http':
      return {
        ...base,
        config: {
          url: httpUrl.value.trim(),
          method: httpMethod.value,
          expected_status_codes: parseExpectedStatusCodes(),
          body_contains: httpMethod.value === 'HEAD' ? null : bodyContains.value.trim() || null,
          follow_redirects: followRedirects.value,
          verify_tls: verifyTls.value,
        },
      }

    case 'tcp':
      return {
        ...base,
        config: {
          host: tcpHost.value.trim(),
          port: tcpPort.value,
        },
      }

    case 'dns':
      return {
        ...base,
        config: {
          host: dnsHost.value.trim(),
          record_type: dnsRecordType.value,
        },
      }

    case 'tls':
      return {
        ...base,
        config: {
          host: tlsHost.value.trim(),
          port: tlsPort.value,
          expiry_threshold_days: tlsExpiryThresholdDays.value,
        },
      }

    case 'icmp':
      return {
        ...base,
        config: {
          host: icmpHost.value.trim(),
        },
      }
  }
}

async function submitMonitor(): Promise<void> {
  if (!monitor.value) {
    return
  }

  errorMessage.value = null
  isSubmitting.value = true

  try {
    const data = buildMonitorUpdate()

    await monitorStore.updateMonitor(monitor.value.id, data)

    await router.push('/monitors')
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail

      if (typeof detail === 'string') {
        errorMessage.value = detail
      } else if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
        errorMessage.value = detail[0].msg
      } else {
        errorMessage.value = 'Unable to update monitor'
      }
    } else if (error instanceof Error) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = 'Unable to update monitor'
    }
  } finally {
    isSubmitting.value = false
  }
}

async function handleDeleteMonitor(): Promise<void> {
  if (!monitor.value) {
    return
  }

  const confirmed = window.confirm(
    `Delete monitor "${monitor.value.name}"? This action cannot be undone.`,
  )

  if (!confirmed) {
    return
  }

  errorMessage.value = null
  isDeleting.value = true

  try {
    await monitorStore.deleteMonitor(monitor.value.id)

    await router.push('/monitors')
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail

      if (typeof detail === 'string') {
        errorMessage.value = detail
      } else {
        errorMessage.value = 'Unable to delete monitor'
      }
    } else {
      errorMessage.value = 'Unable to delete monitor'
    }
  } finally {
    isDeleting.value = false
  }
}

onMounted(async () => {
  await loadMonitor()
})
</script>

<template>
  <section class="monitor-edit">
    <div class="monitor-edit__header">
      <div>
        <h1>Edit monitor</h1>

        <p>Update monitor configuration and check settings.</p>
      </div>

      <RouterLink class="monitor-edit__back" to="/monitors"> Back to monitors </RouterLink>
    </div>

    <p v-if="loading">Loading monitor...</p>

    <div v-else-if="loadError" class="monitor-edit__error">
      {{ loadError }}
    </div>

    <div v-else-if="!canUpdateMonitor" class="monitor-edit__forbidden">
      Your organization role does not allow updating monitors.
    </div>

    <form v-else-if="monitor" class="monitor-form" @submit.prevent="submitMonitor">
      <div class="form-section">
        <h2>General</h2>

        <div class="form-field">
          <label for="name"> Name </label>

          <input id="name" v-model.trim="name" type="text" maxlength="100" required />
        </div>

        <div class="form-field">
          <label> Monitor type </label>

          <input :value="monitor.monitor_type.toUpperCase()" type="text" disabled />

          <small> Monitor type cannot be changed after creation. </small>
        </div>
      </div>

      <div class="form-section">
        <h2>Target</h2>

        <template v-if="monitor.monitor_type === 'http'">
          <div class="form-field">
            <label for="http-url"> URL </label>

            <input id="http-url" v-model.trim="httpUrl" type="url" required />
          </div>

          <div class="form-field">
            <label for="http-method"> Method </label>
            <AppSelect id="monitor-type" v-model="httpMethod" :options="httpMethodOptions" />
          </div>

          <div class="form-field">
            <label for="expected-status-codes"> Expected status codes </label>

            <input
              id="expected-status-codes"
              v-model.trim="expectedStatusCodes"
              type="text"
              placeholder="200, 204"
            />
          </div>

          <div v-if="httpMethod !== 'HEAD'" class="form-field">
            <label for="body-contains"> Response body contains </label>

            <input id="body-contains" v-model="bodyContains" type="text" maxlength="4096" />
          </div>

          <label class="form-checkbox">
            <input v-model="followRedirects" type="checkbox" />

            Follow redirects
          </label>

          <label class="form-checkbox">
            <input v-model="verifyTls" type="checkbox" />

            Verify TLS certificate
          </label>
        </template>

        <template v-else-if="monitor.monitor_type === 'tcp'">
          <div class="form-grid">
            <div class="form-field">
              <label for="tcp-host"> Host </label>

              <input id="tcp-host" v-model.trim="tcpHost" type="text" maxlength="255" required />
            </div>

            <div class="form-field">
              <label for="tcp-port"> Port </label>

              <input
                id="tcp-port"
                v-model.number="tcpPort"
                type="number"
                min="1"
                max="65535"
                required
              />
            </div>
          </div>
        </template>

        <template v-else-if="monitor.monitor_type === 'dns'">
          <div class="form-grid">
            <div class="form-field">
              <label for="dns-host"> Host </label>

              <input id="dns-host" v-model.trim="dnsHost" type="text" maxlength="253" required />
            </div>

            <div class="form-field">
              <label for="dns-record-type"> Record type </label>
              <AppSelect
                id="monitor-type"
                v-model="dnsRecordType"
                :options="dnsRecordTypeOptions"
              />
            </div>
          </div>
        </template>

        <template v-else-if="monitor.monitor_type === 'tls'">
          <div class="form-grid">
            <div class="form-field">
              <label for="tls-host"> Host </label>

              <input id="tls-host" v-model.trim="tlsHost" type="text" maxlength="253" required />
            </div>

            <div class="form-field">
              <label for="tls-port"> Port </label>

              <input
                id="tls-port"
                v-model.number="tlsPort"
                type="number"
                min="1"
                max="65535"
                required
              />
            </div>
          </div>

          <div class="form-field">
            <label for="tls-expiry-threshold"> Expiry threshold </label>

            <input
              id="tls-expiry-threshold"
              v-model.number="tlsExpiryThresholdDays"
              type="number"
              min="0"
              max="365"
              required
            />

            <small> Days before certificate expiration. </small>
          </div>
        </template>

        <template v-else-if="monitor.monitor_type === 'icmp'">
          <div class="form-field">
            <label for="icmp-host"> Host </label>

            <input id="icmp-host" v-model.trim="icmpHost" type="text" maxlength="253" required />
          </div>
        </template>
      </div>

      <div class="form-section">
        <h2>Check settings</h2>

        <div class="form-grid">
          <div class="form-field">
            <label for="interval"> Interval </label>

            <input
              id="interval"
              v-model.number="intervalSeconds"
              type="number"
              min="10"
              max="3600"
              required
            />

            <small>Seconds between checks.</small>
          </div>

          <div class="form-field">
            <label for="timeout"> Timeout </label>

            <input
              id="timeout"
              v-model.number="timeoutSeconds"
              type="number"
              min="1"
              max="60"
              required
            />

            <small>Maximum check duration in seconds.</small>
          </div>

          <div class="form-field">
            <label for="failure-threshold"> Failure threshold </label>

            <input
              id="failure-threshold"
              v-model.number="failureThreshold"
              type="number"
              min="1"
              max="10"
              required
            />
          </div>

          <div class="form-field">
            <label for="recovery-threshold"> Recovery threshold </label>

            <input
              id="recovery-threshold"
              v-model.number="recoveryThreshold"
              type="number"
              min="1"
              max="10"
              required
            />
          </div>
        </div>
      </div>

      <p v-if="errorMessage" class="form-error" role="alert">
        {{ errorMessage }}
      </p>

      <div class="monitor-form__actions">
        <button
          class="button-danger"
          type="button"
          :disabled="isSubmitting || isDeleting"
          @click="handleDeleteMonitor"
        >
          {{ isDeleting ? 'Deleting...' : 'Delete monitor' }}
        </button>

        <div class="monitor-form__actions-right">
          <RouterLink class="button-secondary" to="/monitors"> Cancel </RouterLink>

          <button class="button-primary" type="submit" :disabled="isSubmitting || isDeleting">
            {{ isSubmitting ? 'Saving...' : 'Save changes' }}
          </button>
        </div>
      </div>
    </form>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/monitor-form';
</style>
