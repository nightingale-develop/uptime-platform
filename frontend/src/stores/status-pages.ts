import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'
import type {
  PublicStatusPage,
  StatusPage,
  StatusPageCreate,
  StatusPageMonitor,
  StatusPageUpdate,
} from '@/types/status-page'

interface StatusPageState {
  pages: StatusPage[]
  loading: boolean
  error: string | null
}

export const useStatusPageStore = defineStore('status-pages', {
  state: (): StatusPageState => ({
    pages: [],
    loading: false,
    error: null,
  }),

  actions: {
    async loadPages(): Promise<void> {
      await loadOrganizationData(
        this,
        () => apiClient.get<StatusPage[]>('/api/v1/status-pages').then((response) => response.data),
        (data) => {
          this.pages = data
        },
        () => {
          this.pages = []
        },
        'Unable to load status pages',
      )
    },

    async getPage(pageId: string): Promise<StatusPage> {
      const response = await apiClient.get<StatusPage>(`/api/v1/status-pages/${pageId}`)

      return response.data
    },

    async createPage(data: StatusPageCreate): Promise<StatusPage> {
      const response = await apiClient.post<StatusPage>('/api/v1/status-pages', data)

      this.pages.unshift(response.data)

      return response.data
    },

    async updatePage(pageId: string, data: StatusPageUpdate): Promise<StatusPage> {
      const response = await apiClient.patch<StatusPage>(`/api/v1/status-pages/${pageId}`, data)

      const index = this.pages.findIndex((page) => {
        return page.id === pageId
      })

      if (index !== -1) {
        this.pages[index] = response.data
      }

      return response.data
    },

    async deletePage(pageId: string): Promise<void> {
      await apiClient.delete(`/api/v1/status-pages/${pageId}`)

      this.pages = this.pages.filter((page) => {
        return page.id !== pageId
      })
    },

    async getPageMonitors(pageId: string): Promise<StatusPageMonitor[]> {
      const response = await apiClient.get<StatusPageMonitor[]>(
        `/api/v1/status-pages/${pageId}/monitors`,
      )

      return response.data
    },

    async addMonitor(pageId: string, monitorId: string): Promise<void> {
      await apiClient.post(`/api/v1/status-pages/${pageId}/monitors/${monitorId}`)
    },

    async removeMonitor(pageId: string, monitorId: string): Promise<void> {
      await apiClient.delete(`/api/v1/status-pages/${pageId}/monitors/${monitorId}`)
    },

    async getPublicPage(slug: string): Promise<PublicStatusPage> {
      const response = await apiClient.get<PublicStatusPage>(`/status/${slug}`)

      return response.data
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.pages = []
      this.loading = false
      this.error = null
    },
  },
})
