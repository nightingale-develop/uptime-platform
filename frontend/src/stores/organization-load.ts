import { isCancel } from 'axios'

import { useOrganizationStore } from '@/stores/organizations'

const loads = new WeakMap<object, symbol>()

interface LoadingState {
  loading: boolean
  error: string | null
}

export function invalidateOrganizationLoad(state: object): void {
  loads.delete(state)
}

export async function loadOrganizationData<T>(
  state: LoadingState,
  load: () => Promise<T>,
  apply: (data: T) => void,
  reset: () => void,
  errorMessage: string,
): Promise<void> {
  const organization = useOrganizationStore()
  const version = organization.contextVersion
  const organizationId = organization.currentOrganizationId
  const token = Symbol('organization-load')
  loads.set(state, token)
  const isCurrent = () =>
    loads.get(state) === token &&
    organization.contextVersion === version &&
    organization.currentOrganizationId === organizationId

  state.loading = true
  state.error = null
  reset()

  try {
    const data = await load()
    if (isCurrent()) {
      apply(data)
    }
  } catch (error) {
    if (isCurrent() && !isCancel(error)) {
      reset()
      state.error = errorMessage
    }
    throw error
  } finally {
    if (isCurrent()) {
      state.loading = false
    }
  }
}
