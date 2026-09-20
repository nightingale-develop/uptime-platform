import { defineStore } from 'pinia'

import apiClient from '@/api/client'
import { invalidateOrganizationLoad, loadOrganizationData } from '@/stores/organization-load'
import type {
  OrganizationMember,
  OrganizationMemberCreate,
  OrganizationMemberUpdate,
} from '@/types/member'

interface MembersState {
  members: OrganizationMember[]
  loading: boolean
  error: string | null
}

export const useMembersStore = defineStore('members', {
  state: (): MembersState => ({
    members: [],
    loading: false,
    error: null,
  }),

  actions: {
    async loadMembers(): Promise<void> {
      await loadOrganizationData(
        this,
        () =>
          apiClient
            .get<OrganizationMember[]>('/api/v1/organization-members')
            .then((response) => response.data),
        (data) => {
          this.members = data
        },
        () => {
          this.members = []
        },
        'Unable to load organization members',
      )
    },

    async addMember(data: OrganizationMemberCreate): Promise<OrganizationMember> {
      const response = await apiClient.post<OrganizationMember>(
        '/api/v1/organization-members',
        data,
      )

      this.members.push(response.data)

      return response.data
    },

    async updateMember(
      userId: string,
      data: OrganizationMemberUpdate,
    ): Promise<OrganizationMember> {
      const response = await apiClient.patch<OrganizationMember>(
        `/api/v1/organization-members/${userId}`,
        data,
      )

      const index = this.members.findIndex((member) => {
        return member.user_id === userId
      })

      if (index !== -1) {
        this.members[index] = response.data
      }

      return response.data
    },

    async removeMember(userId: string): Promise<void> {
      await apiClient.delete(`/api/v1/organization-members/${userId}`)

      this.members = this.members.filter((member) => {
        return member.user_id !== userId
      })
    },

    clear(): void {
      invalidateOrganizationLoad(this)
      this.members = []
      this.loading = false
      this.error = null
    },
  },
})
