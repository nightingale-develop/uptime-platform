<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref, watch } from 'vue'
import { requestConfirmation } from '@/composables/confirmation'

import { useApiKeysStore } from '@/stores/api-keys'
import { useOrganizationStore } from '@/stores/organizations'
import type { ApiKey } from '@/types/api-key'

const apiKeysStore = useApiKeysStore()
const organizationStore = useOrganizationStore()

const name = ref('')
const createdKey = ref<string | null>(null)

const isCreating = ref(false)
const deletingKeyId = ref<string | null>(null)

const actionError = ref<string | null>(null)
const copyMessage = ref<string | null>(null)

const canManageApiKeys = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin'
})

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) {
    return fallback
  }

  const detail = error.response?.data?.detail

  if (typeof detail === 'string') {
    return detail
  }

  return fallback
}

function formatLastUsed(apiKey: ApiKey): string {
  if (!apiKey.last_used_at) {
    return 'Never'
  }

  return new Date(apiKey.last_used_at).toLocaleString()
}

async function loadApiKeys(): Promise<void> {
  createdKey.value = null
  actionError.value = null
  copyMessage.value = null

  try {
    await apiKeysStore.loadApiKeys()
  } catch {
    // Store already contains the error.
  }
}

async function handleCreate(): Promise<void> {
  actionError.value = null
  copyMessage.value = null
  createdKey.value = null

  const trimmedName = name.value.trim()

  if (!trimmedName) {
    actionError.value = 'API key name is required'
    return
  }

  isCreating.value = true

  try {
    const result = await apiKeysStore.createApiKey({
      name: trimmedName,
    })

    createdKey.value = result.key
    name.value = ''
  } catch (error) {
    actionError.value = getApiErrorMessage(error, 'Unable to create API key')
  } finally {
    isCreating.value = false
  }
}

async function handleCopyKey(): Promise<void> {
  if (!createdKey.value) {
    return
  }

  copyMessage.value = null

  try {
    await navigator.clipboard.writeText(createdKey.value)

    copyMessage.value = 'Copied'
  } catch {
    copyMessage.value = 'Unable to copy automatically'
  }
}

function dismissCreatedKey(): void {
  createdKey.value = null
  copyMessage.value = null
}

async function handleDelete(apiKey: ApiKey): Promise<void> {
  const confirmed = await requestConfirmation({
    title: 'Revoke API key',
    message: `Revoke "${apiKey.name}"? ` + 'Applications using this key will lose access.',
    confirmLabel: 'Revoke key',
  })

  if (!confirmed) {
    return
  }

  actionError.value = null
  deletingKeyId.value = apiKey.id

  try {
    await apiKeysStore.deleteApiKey(apiKey.id)
  } catch (error) {
    actionError.value = getApiErrorMessage(error, 'Unable to delete API key')
  } finally {
    deletingKeyId.value = null
  }
}

onMounted(async () => {
  if (canManageApiKeys.value) {
    await loadApiKeys()
  }
})

watch(
  () => organizationStore.currentOrganizationId,
  async (currentOrganizationId, previousOrganizationId) => {
    if (previousOrganizationId && currentOrganizationId !== previousOrganizationId) {
      apiKeysStore.clear()
      createdKey.value = null
      name.value = ''

      if (canManageApiKeys.value) {
        await loadApiKeys()
      }
    }
  },
)
</script>

<template>
  <section class="api-keys-page">
    <div class="api-keys-page__header">
      <div>
        <h1>API Keys</h1>

        <p>Manage API credentials for the current organization.</p>
      </div>
    </div>

    <div v-if="!canManageApiKeys" class="message-error">
      Only organization owners and administrators can manage API keys.
    </div>

    <template v-else>
      <div class="section-card">
        <div class="section-header">
          <div>
            <h2>Create API key</h2>

            <p>Create a credential for scripts, integrations or automation.</p>
          </div>
        </div>

        <form class="api-key-form" @submit.prevent="handleCreate">
          <div class="form-field">
            <label for="api-key-name"> Name </label>

            <input
              id="api-key-name"
              v-model="name"
              maxlength="100"
              placeholder="Production CI"
              required
            />
          </div>

          <div class="api-key-form__actions">
            <button class="button-primary" type="submit" :disabled="isCreating">
              {{ isCreating ? 'Creating...' : 'Create API key' }}
            </button>
          </div>
        </form>
      </div>

      <div v-if="createdKey" class="api-key-secret">
        <div class="api-key-secret__header">
          <div>
            <h2>API key created</h2>

            <p>Copy this key now. It will not be shown again.</p>
          </div>

          <button class="button-secondary" type="button" @click="dismissCreatedKey">Dismiss</button>
        </div>

        <div class="api-key-secret__value">
          <code>{{ createdKey }}</code>

          <button class="button-secondary" type="button" @click="handleCopyKey">Copy</button>
        </div>

        <p v-if="copyMessage" class="text-muted">
          {{ copyMessage }}
        </p>
      </div>

      <div v-if="actionError" class="message-error api-keys-page__message">
        {{ actionError }}
      </div>

      <div v-if="apiKeysStore.error" class="message-error">
        {{ apiKeysStore.error }}
      </div>

      <p v-else-if="apiKeysStore.loading" class="text-muted">Loading API keys...</p>

      <div v-else-if="apiKeysStore.apiKeys.length === 0" class="api-keys-page__empty">
        <h2>No API keys</h2>

        <p>Create an API key to access the platform programmatically.</p>
      </div>

      <div v-else class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Prefix</th>
              <th>Created</th>
              <th>Last used</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            <tr v-for="apiKey in apiKeysStore.apiKeys" :key="apiKey.id">
              <td>
                <strong>{{ apiKey.name }}</strong>
              </td>

              <td>
                <code>{{ apiKey.key_prefix }}...</code>
              </td>

              <td>
                {{ new Date(apiKey.created_at).toLocaleString() }}
              </td>

              <td>
                {{ formatLastUsed(apiKey) }}
              </td>

              <td>
                <button
                  class="button-danger"
                  type="button"
                  :disabled="deletingKeyId === apiKey.id"
                  @click="handleDelete(apiKey)"
                >
                  {{ deletingKeyId === apiKey.id ? 'Deleting...' : 'Delete' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/api-keys';
</style>
