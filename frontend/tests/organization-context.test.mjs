import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'

import { AxiosError, isCancel } from 'axios'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

let server
let apiClient
let setupApiInterceptors
let useOrganizationStore
const stores = []

before(async () => {
  server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL('..', import.meta.url)),
    resolve: { alias: { '@': fileURLToPath(new URL('../src', import.meta.url)) } },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true },
  })
  ;({ default: apiClient } = await server.ssrLoadModule('/src/api/client.ts'))
  ;({ setupApiInterceptors } = await server.ssrLoadModule('/src/api/interceptors.ts'))
  ;({ useOrganizationStore } = await server.ssrLoadModule('/src/stores/organizations.ts'))
  for (const [file, name, load, field] of [
    ['monitors', 'useMonitorStore', 'loadMonitors', 'monitors'],
    ['incidents', 'useIncidentStore', 'loadIncidents', 'incidents'],
    ['maintenance', 'useMaintenanceStore', 'loadMaintenanceWindows', 'windows'],
    ['notifications', 'useNotificationStore', 'loadDestinations', 'destinations'],
    ['members', 'useMembersStore', 'loadMembers', 'members'],
    ['api-keys', 'useApiKeysStore', 'loadApiKeys', 'apiKeys'],
    ['status-pages', 'useStatusPageStore', 'loadPages', 'pages'],
  ]) {
    const module = await server.ssrLoadModule(`/src/stores/${file}.ts`)
    stores.push({ file, useStore: module[name], load, field })
  }
})

after(async () => server?.close())

function deferred() {
  let resolve
  let reject
  const promise = new Promise((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function context(t) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const storage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  const organizations = useOrganizationStore()
  organizations.organizations = [{ id: 'A' }, { id: 'B' }]
  organizations.selectOrganization('A')
  const auth = {
    accessToken: 'fresh-token',
    async refreshAccessToken() {},
    clearAuth() {
      throw new Error('Context cancellation must not log out')
    },
  }
  setupApiInterceptors(auth, organizations, {
    currentRoute: { value: { name: 'dashboard', fullPath: '/dashboard' } },
    push() {
      throw new Error('Context cancellation must not redirect')
    },
  })
  t.after(() => {
    apiClient.interceptors.request.clear()
    apiClient.interceptors.response.clear()
    disposePinia(pinia)
    globalThis.localStorage = storage
  })
  return { organizations, auth }
}

function response(config, data = {}) {
  return { config, data, status: 200, statusText: 'OK', headers: {} }
}

test('refresh must not replay a POST in another organization', async (t) => {
  const { organizations, auth } = context(t)
  const refreshing = deferred()
  const finishRefresh = deferred()
  auth.refreshAccessToken = async () => {
    refreshing.resolve()
    await finishRefresh.promise
  }
  const attempts = []
  apiClient.defaults.adapter = async (config) => {
    attempts.push({ organization: config.headers.get('X-Organization-ID'), data: config.data })
    if (attempts.length === 1) {
      throw new AxiosError('Expired token', 'ERR_BAD_REQUEST', config, null, {
        ...response(config),
        status: 401,
      })
    }
    return response(config)
  }
  const request = apiClient.post('/api/v1/monitors', { name: 'belongs to A' })
  const rejected = assert.rejects(request, isCancel)
  await refreshing.promise
  organizations.selectOrganization('B')
  finishRefresh.resolve()
  await rejected
  assert.deepEqual(attempts, [{ organization: 'A', data: '{"name":"belongs to A"}' }])
})

test('refresh still retries within the same organization', async (t) => {
  context(t)
  const attempts = []
  apiClient.defaults.adapter = async (config) => {
    attempts.push(config.headers.get('X-Organization-ID'))
    if (attempts.length === 1) {
      throw new AxiosError('Expired token', 'ERR_BAD_REQUEST', config, null, {
        ...response(config),
        status: 401,
      })
    }
    return response(config, { id: 'created-in-A' })
  }
  const result = await apiClient.post('/api/v1/monitors', { name: 'A monitor' })
  assert.equal(result.data.id, 'created-in-A')
  assert.deepEqual(attempts, ['A', 'A'])
})

test('late responses and errors cannot overwrite another organization in any list store', async (t) => {
  for (const { file, useStore, load, field } of stores) {
    for (const outcome of ['success', 'error', 'unauthorized']) {
      await t.test(`${file}: late A ${outcome} after B`, async (t) => {
        const { organizations, auth } = context(t)
        auth.refreshAccessToken = async () => {
          throw new Error('Stale 401 must not refresh')
        }
        const pending = new Map()
        const started = new Map([
          ['A', deferred()],
          ['B', deferred()],
        ])
        apiClient.defaults.adapter = (config) => {
          const result = deferred()
          pending.set(config.headers.get('X-Organization-ID'), { ...result, config })
          started.get(config.headers.get('X-Organization-ID')).resolve()
          return result.promise
        }
        const store = useStore()
        const first = store[load]().catch((error) => error)
        await started.get('A').promise
        organizations.selectOrganization('B')
        const second = store[load]()
        await started.get('B').promise
        const b = pending.get('B')
        b.resolve(response(b.config, [{ id: 'B-item' }]))
        await second
        assert.deepEqual(
          store[field].map((item) => item.id),
          ['B-item'],
        )
        const a = pending.get('A')
        if (outcome === 'success') {
          a.resolve(response(a.config, [{ id: 'A-item' }]))
        } else {
          a.reject(
            new AxiosError('Old request failed', 'ERR_BAD_RESPONSE', a.config, null, {
              ...response(a.config),
              status: outcome === 'unauthorized' ? 401 : 503,
            }),
          )
        }
        const oldResult = await first
        assert.deepEqual(
          store[field].map((item) => item.id),
          ['B-item'],
        )
        assert.equal(isCancel(oldResult), true)
        assert.equal(store.loading, false)
        assert.equal(store.error, null)
      })
    }
  }
})

test('late A response cannot stop the loading indicator for B', async (t) => {
  const { organizations } = context(t)
  const pending = []
  apiClient.defaults.adapter = (config) => {
    const result = deferred()
    pending.push({ ...result, config })
    return result.promise
  }
  const { useStore, load, field } = stores[0]
  const store = useStore()
  const first = store[load]().catch((error) => error)
  organizations.selectOrganization('B')
  const second = store[load]()
  pending[0].resolve(response(pending[0].config, [{ id: 'A-item' }]))
  assert.equal(isCancel(await first), true)
  assert.equal(store.loading, true)
  assert.deepEqual(store[field], [])
  pending[1].resolve(response(pending[1].config, [{ id: 'B-item' }]))
  await second
  assert.equal(store.loading, false)
})

test('switching A to B and back still invalidates the original A response', async (t) => {
  const { organizations } = context(t)
  const pending = deferred()
  let original
  apiClient.defaults.adapter = (config) => {
    original = config
    return pending.promise
  }
  const request = apiClient.get('/api/v1/monitors')
  const rejected = assert.rejects(request, isCancel)
  organizations.selectOrganization('B')
  organizations.selectOrganization('A')
  pending.resolve(response(original, [{ id: 'stale-A' }]))
  await rejected
})

test('older loads in the same organization and cleared loads do not overwrite current state', async (t) => {
  context(t)
  const pending = []
  apiClient.defaults.adapter = (config) => {
    const result = deferred()
    pending.push({ ...result, config })
    return result.promise
  }
  const { useStore, load, field } = stores[0]
  const store = useStore()
  const first = store[load]()
  const second = store[load]()
  pending[1].resolve(response(pending[1].config, [{ id: 'new-A' }]))
  await second
  pending[0].resolve(response(pending[0].config, [{ id: 'old-A' }]))
  await first
  assert.deepEqual(
    store[field].map((item) => item.id),
    ['new-A'],
  )
  const third = store[load]()
  store.clear()
  pending[2].resolve(response(pending[2].config, [{ id: 'cleared-A' }]))
  await third
  assert.deepEqual(store[field], [])
  assert.equal(store.loading, false)
})

test('a create response after switching organizations cannot append a member in B', async (t) => {
  const { organizations } = context(t)
  const pending = deferred()
  let original
  apiClient.defaults.adapter = (config) => {
    original = config
    return pending.promise
  }
  const store = stores.find((entry) => entry.file === 'members').useStore()
  const request = store.addMember({ email: 'member@example.com', role: 'member' })
  const rejected = assert.rejects(request, isCancel)
  organizations.selectOrganization('B')
  store.members = [{ user_id: 'B-member' }]
  pending.resolve(response(original, { user_id: 'A-member' }))
  await rejected
  assert.deepEqual(
    store.members.map((member) => member.user_id),
    ['B-member'],
  )
})
