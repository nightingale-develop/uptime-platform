import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'

import type {
  Check,
  Monitor,
  MonitorCreate,
  MonitorStatistics,
  MonitorUpdate,
  StatisticsPeriod,
} from '@/types/monitor'

interface MonitorState {
  monitors: Monitor[]
  loading: boolean
  error: string | null
}

export const useMonitorStore = defineStore('monitors', {
  state: (): MonitorState => ({
    monitors: [],
    loading: false,
    error: null,
  }),

  actions: {
    async loadMonitors(): Promise<void> {
      await loadOrganizationData(
        this,
        () => apiClient.get<Monitor[]>('/api/v1/monitors').then((response) => response.data),
        (data) => {
          this.monitors = data
        },
        () => {
          this.monitors = []
        },
        'Unable to load monitors',
      )
    },

    async getMonitor(monitorId: string): Promise<Monitor> {
      const response = await apiClient.get<Monitor>(`/api/v1/monitors/${monitorId}`)

      return response.data
    },

    async createMonitor(data: MonitorCreate): Promise<Monitor> {
      const response = await apiClient.post<Monitor>('/api/v1/monitors', data)

      return response.data
    },

    async updateMonitor(monitorId: string, data: MonitorUpdate): Promise<Monitor> {
      const response = await apiClient.patch<Monitor>(`/api/v1/monitors/${monitorId}`, data)

      const monitorIndex = this.monitors.findIndex((monitor) => {
        return monitor.id === monitorId
      })

      if (monitorIndex !== -1) {
        this.monitors[monitorIndex] = response.data
      }

      return response.data
    },

    async deleteMonitor(monitorId: string): Promise<void> {
      await apiClient.delete(`/api/v1/monitors/${monitorId}`)

      this.monitors = this.monitors.filter((monitor) => {
        return monitor.id !== monitorId
      })
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.monitors = []
      this.loading = false
      this.error = null
    },
    async runMonitorCheck(monitorId: string): Promise<Check> {
      const response = await apiClient.post<Check>(`/api/v1/monitors/${monitorId}/checks`)

      return response.data
    },

    async getMonitorChecks(monitorId: string, limit = 50): Promise<Check[]> {
      const response = await apiClient.get<Check[]>(`/api/v1/monitors/${monitorId}/checks`, {
        params: {
          limit,
        },
      })

      return response.data
    },
    async getMonitorStatistics(
      monitorId: string,
      period: StatisticsPeriod,
    ): Promise<MonitorStatistics> {
      const response = await apiClient.get<MonitorStatistics>(
        `/api/v1/monitors/${monitorId}/statistics`,
        {
          params: {
            period,
          },
        },
      )

      return response.data
    },
  },
})
