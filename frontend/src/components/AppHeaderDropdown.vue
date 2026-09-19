<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useSelectMenu } from '@/composables/useSelectMenu'

defineProps<{
  label: string
  active: boolean
}>()

const route = useRoute()
const dropdown = ref<HTMLDetailsElement | null>(null)
const trigger = ref<HTMLElement | null>(null)
const { isOpen, open, close } = useSelectMenu()

function toggle(): void {
  if (isOpen.value) {
    close()
  } else {
    open()
  }
}

function handleOutsideInteraction(event: Event): void {
  if (event.target instanceof Node && !dropdown.value?.contains(event.target)) {
    close()
  }
}

function handleEscape(): void {
  close()
  trigger.value?.focus()
}

watch(() => route.fullPath, close)

onMounted(() => {
  document.addEventListener('pointerdown', handleOutsideInteraction, true)
  document.addEventListener('click', handleOutsideInteraction, true)
  document.addEventListener('focusin', handleOutsideInteraction)
  window.addEventListener('resize', close)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleOutsideInteraction, true)
  document.removeEventListener('click', handleOutsideInteraction, true)
  document.removeEventListener('focusin', handleOutsideInteraction)
  window.removeEventListener('resize', close)
})
</script>

<template>
  <details
    ref="dropdown"
    class="app-header__dropdown"
    :open="isOpen"
    @keydown.esc.stop.prevent="handleEscape"
  >
    <summary
      ref="trigger"
      class="app-header__dropdown-toggle"
      :class="{ 'app-header__dropdown-toggle--active': active }"
      :aria-expanded="isOpen"
      @click.prevent="toggle"
    >
      {{ label }}
    </summary>

    <div class="app-header__dropdown-menu" @click="close">
      <slot />
    </div>
  </details>
</template>
