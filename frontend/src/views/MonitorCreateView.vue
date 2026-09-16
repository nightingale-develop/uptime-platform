<script setup lang="ts">
import axios from 'axios'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useMonitorStore } from '@/stores/monitors'
import { useOrganizationStore } from '@/stores/organizations'
import type { DnsRecordType, HttpMethod, MonitorCreate, MonitorType } from '@/types/monitor'

import AppSelect from '@/components/AppSelect.vue'
import type { SelectOption } from '@/types/select'

const monitorTypeOptions: SelectOption<MonitorType>[] = [
  { value: 'http', label: 'HTTP' },
  { value: 'tcp', label: 'TCP' },
  { value: 'dns', label: 'DNS' },
  { value: 'tls', label: 'TLS' },
  { value: 'icmp', label: 'ICMP' },
]

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

const router = useRouter()

const monitorStore = useMonitorStore()
const organizationStore = useOrganizationStore()

const name = ref('')
const monitorType = ref<MonitorType>('http')

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

const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

const canCreateMonitor = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin' || role === 'member'
})

watch(httpMethod, (method) => {
  if (method === 'HEAD') {
    bodyContains.value = ''
  }
})

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

function buildMonitorCreate(): MonitorCreate {
  const base = {
    name: name.value.trim(),
    interval_seconds: intervalSeconds.value,
    timeout_seconds: timeoutSeconds.value,
    failure_threshold: failureThreshold.value,
    recovery_threshold: recoveryThreshold.value,
  }

  switch (monitorType.value) {
    case 'http':
      return {
        ...base,
        monitor_type: 'http',
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
        monitor_type: 'tcp',
        config: {
          host: tcpHost.value.trim(),
          port: tcpPort.value,
        },
      }

    case 'dns':
      return {
        ...base,
        monitor_type: 'dns',
        config: {
          host: dnsHost.value.trim(),
          record_type: dnsRecordType.value,
        },
      }

    case 'tls':
      return {
        ...base,
        monitor_type: 'tls',
        config: {
          host: tlsHost.value.trim(),
          port: tlsPort.value,
          expiry_threshold_days: tlsExpiryThresholdDays.value,
        },
      }

    case 'icmp':
      return {
        ...base,
        monitor_type: 'icmp',
        config: {
          host: icmpHost.value.trim(),
        },
      }
  }
}

async function submitMonitor(): Promise<void> {
  errorMessage.value = null
  isSubmitting.value = true

  try {
    const data = buildMonitorCreate()

    await monitorStore.createMonitor(data)

    await router.push('/monitors')
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail

      if (typeof detail === 'string') {
        errorMessage.value = detail
      } else if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') {
        errorMessage.value = detail[0].msg
      } else {
        errorMessage.value = 'Unable to create monitor'
      }
    } else if (error instanceof Error) {
      errorMessage.value = error.message
    } else {
      errorMessage.value = 'Unable to create monitor'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <section class="monitor-create">
    <div class="monitor-create__header">
      <div>
        <h1>Create monitor</h1>

        <p>Configure a new monitor for the selected organization.</p>
      </div>

      <RouterLink class="monitor-create__back" to="/monitors"> Back to monitors </RouterLink>
    </div>

    <div v-if="!canCreateMonitor" class="monitor-create__forbidden">
      Your organization role does not allow creating monitors.
    </div>

    <form v-else class="monitor-form" @submit.prevent="submitMonitor">
      <div class="form-section">
        <h2>General</h2>

        <div class="form-field">
          <label for="name"> Name </label>

          <input id="name" v-model.trim="name" type="text" maxlength="100" required />
        </div>

        <div class="form-field">
          <label for="monitor-type"> Monitor type </label>
          <AppSelect id="monitor-type" v-model="monitorType" :options="monitorTypeOptions" />
        </div>
      </div>

      <div class="form-section">
        <h2>Target</h2>

        <template v-if="monitorType === 'http'">
          <div class="form-field">
            <label for="http-url"> URL </label>

            <input
              id="http-url"
              v-model.trim="httpUrl"
              type="url"
              placeholder="https://example.com/health"
              required
            />
          </div>

          <div class="form-field">
            <label for="http-method"> Method </label>
            <AppSelect id="http-method" v-model="httpMethod" :options="httpMethodOptions" />
          </div>

          <div class="form-field">
            <label for="expected-status-codes"> Expected status codes </label>

            <input
              id="expected-status-codes"
              v-model.trim="expectedStatusCodes"
              type="text"
              placeholder="200, 204"
            />

            <small> Leave empty to use the backend default behavior. </small>
          </div>

          <div v-if="httpMethod !== 'HEAD'" class="form-field">
            <label for="body-contains"> Response body contains </label>

            <input
              id="body-contains"
              v-model="bodyContains"
              type="text"
              maxlength="4096"
              placeholder="Optional text"
            />
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

        <template v-else-if="monitorType === 'tcp'">
          <div class="form-grid">
            <div class="form-field">
              <label for="tcp-host"> Host </label>

              <input
                id="tcp-host"
                v-model.trim="tcpHost"
                type="text"
                maxlength="255"
                placeholder="example.com"
                required
              />
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

        <template v-else-if="monitorType === 'dns'">
          <div class="form-grid">
            <div class="form-field">
              <label for="dns-host"> Host </label>

              <input
                id="dns-host"
                v-model.trim="dnsHost"
                type="text"
                maxlength="253"
                placeholder="example.com"
                required
              />
            </div>

            <div class="form-field">
              <label for="dns-record-type"> Record type </label>
              <AppSelect
                id="dns-record-type"
                v-model="dnsRecordType"
                :options="dnsRecordTypeOptions"
              />
            </div>
          </div>
        </template>

        <template v-else-if="monitorType === 'tls'">
          <div class="form-grid">
            <div class="form-field">
              <label for="tls-host"> Host </label>

              <input
                id="tls-host"
                v-model.trim="tlsHost"
                type="text"
                maxlength="253"
                placeholder="example.com"
                required
              />
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

        <template v-else-if="monitorType === 'icmp'">
          <div class="form-field">
            <label for="icmp-host"> Host </label>

            <input
              id="icmp-host"
              v-model.trim="icmpHost"
              type="text"
              maxlength="253"
              placeholder="example.com"
              required
            />
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

            <small> Consecutive failures before marking the monitor down. </small>
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

            <small> Consecutive successful checks before recovery. </small>
          </div>
        </div>
      </div>

      <p v-if="errorMessage" class="form-error" role="alert">
        {{ errorMessage }}
      </p>

      <div class="monitor-form__actions">
        <RouterLink class="button-secondary" to="/monitors"> Cancel </RouterLink>

        <button class="button-primary" type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Creating...' : 'Create monitor' }}
        </button>
      </div>
    </form>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/monitor-form';
</style>
