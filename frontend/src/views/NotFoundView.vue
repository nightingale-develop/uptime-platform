<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
</script>

<template>
  <main class="not-found">
    <div class="not-found__content">
      <span class="not-found__code">404</span>

      <h1>Page not found</h1>

      <p>The page you are looking for does not exist or may have been moved.</p>

      <RouterLink class="button-primary" :to="authStore.isAuthenticated ? '/dashboard' : '/login'">
        {{ authStore.isAuthenticated ? 'Back to dashboard' : 'Sign in' }}
      </RouterLink>
    </div>
  </main>
</template>

<style scoped lang="scss">
@use '@/assets/scss/variables' as *;

.not-found {
  display: flex;
  align-items: center;
  justify-content: center;

  min-height: 100vh;
  min-height: 100dvh;
  padding: 24px;

  &__content {
    width: 100%;
    max-width: 440px;

    text-align: center;
  }

  &__code {
    color: $color-primary;
    font-size: clamp(80px, 20vw, 128px);
    font-weight: 800;
    line-height: 1;
  }

  h1 {
    margin: 20px 0 12px;

    color: $color-heading;
    font-size: 28px;
  }

  p {
    margin: 0 0 32px;

    color: $color-muted;
    line-height: 1.6;
  }
}
</style>
