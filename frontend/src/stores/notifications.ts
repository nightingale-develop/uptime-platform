import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'
import type {
  NotificationDestination,
  NotificationDestinationCreate,
  NotificationDestinationUpdate,
} from '@/types/notification'

interface NotificationState {
  destinations: NotificationDestination[]
  loading: boolean
  error: string | null
}

export const useNotificationStore = defineStore('notifications', {
  state: (): NotificationState => ({
    destinations: [],
    loading: false,
    error: null,
  }),

  actions: {
    async loadDestinations(): Promise<void> {
      await loadOrganizationData(
        this,
        () =>
          apiClient
            .get<NotificationDestination[]>('/api/v1/notification-destinations')
            .then((response) => response.data),
        (data) => {
          this.destinations = data
        },
        () => {
          this.destinations = []
        },
        'Unable to load notification destinations',
      )
    },

    async createDestination(data: NotificationDestinationCreate): Promise<NotificationDestination> {
      const response = await apiClient.post<NotificationDestination>(
        '/api/v1/notification-destinations',
        data,
      )

      return response.data
    },

    async updateDestination(
      destinationId: string,
      data: NotificationDestinationUpdate,
    ): Promise<NotificationDestination> {
      const response = await apiClient.patch<NotificationDestination>(
        `/api/v1/notification-destinations/${destinationId}`,
        data,
      )

      const index = this.destinations.findIndex((destination) => {
        return destination.id === destinationId
      })

      if (index !== -1) {
        this.destinations[index] = response.data
      }

      return response.data
    },

    async deleteDestination(destinationId: string): Promise<void> {
      await apiClient.delete(`/api/v1/notification-destinations/${destinationId}`)

      this.destinations = this.destinations.filter((destination) => {
        return destination.id !== destinationId
      })
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.destinations = []
      this.loading = false
      this.error = null
    },
  },
})
