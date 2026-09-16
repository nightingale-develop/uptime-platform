<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

import { confirmation, resolveConfirmation } from '@/composables/confirmation'

const dialog = ref<HTMLDialogElement | null>(null)
const cancelButton = ref<HTMLButtonElement | null>(null)

watch(
  () => confirmation.open,
  (isOpen) => {
    const element = dialog.value

    if (!element) {
      return
    }

    if (isOpen && !element.open) {
      element.showModal()
      cancelButton.value?.focus()
    } else if (!isOpen && element.open) {
      element.close()
    }
  },
  {
    flush: 'post',
  },
)

function handleCancel(event: Event): void {
  event.preventDefault()

  resolveConfirmation(false)
}

function handleBackdropClick(event: MouseEvent): void {
  if (event.target === dialog.value) {
    resolveConfirmation(false)
  }
}

function handleClose(): void {
  if (confirmation.open) {
    resolveConfirmation(false)
  }
}

onBeforeUnmount(() => {
  if (confirmation.open) {
    resolveConfirmation(false)
  }
})
</script>

<template>
  <dialog
    ref="dialog"
    class="confirm-dialog"
    aria-labelledby="confirm-dialog-title"
    aria-describedby="confirm-dialog-message"
    @cancel="handleCancel"
    @close="handleClose"
    @click="handleBackdropClick"
  >
    <div class="confirm-dialog__content">
      <h2 id="confirm-dialog-title">
        {{ confirmation.title }}
      </h2>

      <p id="confirm-dialog-message">
        {{ confirmation.message }}
      </p>

      <div class="confirm-dialog__actions">
        <button
          ref="cancelButton"
          class="button-secondary"
          type="button"
          @click="resolveConfirmation(false)"
        >
          Cancel
        </button>

        <button class="button-danger" type="button" @click="resolveConfirmation(true)">
          {{ confirmation.confirmLabel }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<style lang="scss">
@use '@/assets/scss/components/confirm-dialog';
</style>
