import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import type { Organization, OrganizationCreate } from '@/types/organization'

const ORGANIZATION_STORAGE_KEY = 'uptime-platform.organization-id'

interface OrganizationState {
  organizations: Organization[]
  currentOrganizationId: string | null
  contextVersion: number
  initialized: boolean
}

export const useOrganizationStore = defineStore('organizations', {
  state: (): OrganizationState => ({
    organizations: [],
    currentOrganizationId: null,
    contextVersion: 0,
    initialized: false,
  }),

  getters: {
    currentOrganization(state): Organization | null {
      if (!state.currentOrganizationId) {
        return null
      }

      return (
        state.organizations.find((organization) => {
          return organization.id === state.currentOrganizationId
        }) ?? null
      )
    },
  },

  actions: {
    async loadOrganizations(): Promise<void> {
      const response = await apiClient.get<Organization[]>('/api/v1/organizations')

      this.organizations = response.data

      const storedOrganizationId = localStorage.getItem(ORGANIZATION_STORAGE_KEY)

      const storedOrganizationExists = this.organizations.some((organization) => {
        return organization.id === storedOrganizationId
      })

      const previousOrganizationId = this.currentOrganizationId
      if (storedOrganizationId && storedOrganizationExists) {
        this.currentOrganizationId = storedOrganizationId
      } else {
        this.currentOrganizationId = this.organizations[0]?.id ?? null
      }

      if (this.currentOrganizationId !== previousOrganizationId) {
        this.contextVersion += 1
      }

      if (this.currentOrganizationId) {
        localStorage.setItem(ORGANIZATION_STORAGE_KEY, this.currentOrganizationId)
      } else {
        localStorage.removeItem(ORGANIZATION_STORAGE_KEY)
      }

      this.initialized = true
    },

    selectOrganization(organizationId: string): void {
      const organizationExists = this.organizations.some((organization) => {
        return organization.id === organizationId
      })

      if (!organizationExists) {
        return
      }

      if (this.currentOrganizationId !== organizationId) {
        this.contextVersion += 1
        this.currentOrganizationId = organizationId
      }

      localStorage.setItem(ORGANIZATION_STORAGE_KEY, organizationId)
    },

    clear(): void {
      this.contextVersion += 1
      this.organizations = []
      this.currentOrganizationId = null
      this.initialized = false

      localStorage.removeItem(ORGANIZATION_STORAGE_KEY)
    },
    async createOrganization(data: OrganizationCreate): Promise<Organization> {
      const response = await apiClient.post<Organization>('/api/v1/organizations', data)

      this.organizations.push(response.data)

      this.selectOrganization(response.data.id)

      return response.data
    },
  },
})
