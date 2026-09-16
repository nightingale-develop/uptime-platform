import { reactive } from 'vue'

interface ConfirmationOptions {
  title: string
  message: string
  confirmLabel?: string
}

export const confirmation = reactive({
  open: false,
  title: '',
  message: '',
  confirmLabel: 'Delete',
})

let resolveActive: ((confirmed: boolean) => void) | null = null

export function requestConfirmation(options: ConfirmationOptions): Promise<boolean> {
  if (resolveActive) {
    return Promise.resolve(false)
  }

  return new Promise<boolean>((resolve) => {
    resolveActive = resolve

    confirmation.title = options.title
    confirmation.message = options.message
    confirmation.confirmLabel = options.confirmLabel ?? 'Delete'

    confirmation.open = true
  })
}

export function resolveConfirmation(confirmed: boolean): void {
  const resolve = resolveActive

  resolveActive = null
  confirmation.open = false

  resolve?.(confirmed)
}
