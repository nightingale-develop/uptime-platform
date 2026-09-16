<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref, watch } from 'vue'

import { useMembersStore } from '@/stores/members'
import { useOrganizationStore } from '@/stores/organizations'
import type { OrganizationMember } from '@/types/member'
import type { OrganizationRole } from '@/types/organization'

import AppSelect from '@/components/AppSelect.vue'
import type { SelectOption } from '@/types/select'

const membersStore = useMembersStore()
const organizationStore = useOrganizationStore()

const roles: OrganizationRole[] = ['owner', 'admin', 'member', 'viewer']

const email = ref('')
const role = ref<OrganizationRole>('member')

const roleOptions:
  SelectOption<OrganizationRole>[] =
    roles.map((availableRole) => {
      return {
        value: availableRole,
        label: formatRole(availableRole),
      }
    })

const isAdding = ref(false)
const updatingMemberId = ref<string | null>(null)
const removingMemberId = ref<string | null>(null)

const actionError = ref<string | null>(null)

const currentOrganization = computed(() => {
  return organizationStore.currentOrganization
})

const canManageMembers = computed(() => {
  const currentRole = currentOrganization.value?.role

  return currentRole === 'owner' || currentRole === 'admin'
})

function formatRole(role: OrganizationRole): string {
  return role.charAt(0).toUpperCase() + role.slice(1)
}

function resetAddForm(): void {
  email.value = ''
  role.value = 'member'
  actionError.value = null
}

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

async function handleAddMember(): Promise<void> {
  actionError.value = null

  const trimmedEmail = email.value.trim()

  if (!trimmedEmail) {
    actionError.value = 'Email is required'
    return
  }

  isAdding.value = true

  try {
    await membersStore.addMember({
      email: trimmedEmail,
      role: role.value,
    })

    resetAddForm()
  } catch (error) {
    actionError.value = getApiErrorMessage(error, 'Unable to add organization member')
  } finally {
    isAdding.value = false
  }
}

async function handleRoleChange(
  member: OrganizationMember,
  newRole: OrganizationRole,
): Promise<void> {
  if (newRole === member.role) {
    return
  }

  actionError.value = null
  updatingMemberId.value = member.user_id

  try {
    await membersStore.updateMember(
      member.user_id,
      {
        role: newRole,
      },
    )
  } catch (error) {
    actionError.value = getApiErrorMessage(
      error,
      'Unable to update member role',
    )
  } finally {
    updatingMemberId.value = null
  }
}

async function handleRemoveMember(member: OrganizationMember): Promise<void> {
  const confirmed = window.confirm(`Remove "${member.email}" from this organization?`)

  if (!confirmed) {
    return
  }

  actionError.value = null
  removingMemberId.value = member.user_id

  try {
    await membersStore.removeMember(member.user_id)
  } catch (error) {
    actionError.value = getApiErrorMessage(error, 'Unable to remove organization member')
  } finally {
    removingMemberId.value = null
  }
}

async function loadMembers(): Promise<void> {
  try {
    await membersStore.loadMembers()
  } catch {
    // Store already contains the load error.
  }
}

onMounted(async () => {
  await loadMembers()
})

watch(
  () => organizationStore.currentOrganizationId,
  async (currentOrganizationId, previousOrganizationId) => {
    if (previousOrganizationId && currentOrganizationId !== previousOrganizationId) {
      resetAddForm()
      await loadMembers()
    }
  },
)
</script>

<template>
  <section class="members-page">
    <div class="members-page__header">
      <div>
        <h1>Members</h1>

        <p v-if="currentOrganization">
          Manage access to
          <strong>{{ currentOrganization.name }}</strong
          >.
        </p>
      </div>
    </div>

    <div v-if="canManageMembers" class="section-card">
      <div class="section-header">
        <div>
          <h2>Add member</h2>

          <p>Add a user to the current organization.</p>
        </div>
      </div>

      <form class="member-form" @submit.prevent="handleAddMember">
        <div class="form-grid">
          <div class="form-field">
            <label for="member-email"> Email </label>

            <input
              id="member-email"
              v-model="email"
              type="email"
              placeholder="user@example.com"
              required
            />
          </div>

          <div class="form-field">
            <label for="member-role"> Role </label>
            <AppSelect
              id="member-role"
              v-model="role"
              :options="roleOptions"
            />
          </div>
        </div>

        <div class="member-form__actions">
          <button class="button-primary" type="submit" :disabled="isAdding">
            {{ isAdding ? 'Adding...' : 'Add member' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="actionError" class="message-error members-page__message">
      {{ actionError }}
    </div>

    <div v-if="membersStore.error" class="message-error">
      {{ membersStore.error }}
    </div>

    <p v-else-if="membersStore.loading" class="text-muted">Loading members...</p>

    <div v-else-if="membersStore.members.length === 0" class="members-page__empty">
      <h2>No members</h2>

      <p>This organization does not have any members.</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Joined</th>

            <th v-if="canManageMembers">Actions</th>
          </tr>
        </thead>

        <tbody>
          <tr v-for="member in membersStore.members" :key="member.user_id">
            <td>
              <strong>{{ member.email }}</strong>
            </td>

            <td>
              <AppSelect
                v-if="canManageMembers"
                :id="`member-role-${member.user_id}`"
                class="member-role-select"
                :model-value="member.role"
                :options="roleOptions"
                :disabled="
                  updatingMemberId === member.user_id
                  || removingMemberId === member.user_id
                "
                @update:model-value="
                  handleRoleChange(member, $event)
                "
              />
              <span v-else class="member-role" :class="`member-role--${member.role}`">
                {{ formatRole(member.role) }}
              </span>
            </td>

            <td>
              {{ new Date(member.created_at).toLocaleString() }}
            </td>

            <td v-if="canManageMembers">
              <button
                class="button-danger"
                type="button"
                :disabled="
                  removingMemberId === member.user_id || updatingMemberId === member.user_id
                "
                @click="handleRemoveMember(member)"
              >
                {{ removingMemberId === member.user_id ? 'Removing...' : 'Remove' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style lang="scss">
@use '@/assets/scss/pages/members';
</style>
