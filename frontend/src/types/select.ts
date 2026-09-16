export interface SelectOption<T extends string = string> {
  value: T
  label: string
  disabled?: boolean
}
