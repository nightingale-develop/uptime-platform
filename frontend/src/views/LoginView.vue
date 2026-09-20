<script setup lang="ts">
import axios from 'axios'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()

const authStore = useAuthStore()

const email = ref('')
const password = ref('')

const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

async function submitLogin(): Promise<void> {
  errorMessage.value = null
  isSubmitting.value = true

  try {
    await authStore.login({
      email: email.value,
      password: password.value,
    })

    const redirect = route.query.redirect

    if (typeof redirect === 'string') {
      await router.push(redirect)
    } else {
      await router.push('/dashboard')
    }
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail

      if (typeof detail === 'string') {
        errorMessage.value = detail
      } else {
        errorMessage.value = 'Unable to sign in'
      }
    } else {
      errorMessage.value = 'Unable to sign in'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <div class="login-card">
      <div class="login-card__header">
        <h1>Sign in</h1>
        <p>Sign in to Uptime Platform</p>
      </div>

      <form class="login-form" @submit.prevent="submitLogin">
        <p v-if="route.query.registered === '1'" role="status">
          Account created. Automatic sign-in failed. Please sign in.
        </p>

        <div class="form-field">
          <label for="email"> Email </label>

          <input id="email" v-model.trim="email" type="email" autocomplete="email" required />
        </div>

        <div class="form-field">
          <label for="password"> Password </label>

          <input
            id="password"
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
          />
        </div>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>

        <button class="button-primary" type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Signing in...' : 'Sign in' }}
        </button>
      </form>

      <p class="login-card__footer">
        Don't have an account?
        <RouterLink to="/register"> Create one </RouterLink>
      </p>
    </div>
  </main>
</template>

<style lang="scss">
@use '@/assets/scss/pages/auth';
</style>
