import { computed, onScopeDispose, shallowRef } from 'vue'

const activeMenu = shallowRef<symbol | null>(null)

export function useSelectMenu() {
  const menu = Symbol('select-menu')
  const isOpen = computed(() => activeMenu.value === menu)

  function open(): void {
    activeMenu.value = menu
  }

  function close(): void {
    if (isOpen.value) {
      activeMenu.value = null
    }
  }

  onScopeDispose(close)

  return { isOpen, open, close }
}
