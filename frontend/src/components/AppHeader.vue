<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppSelect from '@/components/AppSelect.vue'
import { useAuthStore } from '@/stores/auth'
import { useOrganizationStore } from '@/stores/organizations'
import type { SelectOption } from '@/types/select'

const route = useRoute()
const router = useRouter()

const authStore = useAuthStore()
const organizationStore = useOrganizationStore()

const isLoggingOut = ref(false)
const logoutError = ref<string | null>(null)

const isMobileMenuOpen = ref(false)
const mobileToggle = ref<HTMLButtonElement | null>(null)
const mobileMenu = ref<HTMLElement | null>(null)
const mobileCloseButton = ref<HTMLButtonElement | null>(null)

const logoLoadFailed = ref(false)
const logoUrl = `${import.meta.env.BASE_URL}logo.png`

const canManageApiKeys = computed(() => {
  const role = organizationStore.currentOrganization?.role

  return role === 'owner' || role === 'admin'
})

const isOperationsActive = computed(() => {
  return (
    route.path.startsWith('/maintenance') ||
    route.path.startsWith('/notifications') ||
    route.path.startsWith('/status-pages')
  )
})

const isSettingsActive = computed(() => {
  return (
    route.path.startsWith('/members') ||
    route.path.startsWith('/organizations') ||
    route.path.startsWith('/api-keys')
  )
})

const organizationOptions = computed<SelectOption<string>[]>(() => {
  return organizationStore.organizations.map((organization) => {
    return {
      value: organization.id,
      label: organization.name,
    }
  })
})

function handleOrganizationChange(organizationId: string): void {
  organizationStore.selectOrganization(organizationId)
}

function closeDropdown(event: Event): void {
  const element = event.currentTarget as HTMLElement
  const details = element.closest('details')

  details?.removeAttribute('open')
}

async function openMobileMenu(): Promise<void> {
  isMobileMenuOpen.value = true

  await nextTick()

  mobileCloseButton.value?.focus()
}

function closeMobileMenu(restoreFocus = true): void {
  if (!isMobileMenuOpen.value) {
    return
  }

  isMobileMenuOpen.value = false

  if (restoreFocus) {
    nextTick(() => {
      mobileToggle.value?.focus()
    })
  }
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (!isMobileMenuOpen.value) {
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    closeMobileMenu()
    return
  }

  if (event.key !== 'Tab' || !mobileMenu.value) {
    return
  }

  const focusableElements = Array.from(
    mobileMenu.value.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => element.getClientRects().length > 0)

  const first = focusableElements[0]
  const last = focusableElements[focusableElements.length - 1]

  if (!first || !last) {
    return
  }

  if (!mobileMenu.value.contains(document.activeElement)) {
    event.preventDefault()
    first.focus()
    return
  }

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function handleResize(): void {
  if (window.innerWidth > 1240) {
    closeMobileMenu(false)
  }
}

async function handleLogout(): Promise<void> {
  logoutError.value = null
  isLoggingOut.value = true

  try {
    await authStore.logout()

    organizationStore.clear()
    closeMobileMenu(false)

    await router.push('/login')
  } catch {
    logoutError.value = 'Unable to sign out'
  } finally {
    isLoggingOut.value = false
  }
}

watch(
  () => route.fullPath,
  () => {
    closeMobileMenu(false)
  },
)

watch(isMobileMenuOpen, (isOpen) => {
  document.body.classList.toggle('app-mobile-menu-open', isOpen)
})

onMounted(() => {
  document.addEventListener('keydown', handleDocumentKeydown)
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleDocumentKeydown)
  window.removeEventListener('resize', handleResize)

  document.body.classList.remove('app-mobile-menu-open')
})
</script>

<template>
  <header class="app-header">
    <div class="app-header__content">
      <button
        ref="mobileToggle"
        class="app-header__mobile-toggle"
        type="button"
        aria-label="Open navigation"
        aria-controls="mobile-navigation"
        :aria-expanded="isMobileMenuOpen"
        @click="openMobileMenu"
      >
        <span />
        <span />
        <span />
      </button>

      <RouterLink class="app-header__logo" to="/dashboard" aria-label="Uptime Platform dashboard">
        <img
          v-if="!logoLoadFailed"
          :src="logoUrl"
          alt="Uptime Platform"
          @error="logoLoadFailed = true"
        />

        <span v-else class="app-header__logo-fallback"> Uptime Platform </span>
      </RouterLink>

      <nav class="app-header__nav" aria-label="Main navigation">
        <RouterLink class="app-header__link" to="/dashboard"> Dashboard </RouterLink>

        <RouterLink class="app-header__link" to="/monitors"> Monitors </RouterLink>

        <RouterLink class="app-header__link" to="/incidents"> Incidents </RouterLink>

        <details class="app-header__dropdown">
          <summary
            class="app-header__dropdown-toggle"
            :class="{
              'app-header__dropdown-toggle--active': isOperationsActive,
            }"
          >
            Operations
          </summary>

          <div class="app-header__dropdown-menu">
            <RouterLink class="app-header__dropdown-link" to="/maintenance" @click="closeDropdown">
              Maintenance
            </RouterLink>

            <RouterLink
              class="app-header__dropdown-link"
              to="/notifications"
              @click="closeDropdown"
            >
              Notifications
            </RouterLink>

            <RouterLink class="app-header__dropdown-link" to="/status-pages" @click="closeDropdown">
              Status Pages
            </RouterLink>
          </div>
        </details>

        <details class="app-header__dropdown">
          <summary
            class="app-header__dropdown-toggle"
            :class="{
              'app-header__dropdown-toggle--active': isSettingsActive,
            }"
          >
            Settings
          </summary>

          <div class="app-header__dropdown-menu">
            <RouterLink class="app-header__dropdown-link" to="/members" @click="closeDropdown">
              Members
            </RouterLink>

            <RouterLink
              class="app-header__dropdown-link"
              to="/organizations"
              @click="closeDropdown"
            >
              Organizations
            </RouterLink>

            <RouterLink
              v-if="canManageApiKeys"
              class="app-header__dropdown-link"
              to="/api-keys"
              @click="closeDropdown"
            >
              API Keys
            </RouterLink>
          </div>
        </details>
      </nav>

      <div class="app-header__user">
        <AppSelect
          v-if="organizationStore.organizations.length > 0"
          id="header-organization"
          class="app-header__organization"
          :model-value="organizationStore.currentOrganizationId ?? ''"
          :options="organizationOptions"
          aria-label="Organization"
          @update:model-value="handleOrganizationChange"
        />

        <span v-if="organizationStore.currentOrganization" class="app-header__role">
          {{ organizationStore.currentOrganization.role }}
        </span>

        <span v-if="authStore.user" class="app-header__email">
          {{ authStore.user.email }}
        </span>

        <button
          class="app-header__logout"
          type="button"
          :disabled="isLoggingOut"
          @click="handleLogout"
        >
          {{ isLoggingOut ? 'Signing out...' : 'Sign out' }}
        </button>
      </div>

      <span class="app-header__mobile-spacer" aria-hidden="true" />
    </div>

    <p v-if="logoutError" class="app-header__error" role="alert">
      {{ logoutError }}
    </p>

    <template v-if="isMobileMenuOpen">
      <button
        class="app-header__mobile-overlay"
        type="button"
        aria-label="Close navigation"
        tabindex="-1"
        @click="closeMobileMenu()"
      />

      <aside
        id="mobile-navigation"
        ref="mobileMenu"
        class="app-header__mobile-menu"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mobile-navigation-title"
      >
        <div class="app-header__mobile-menu-header">
          <strong id="mobile-navigation-title">Navigation</strong>

          <button
            ref="mobileCloseButton"
            class="app-header__mobile-close"
            type="button"
            aria-label="Close navigation"
            @click="closeMobileMenu()"
          >
            ×
          </button>
        </div>

        <nav class="app-header__mobile-nav" aria-label="Mobile navigation">
          <RouterLink
            class="app-header__mobile-link"
            to="/dashboard"
            @click="closeMobileMenu(false)"
          >
            Dashboard
          </RouterLink>

          <RouterLink
            class="app-header__mobile-link"
            to="/monitors"
            @click="closeMobileMenu(false)"
          >
            Monitors
          </RouterLink>

          <RouterLink
            class="app-header__mobile-link"
            to="/incidents"
            @click="closeMobileMenu(false)"
          >
            Incidents
          </RouterLink>

          <div class="app-header__mobile-section">Operations</div>

          <RouterLink
            class="app-header__mobile-link"
            to="/maintenance"
            @click="closeMobileMenu(false)"
          >
            Maintenance
          </RouterLink>

          <RouterLink
            class="app-header__mobile-link"
            to="/notifications"
            @click="closeMobileMenu(false)"
          >
            Notifications
          </RouterLink>

          <RouterLink
            class="app-header__mobile-link"
            to="/status-pages"
            @click="closeMobileMenu(false)"
          >
            Status Pages
          </RouterLink>

          <div class="app-header__mobile-section">Settings</div>

          <RouterLink class="app-header__mobile-link" to="/members" @click="closeMobileMenu(false)">
            Members
          </RouterLink>

          <RouterLink
            class="app-header__mobile-link"
            to="/organizations"
            @click="closeMobileMenu(false)"
          >
            Organizations
          </RouterLink>

          <RouterLink
            v-if="canManageApiKeys"
            class="app-header__mobile-link"
            to="/api-keys"
            @click="closeMobileMenu(false)"
          >
            API Keys
          </RouterLink>
        </nav>

        <div class="app-header__mobile-account">
          <div v-if="organizationStore.organizations.length > 0" class="app-header__mobile-field">
            <label for="mobile-header-organization"> Organization </label>

            <AppSelect
              id="mobile-header-organization"
              class="app-header__mobile-organization"
              :model-value="organizationStore.currentOrganizationId ?? ''"
              :options="organizationOptions"
              @update:model-value="handleOrganizationChange"
            />
          </div>

          <div class="app-header__mobile-user-info">
            <span v-if="organizationStore.currentOrganization">
              Role: {{ organizationStore.currentOrganization.role }}
            </span>

            <span v-if="authStore.user">
              {{ authStore.user.email }}
            </span>
          </div>

          <button
            class="app-header__mobile-logout"
            type="button"
            :disabled="isLoggingOut"
            @click="handleLogout"
          >
            {{ isLoggingOut ? 'Signing out...' : 'Sign out' }}
          </button>
        </div>
      </aside>
    </template>
  </header>
</template>

<style lang="scss">
@use '@/assets/scss/components/app-header';
</style>
