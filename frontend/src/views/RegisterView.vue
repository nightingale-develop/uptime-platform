<script setup lang="ts">
import axios from 'axios'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const organizationName = ref('')
const email = ref('')
const password = ref('')
const passwordConfirmation = ref('')

const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

async function submitRegistration(): Promise<void> {
  if (isSubmitting.value) {
    return
  }

  errorMessage.value = null

  if (password.value !== passwordConfirmation.value) {
    errorMessage.value = 'Passwords do not match'
    return
  }

  isSubmitting.value = true

  const credentials = { email: email.value, password: password.value }
  let accountCreated = false

  try {
    await authStore.register({
      ...credentials,
      organization_name: organizationName.value,
    })

    accountCreated = true
    await authStore.login(credentials)
    await router.replace('/dashboard')
  } catch (error) {
    if (accountCreated) {
      await router.replace({ name: 'login', query: { registered: '1' } })
      return
    }

    if (axios.isAxiosError(error)) {
      const detail = error.response?.data?.detail

      if (typeof detail === 'string') {
        errorMessage.value = detail
      } else {
        errorMessage.value = 'Unable to create account'
      }
    } else {
      errorMessage.value = 'Unable to create account'
    }
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <main class="register-page">
    <div class="register-card">
      <div class="register-card__header">
        <h1>Create account</h1>

        <p>Create your Uptime Platform account</p>
      </div>

      <form class="register-form" @submit.prevent="submitRegistration">
        <div class="form-field">
          <label for="organization-name"> Organization name </label>

          <input
            id="organization-name"
            v-model.trim="organizationName"
            type="text"
            autocomplete="organization"
            maxlength="100"
            required
          />
        </div>

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
            autocomplete="new-password"
            minlength="8"
            maxlength="128"
            required
          />
        </div>

        <div class="form-field">
          <label for="password-confirmation"> Confirm password </label>

          <input
            id="password-confirmation"
            v-model="passwordConfirmation"
            type="password"
            autocomplete="new-password"
            minlength="8"
            maxlength="128"
            required
          />
        </div>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>

        <button class="button-primary" type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? 'Creating account...' : 'Create account' }}
        </button>
      </form>

      <p class="register-card__footer">
        Already have an account?

        <RouterLink to="/login"> Sign in </RouterLink>
      </p>
    </div>
  </main>
</template>

<style lang="scss">
@use '@/assets/scss/pages/auth';
</style>
