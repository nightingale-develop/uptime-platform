<script setup lang="ts" generic="T extends string">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'

import { useSelectMenu } from '@/composables/useSelectMenu'
import type { SelectOption } from '@/types/select.ts'

const props = withDefaults(
  defineProps<{
    id: string
    options: readonly SelectOption<T>[]
    disabled?: boolean
    ariaLabel?: string
  }>(),
  {
    disabled: false,
    ariaLabel: undefined,
  },
)

const model = defineModel<T>({ required: true })

const { isOpen, open: activateMenu, close: closeMenu } = useSelectMenu()
const trigger = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)

const menuStyle = ref<CSSProperties>({})

const selectedOption = computed(() => {
  return props.options.find((option) => {
    return option.value === model.value
  })
})

const menuId = computed(() => {
  return `${props.id}-options`
})

function updateMenuPosition(): void {
  if (!isOpen.value || !trigger.value) {
    return
  }

  const rect = trigger.value.getBoundingClientRect()

  const viewportWidth = document.documentElement.clientWidth

  const viewportHeight = window.innerHeight

  const viewportGap = 8
  const menuGap = 6

  const width = Math.min(Math.max(rect.width, 180), viewportWidth - viewportGap * 2)

  const left = Math.min(Math.max(rect.left, viewportGap), viewportWidth - width - viewportGap)

  const top = Math.min(rect.bottom + menuGap, viewportHeight - viewportGap)

  const availableHeight = Math.max(0, viewportHeight - top - viewportGap)

  menuStyle.value = {
    top: `${top}px`,
    left: `${left}px`,
    width: `${width}px`,
    maxHeight: `${Math.min(320, availableHeight)}px`,
  }
}

async function openMenu(): Promise<void> {
  if (props.disabled) {
    return
  }

  activateMenu()

  await nextTick()

  if (!isOpen.value || !trigger.value) {
    return
  }

  const rect = trigger.value.getBoundingClientRect()

  const availableHeight = window.innerHeight - rect.bottom - 14

  if (availableHeight < 140) {
    trigger.value.scrollIntoView({
      block: 'center',
      inline: 'nearest',
    })
  }

  requestAnimationFrame(updateMenuPosition)
}

async function toggleMenu(): Promise<void> {
  if (isOpen.value) {
    closeMenu()
    return
  }

  await openMenu()
}

function selectOption(option: SelectOption<T>): void {
  if (option.disabled) {
    return
  }

  model.value = option.value
  closeMenu()

  nextTick(() => {
    trigger.value?.focus()
  })
}

function handleDocumentPointerDown(event: PointerEvent): void {
  if (!isOpen.value) {
    return
  }

  const target = event.target as Node

  if (trigger.value?.contains(target) || menu.value?.contains(target)) {
    return
  }

  closeMenu()
}

function handleViewportChange(): void {
  updateMenuPosition()
}

watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) {
      closeMenu()
    }
  },
)

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)

  window.addEventListener('resize', handleViewportChange)

  window.addEventListener('scroll', handleViewportChange, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown, true)

  window.removeEventListener('resize', handleViewportChange)

  window.removeEventListener('scroll', handleViewportChange, true)
})
</script>

<template>
  <div class="app-select">
    <button
      :id="id"
      ref="trigger"
      class="app-select__trigger"
      type="button"
      :disabled="disabled"
      :aria-label="ariaLabel"
      :aria-expanded="isOpen"
      :aria-controls="menuId"
      aria-haspopup="listbox"
      @click="toggleMenu"
      @keydown.esc="closeMenu"
      @keydown.down.prevent="openMenu"
    >
      <span class="app-select__value">
        {{ selectedOption?.label ?? model }}
      </span>

      <span
        class="app-select__chevron"
        :class="{
          'app-select__chevron--open': isOpen,
        }"
        aria-hidden="true"
      >
        ▾
      </span>
    </button>

    <Teleport to="body">
      <div
        v-if="isOpen"
        :id="menuId"
        ref="menu"
        class="app-select__menu"
        :style="menuStyle"
        role="listbox"
        :aria-labelledby="id"
      >
        <button
          v-for="option in options"
          :key="option.value"
          class="app-select__option"
          :class="{
            'app-select__option--selected': option.value === model,
          }"
          type="button"
          role="option"
          :aria-selected="option.value === model"
          :disabled="option.disabled"
          @click="selectOption(option)"
        >
          {{ option.label }}
        </button>
      </div>
    </Teleport>
  </div>
</template>
