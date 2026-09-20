import { CanceledError, type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { Router } from 'vue-router'

import apiClient from '@/api/client'
import type { useAuthStore } from '@/stores/auth'
import type { useOrganizationStore } from '@/stores/organizations'

type AuthStore = ReturnType<typeof useAuthStore>

type OrganizationStore = ReturnType<typeof useOrganizationStore>

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
  _organizationId?: string | null
  _organizationVersion?: number
}

const AUTH_ENDPOINTS_WITHOUT_REFRESH = [
  '/api/v1/auth/login',
  '/api/v1/auth/register',
  '/api/v1/auth/refresh',
  '/api/v1/auth/logout',
]

function shouldSkipRefresh(url?: string): boolean {
  if (!url) {
    return false
  }

  return AUTH_ENDPOINTS_WITHOUT_REFRESH.some((path) => {
    return url.endsWith(path)
  })
}

export function setupApiInterceptors(
  authStore: AuthStore,
  organizationStore: OrganizationStore,
  router: Router,
): void {
  function contextChanged(config?: RetryableRequestConfig): boolean {
    return (
      config?._organizationId !== undefined &&
      (config._organizationId !== organizationStore.currentOrganizationId ||
        config._organizationVersion !== organizationStore.contextVersion)
    )
  }

  apiClient.interceptors.request.use(
    (config: RetryableRequestConfig) => {
      const organizationId = organizationStore.currentOrganizationId
      if (
        config.url?.startsWith('/api/v1/') &&
        !config.url.startsWith('/api/v1/auth/') &&
        config.url !== '/api/v1/organizations'
      ) {
        if (config._organizationId === undefined) {
          config._organizationId = organizationId
          config._organizationVersion = organizationStore.contextVersion
        }
        if (contextChanged(config)) {
          throw new CanceledError('Organization changed', config)
        }
      }

      if (organizationId) {
        config.headers.set('X-Organization-ID', organizationId)
      } else {
        config.headers.delete('X-Organization-ID')
      }

      return config
    },
    (error: unknown) => {
      throw error
    },
    { synchronous: true },
  )

  apiClient.interceptors.response.use(
    (response) => {
      if (contextChanged(response.config)) {
        throw new CanceledError('Organization changed', response.config)
      }
      return response
    },

    async (error: AxiosError) => {
      const request = error.config as RetryableRequestConfig | undefined

      if (contextChanged(request)) {
        return Promise.reject(new CanceledError('Organization changed', request))
      }

      if (
        error.response?.status !== 401 ||
        !request ||
        request._retry ||
        shouldSkipRefresh(request.url)
      ) {
        return Promise.reject(error)
      }

      request._retry = true

      try {
        await authStore.refreshAccessToken()

        if (!authStore.accessToken) {
          return Promise.reject(error)
        }

        request.headers.set('Authorization', `Bearer ${authStore.accessToken}`)

        return apiClient(request)
      } catch {
        authStore.clearAuth()
        organizationStore.clear()

        const currentRoute = router.currentRoute.value

        if (currentRoute.name !== 'login') {
          await router.push({
            name: 'login',
            query: {
              redirect: currentRoute.fullPath,
            },
          })
        }

        return Promise.reject(error)
      }
    },
  )
}
