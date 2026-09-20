import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { renderToString } from '@vue/server-renderer'
import { AxiosError } from 'axios'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'
import { createSSRApp } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

let server
let apiClient
let useAuthStore
let RegisterView
let LoginView

before(async () => {
  server = await createServer({
    configFile: false,
    root: fileURLToPath(new URL('..', import.meta.url)),
    plugins: [vue()],
    resolve: { alias: { '@': fileURLToPath(new URL('../src', import.meta.url)) } },
    server: { middlewareMode: true, hmr: false, ws: false, watch: null },
    optimizeDeps: { noDiscovery: true },
  })
  ;({ default: apiClient } = await server.ssrLoadModule('/src/api/client.ts'))
  ;({ useAuthStore } = await server.ssrLoadModule('/src/stores/auth.ts'))
  ;({ default: RegisterView } = await server.ssrLoadModule('/src/views/RegisterView.vue'))
  ;({ default: LoginView } = await server.ssrLoadModule('/src/views/LoginView.vue'))
})

after(async () => server?.close())

async function context(t, failurePath) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/register', name: 'register', component: RegisterView },
      { path: '/login', name: 'login', component: LoginView },
      { path: '/dashboard', name: 'dashboard', component: { render: () => null } },
    ],
  })
  await router.push('/register')
  await router.isReady()
  const requests = []
  apiClient.defaults.adapter = async (config) => {
    requests.push(config)
    const response = { config, status: 200, statusText: 'OK', headers: {}, data: {} }
    if (config.url === failurePath) {
      throw new AxiosError('Request failed', 'ERR_BAD_RESPONSE', config, null, {
        ...response,
        status: failurePath.endsWith('register') ? 409 : 503,
        data: { detail: 'Rejected request' },
      })
    }
    if (config.url.endsWith('/register')) {
      return { ...response, status: 201, data: { id: 'new-user', email: 'owner@example.com' } }
    }
    if (config.url.endsWith('/login')) {
      return { ...response, data: { access_token: 'new-token', token_type: 'bearer' } }
    }
    if (config.url.endsWith('/me')) {
      return { ...response, data: { id: 'new-user', email: 'owner@example.com' } }
    }
    throw new Error(`Unexpected request: ${config.url}`)
  }
  let form
  const app = createSSRApp({
    setup() {
      form = RegisterView.setup({}, { expose() {} })
      return () => null
    },
  })
  app.use(pinia)
  app.use(router)
  await renderToString(app)
  form.organizationName.value = 'My organization'
  form.email.value = 'owner@example.com'
  form.password.value = 'new-password'
  form.passwordConfirmation.value = 'new-password'
  t.after(() => {
    auth.clearAuth()
    disposePinia(pinia)
  })
  return { form, auth, router, pinia, requests }
}

test('registration signs in with the submitted credentials and opens dashboard', async (t) => {
  const { form, auth, router, requests } = await context(t)

  await Promise.all([form.submitRegistration(), form.submitRegistration()])

  assert.equal(router.currentRoute.value.name, 'dashboard')
  assert.equal(auth.isAuthenticated, true)
  assert.equal(form.isSubmitting.value, false)
  assert.deepEqual(
    requests.map((request) => request.url),
    ['/api/v1/auth/register', '/api/v1/auth/login', '/api/v1/auth/me'],
  )
  assert.deepEqual(JSON.parse(requests[1].data), {
    email: 'owner@example.com',
    password: 'new-password',
  })
  assert.equal(requests[2].headers.get('Authorization'), 'Bearer new-token')
})

for (const endpoint of ['login', 'me']) {
  test(`failed ${endpoint} after registration explains that the account already exists`, async (t) => {
    const { form, auth, router, pinia, requests } = await context(t, `/api/v1/auth/${endpoint}`)

    await form.submitRegistration()

    assert.equal(router.currentRoute.value.name, 'login')
    assert.equal(router.currentRoute.value.query.registered, '1')
    assert.equal(auth.isAuthenticated, false)
    assert.equal(form.isSubmitting.value, false)
    assert.equal(requests.filter((request) => request.url.endsWith('/register')).length, 1)
    const app = createSSRApp(LoginView)
    app.use(pinia)
    app.use(router)
    const html = await renderToString(app)
    assert.match(html, /Account created\. Automatic sign-in failed\. Please sign in\./)
  })
}

test('failed registration stays on the form and does not attempt login', async (t) => {
  const { form, auth, router, requests } = await context(t, '/api/v1/auth/register')

  await form.submitRegistration()

  assert.equal(router.currentRoute.value.name, 'register')
  assert.equal(auth.isAuthenticated, false)
  assert.equal(form.errorMessage.value, 'Rejected request')
  assert.equal(form.isSubmitting.value, false)
  assert.equal(requests.length, 1)
})
