import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'
import type { Incident, IncidentFilters } from '@/types/incident'

interface IncidentState {
  incidents: Incident[]
  loading: boolean
  error: string | null
}

export const useIncidentStore = defineStore('incidents', {
  state: (): IncidentState => ({
    incidents: [],
    loading: false,
    error: null,
  }),

  actions: {
    async getIncidents(filters: IncidentFilters = {}): Promise<Incident[]> {
      const response = await apiClient.get<Incident[]>('/api/v1/incidents', {
        params: {
          status: filters.status ?? undefined,
          monitor_id: filters.monitor_id ?? undefined,
          limit: filters.limit ?? 100,
        },
      })

      return response.data
    },

    async loadIncidents(filters: IncidentFilters = {}): Promise<void> {
      await loadOrganizationData(
        this,
        () => this.getIncidents(filters),
        (data) => {
          this.incidents = data
        },
        () => {
          this.incidents = []
        },
        'Unable to load incidents',
      )
    },

    async getIncident(incidentId: string): Promise<Incident> {
      const response = await apiClient.get<Incident>(`/api/v1/incidents/${incidentId}`)

      return response.data
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.incidents = []
      this.loading = false
      this.error = null
    },
  },
})
