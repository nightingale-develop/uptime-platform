import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'
import type {
  MaintenanceWindow,
  MaintenanceWindowCreate,
  MaintenanceWindowFilters,
} from '@/types/maintenance'

interface MaintenanceState {
  windows: MaintenanceWindow[]
  loading: boolean
  error: string | null
}

export const useMaintenanceStore = defineStore('maintenance', {
  state: (): MaintenanceState => ({
    windows: [],
    loading: false,
    error: null,
  }),

  actions: {
    async getMaintenanceWindows(
      filters: MaintenanceWindowFilters = {},
    ): Promise<MaintenanceWindow[]> {
      const response = await apiClient.get<MaintenanceWindow[]>('/api/v1/maintenance-windows', {
        params: {
          monitor_id: filters.monitor_id ?? undefined,
        },
      })

      return response.data
    },

    async loadMaintenanceWindows(filters: MaintenanceWindowFilters = {}): Promise<void> {
      await loadOrganizationData(
        this,
        () => this.getMaintenanceWindows(filters),
        (data) => {
          this.windows = data
        },
        () => {
          this.windows = []
        },
        'Unable to load maintenance windows',
      )
    },

    async createMaintenanceWindow(data: MaintenanceWindowCreate): Promise<MaintenanceWindow> {
      const response = await apiClient.post<MaintenanceWindow>('/api/v1/maintenance-windows', data)

      return response.data
    },

    async deleteMaintenanceWindow(windowId: string): Promise<void> {
      await apiClient.delete(`/api/v1/maintenance-windows/${windowId}`)

      this.windows = this.windows.filter((window) => {
        return window.id !== windowId
      })
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.windows = []
      this.loading = false
      this.error = null
    },
  },
})
