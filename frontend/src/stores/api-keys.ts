import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'
import type { ApiKey, ApiKeyCreate, ApiKeyCreated } from '@/types/api-key'

interface ApiKeysState {
  apiKeys: ApiKey[]
  loading: boolean
  error: string | null
}

export const useApiKeysStore = defineStore('api-keys', {
  state: (): ApiKeysState => ({
    apiKeys: [],
    loading: false,
    error: null,
  }),

  actions: {
    async loadApiKeys(): Promise<void> {
      await loadOrganizationData(
        this,
        () => apiClient.get<ApiKey[]>('/api/v1/api-keys').then((response) => response.data),
        (data) => {
          this.apiKeys = data
        },
        () => {
          this.apiKeys = []
        },
        'Unable to load API keys',
      )
    },

    async createApiKey(data: ApiKeyCreate): Promise<ApiKeyCreated> {
      const response = await apiClient.post<ApiKeyCreated>('/api/v1/api-keys', data)

      this.apiKeys.push({
        id: response.data.id,
        name: response.data.name,
        key_prefix: response.data.key_prefix,
        created_at: response.data.created_at,
        last_used_at: response.data.last_used_at,
      })

      return response.data
    },

    async deleteApiKey(apiKeyId: string): Promise<void> {
      await apiClient.delete(`/api/v1/api-keys/${apiKeyId}`)

      this.apiKeys = this.apiKeys.filter((apiKey) => {
        return apiKey.id !== apiKeyId
      })
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.apiKeys = []
      this.loading = false
      this.error = null
    },
  },
})
