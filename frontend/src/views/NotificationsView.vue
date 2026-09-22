<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { requestConfirmation } from '@/composables/confirmation'
import { useNotificationStore } from '@/stores/notifications'
import { useOrganizationStore } from '@/stores/organizations'
import type {
  EmailSecurity,
  NotificationDestination,
  NotificationDestinationCreate,
  NotificationDestinationType,
  NotificationDestinationUpdate,
} from '@/types/notification'

import AppSelect from '@/components/AppSelect.vue'
import type { SelectOption } from '@/types/select'

const notificationStore = useNotificationStore()
const organizationStore = useOrganizationStore()

const editingDestinationId = ref<string | null>(null)

const name = ref('')
const destinationType = ref<NotificationDestinationType>('webhook')

const enabled = ref(true)

const webhookUrl = ref('')
const webhookSecret = ref('')

const slackWebhookUrl = ref('')

const telegramBotToken = ref('')
const telegramChatId = ref('')

const emailHost = ref('')
const emailPort = ref(587)
const emailUsername = ref('')
const emailPassword = ref('')
const emailFrom = ref('')
const emailTo = ref('')
const emailSecurity = ref<EmailSecurity>('starttls')

const formError = ref<string | null>(null)
const isSaving = ref(false)
const deletingDestinationId = ref<string | null>(null)

const isEditing = computed(() => {
  return editingDestinationId.value !== null
})

const canManageNotifications = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin' || role === 'member'
})

const destinationTypeOptions: SelectOption<NotificationDestinationType>[] = [
  { value: 'webhook', label: 'Webhook' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'email', label: 'Email' },
  { value: 'slack', label: 'Slack' },
]

const emailSecurityOptions: SelectOption<EmailSecurity>[] = [
  { value: 'none', label: 'None' },
  { value: 'starttls', label: 'STARTTLS' },
  { value: 'tls', label: 'TLS' },
]

function clearConfigFields(): void {
  slackWebhookUrl.value = ''
  webhookUrl.value = ''
  webhookSecret.value = ''

  telegramBotToken.value = ''
  telegramChatId.value = ''

  emailHost.value = ''
  emailPort.value = 587
  emailUsername.value = ''
  emailPassword.value = ''
  emailFrom.value = ''
  emailTo.value = ''
  emailSecurity.value = 'starttls'
}

function resetForm(): void {
  editingDestinationId.value = null

  name.value = ''
  destinationType.value = 'webhook'
  enabled.value = true

  clearConfigFields()

  formError.value = null
}

function startEdit(destination: NotificationDestination): void {
  clearConfigFields()

  editingDestinationId.value = destination.id

  name.value = destination.name
  enabled.value = destination.enabled
  destinationType.value = destination.destination_type

  switch (destination.destination_type) {
    case 'slack':
      break
    case 'webhook':
      webhookUrl.value = destination.config.url
      break

    case 'telegram':
      telegramChatId.value = destination.config.chat_id
      break

    case 'email':
      emailHost.value = destination.config.host
      emailPort.value = destination.config.port
      emailUsername.value = destination.config.username ?? ''
      emailFrom.value = destination.config.from_email
      emailTo.value = destination.config.to_email
      emailSecurity.value = destination.config.security
      break
  }

  formError.value = null
}

function buildCreatePayload(): NotificationDestinationCreate | null {
  const trimmedName = name.value.trim()

  if (!trimmedName) {
    formError.value = 'Name is required'
    return null
  }

  switch (destinationType.value) {
    case 'slack':
      if (!slackWebhookUrl.value.trim()) {
        formError.value = 'Slack incoming webhook URL is required'
        return null
      }
      return {
        name: trimmedName,
        destination_type: 'slack',
        enabled: enabled.value,
        config: { webhook_url: slackWebhookUrl.value.trim() },
      }

    case 'webhook':
      if (!webhookUrl.value.trim()) {
        formError.value = 'Webhook URL is required'
        return null
      }

      if (webhookSecret.value.length < 16) {
        formError.value = 'Webhook secret must be at least 16 characters'
        return null
      }

      return {
        name: trimmedName,
        destination_type: 'webhook',
        enabled: enabled.value,
        config: {
          url: webhookUrl.value.trim(),
          secret: webhookSecret.value,
        },
      }

    case 'telegram':
      if (!telegramBotToken.value.trim() || !telegramChatId.value.trim()) {
        formError.value = 'Bot token and chat ID are required'
        return null
      }

      return {
        name: trimmedName,
        destination_type: 'telegram',
        enabled: enabled.value,
        config: {
          bot_token: telegramBotToken.value.trim(),
          chat_id: telegramChatId.value.trim(),
        },
      }

    case 'email':
      if (!emailHost.value.trim() || !emailFrom.value.trim() || !emailTo.value.trim()) {
        formError.value = 'SMTP host, from email and to email are required'
        return null
      }

      if (emailPort.value < 1 || emailPort.value > 65535) {
        formError.value = 'Invalid SMTP port'
        return null
      }

      return {
        name: trimmedName,
        destination_type: 'email',
        enabled: enabled.value,
        config: {
          host: emailHost.value.trim(),
          port: emailPort.value,
          username: emailUsername.value.trim() || null,
          password: emailPassword.value || null,
          from_email: emailFrom.value.trim(),
          to_email: emailTo.value.trim(),
          security: emailSecurity.value,
        },
      }
  }
}

function buildUpdatePayload(): NotificationDestinationUpdate | null {
  const trimmedName = name.value.trim()

  if (!trimmedName) {
    formError.value = 'Name is required'
    return null
  }

  switch (destinationType.value) {
    case 'slack':
      return {
        name: trimmedName,
        enabled: enabled.value,
        ...(slackWebhookUrl.value.trim()
          ? { config: { webhook_url: slackWebhookUrl.value.trim() } }
          : {}),
      }

    case 'webhook': {
      if (!webhookUrl.value.trim()) {
        formError.value = 'Webhook URL is required'
        return null
      }

      if (webhookSecret.value && webhookSecret.value.length < 16) {
        formError.value = 'Webhook secret must be at least 16 characters'
        return null
      }

      const config: {
        url: string
        secret?: string
      } = {
        url: webhookUrl.value.trim(),
      }

      if (webhookSecret.value) {
        config.secret = webhookSecret.value
      }

      return {
        name: trimmedName,
        enabled: enabled.value,
        config,
      }
    }

    case 'telegram': {
      if (!telegramChatId.value.trim()) {
        formError.value = 'Chat ID is required'
        return null
      }

      const config: {
        chat_id: string
        bot_token?: string
      } = {
        chat_id: telegramChatId.value.trim(),
      }

      if (telegramBotToken.value.trim()) {
        config.bot_token = telegramBotToken.value.trim()
      }

      return {
        name: trimmedName,
        enabled: enabled.value,
        config,
      }
    }

    case 'email': {
      if (!emailHost.value.trim() || !emailFrom.value.trim() || !emailTo.value.trim()) {
        formError.value = 'SMTP host, from email and to email are required'
        return null
      }

      const config: {
        host: string
        port: number
        username: string | null
        from_email: string
        to_email: string
        security: EmailSecurity
        password?: string
      } = {
        host: emailHost.value.trim(),
        port: emailPort.value,
        username: emailUsername.value.trim() || null,
        from_email: emailFrom.value.trim(),
        to_email: emailTo.value.trim(),
        security: emailSecurity.value,
      }

      if (emailPassword.value) {
        config.password = emailPassword.value
      }

      return {
        name: trimmedName,
        enabled: enabled.value,
        config,
      }
    }
  }
}

async function handleSubmit(): Promise<void> {
  formError.value = null

  isSaving.value = true

  try {
    if (editingDestinationId.value) {
      const payload = buildUpdatePayload()

      if (!payload) {
        return
      }

      await notificationStore.updateDestination(editingDestinationId.value, payload)
    } else {
      const payload = buildCreatePayload()

      if (!payload) {
        return
      }

      await notificationStore.createDestination(payload)

      await notificationStore.loadDestinations()
    }

    resetForm()
  } catch {
    formError.value = isEditing.value
      ? 'Unable to update notification destination'
      : 'Unable to create notification destination'
  } finally {
    isSaving.value = false
  }
}

async function toggleEnabled(destination: NotificationDestination): Promise<void> {
  await notificationStore.updateDestination(destination.id, {
    enabled: !destination.enabled,
  })
}

async function handleDelete(destination: NotificationDestination): Promise<void> {
  const confirmed = await requestConfirmation({
    title: 'Delete notification destination',
    message: `Delete "${destination.name}"?`,
    confirmLabel: 'Delete destination',
  })
  if (!confirmed) {
    return
  }

  deletingDestinationId.value = destination.id

  try {
    await notificationStore.deleteDestination(destination.id)

    if (editingDestinationId.value === destination.id) {
      resetForm()
    }
  } finally {
    deletingDestinationId.value = null
  }
}

function getDestinationDetails(destination: NotificationDestination): string {
  switch (destination.destination_type) {
    case 'slack':
      return 'Slack incoming webhook'

    case 'webhook':
      return destination.config.url

    case 'telegram':
      return `Chat ID: ${destination.config.chat_id}`

    case 'email':
      return `${destination.config.from_email}` + ` → ${destination.config.to_email}`
  }
}

onMounted(async () => {
  await notificationStore.loadDestinations()
})

watch(
  () => organizationStore.currentOrganizationId,
  async (currentOrganizationId, previousOrganizationId) => {
    if (previousOrganizationId && currentOrganizationId !== previousOrganizationId) {
      resetForm()

      await notificationStore.loadDestinations()
    }
  },
)
</script>

<template>
  <section class="notifications-page">
    <div class="notifications-page__header">
      <div>
        <h1>Notifications</h1>

        <p>Configure destinations for incident notifications.</p>
      </div>
    </div>

    <div v-if="canManageNotifications" class="section-card">
      <div class="section-header">
        <div>
          <h2>
            {{ isEditing ? 'Edit destination' : 'Add destination' }}
          </h2>

          <p>Configure Webhook, Telegram, Email or Slack delivery.</p>
        </div>

        <button v-if="isEditing" class="button-secondary" type="button" @click="resetForm">
          Cancel editing
        </button>
      </div>

      <form class="notification-form" @submit.prevent="handleSubmit">
        <div class="form-grid">
          <div class="form-field">
            <label for="notification-name"> Name </label>

            <input id="notification-name" v-model="name" maxlength="100" required />
          </div>

          <div class="form-field">
            <label for="notification-type"> Type </label>

            <AppSelect
              id="notification-type"
              v-model="destinationType"
              :options="destinationTypeOptions"
              :disabled="isEditing"
            />

            <small v-if="isEditing"> Destination type cannot be changed. </small>
          </div>
        </div>

        <template v-if="destinationType === 'webhook'">
          <div class="form-field">
            <label for="webhook-url"> Webhook URL </label>

            <input
              id="webhook-url"
              v-model="webhookUrl"
              type="url"
              placeholder="https://example.com/webhook"
              required
            />
          </div>

          <div class="form-field">
            <label for="webhook-secret"> Secret </label>

            <input
              id="webhook-secret"
              v-model="webhookSecret"
              type="password"
              :required="!isEditing"
            />

            <small v-if="isEditing"> Leave empty to keep the existing secret. </small>
          </div>
        </template>

        <template v-else-if="destinationType === 'telegram'">
          <div class="form-grid">
            <div class="form-field">
              <label for="telegram-token"> Bot token </label>

              <input
                id="telegram-token"
                v-model="telegramBotToken"
                type="password"
                :required="!isEditing"
              />

              <small v-if="isEditing"> Leave empty to keep the existing token. </small>
            </div>

            <div class="form-field">
              <label for="telegram-chat-id"> Chat ID </label>

              <input id="telegram-chat-id" v-model="telegramChatId" required />
            </div>
          </div>
        </template>

        <template v-else-if="destinationType === 'slack'">
          <div class="form-field">
            <label for="slack-webhook-url"> Incoming webhook URL </label>
            <input
              id="slack-webhook-url"
              v-model="slackWebhookUrl"
              type="password"
              autocomplete="new-password"
              maxlength="2048"
              placeholder="https://hooks.slack.com/services/..."
              :required="!isEditing"
            />
            <small v-if="isEditing"> Leave empty to keep the existing webhook URL. </small>
            <small v-else>
              Create an incoming webhook in your Slack app for the desired channel.
            </small>
          </div>
        </template>

        <template v-else>
          <div class="form-grid">
            <div class="form-field">
              <label for="email-host"> SMTP host </label>

              <input id="email-host" v-model="emailHost" required />
            </div>

            <div class="form-field">
              <label for="email-port"> SMTP port </label>

              <input
                id="email-port"
                v-model.number="emailPort"
                type="number"
                min="1"
                max="65535"
                required
              />
            </div>

            <div class="form-field">
              <label for="email-username"> Username </label>

              <input id="email-username" v-model="emailUsername" />
            </div>

            <div class="form-field">
              <label for="email-password"> Password </label>

              <input id="email-password" v-model="emailPassword" type="password" />

              <small v-if="isEditing"> Leave empty to keep the existing password. </small>
            </div>

            <div class="form-field">
              <label for="email-from"> From email </label>

              <input id="email-from" v-model="emailFrom" type="email" required />
            </div>

            <div class="form-field">
              <label for="email-to"> To email </label>

              <input id="email-to" v-model="emailTo" type="email" required />
            </div>

            <div class="form-field">
              <label for="email-security"> Security </label>

              <AppSelect
                id="email-security"
                v-model="emailSecurity"
                :options="emailSecurityOptions"
              />
            </div>
          </div>
        </template>

        <label class="form-checkbox">
          <input v-model="enabled" type="checkbox" />

          Enabled
        </label>

        <p v-if="formError" class="form-error">
          {{ formError }}
        </p>

        <div class="notification-form__actions">
          <button class="button-primary" type="submit" :disabled="isSaving">
            {{ isSaving ? 'Saving...' : isEditing ? 'Save changes' : 'Add destination' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="notificationStore.error" class="message-error">
      {{ notificationStore.error }}
    </div>

    <p v-else-if="notificationStore.loading" class="text-muted">
      Loading notification destinations...
    </p>

    <div v-else-if="notificationStore.destinations.length === 0" class="notifications-page__empty">
      <h2>No notification destinations</h2>

      <p>Add a destination to receive incident notifications.</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Destination</th>
            <th>Status</th>
            <th>Created</th>

            <th v-if="canManageNotifications">Actions</th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="destination in notificationStore.destinations" :key="destination.id">
            <td>
              <strong>{{ destination.name }}</strong>
            </td>

            <td>
              {{ destination.destination_type }}
            </td>

            <td>
              {{ getDestinationDetails(destination) }}
            </td>

            <td>
              <span
                class="destination-status"
                :class="{
                  'destination-status--enabled': destination.enabled,
                  'destination-status--disabled': !destination.enabled,
                }"
              >
                {{ destination.enabled ? 'Enabled' : 'Disabled' }}
              </span>
            </td>

            <td>
              {{ new Date(destination.created_at).toLocaleString() }}
            </td>

            <td v-if="canManageNotifications" class="notifications-actions">
              <button class="button-secondary" type="button" @click="toggleEnabled(destination)">
                {{ destination.enabled ? 'Disable' : 'Enable' }}
              </button>

              <button class="button-secondary" type="button" @click="startEdit(destination)">
                Edit
              </button>

              <button
                class="button-danger"
                type="button"
                :disabled="deletingDestinationId === destination.id"
                @click="handleDelete(destination)"
              >
                {{ deletingDestinationId === destination.id ? 'Deleting...' : 'Delete' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/notifications';
</style>
