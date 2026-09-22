export type NotificationDestinationType = 'webhook' | 'telegram' | 'email' | 'slack'

export type EmailSecurity = 'none' | 'starttls' | 'tls'

export interface WebhookDestinationConfigCreate {
  url: string
  secret: string
}

export interface TelegramDestinationConfigCreate {
  bot_token: string
  chat_id: string
}

export interface EmailDestinationConfigCreate {
  host: string
  port: number
  username: string | null
  password: string | null
  from_email: string
  to_email: string
  security: EmailSecurity
}

interface BaseNotificationDestinationCreate {
  name: string
  enabled: boolean
}

export interface SlackDestinationConfigCreate {
  webhook_url: string
}

export type NotificationDestinationCreate =
  | (BaseNotificationDestinationCreate & {
      destination_type: 'slack'
      config: SlackDestinationConfigCreate
    })
  | (BaseNotificationDestinationCreate & {
      destination_type: 'webhook'
      config: WebhookDestinationConfigCreate
    })
  | (BaseNotificationDestinationCreate & {
      destination_type: 'telegram'
      config: TelegramDestinationConfigCreate
    })
  | (BaseNotificationDestinationCreate & {
      destination_type: 'email'
      config: EmailDestinationConfigCreate
    })

export interface WebhookDestinationConfigResponse {
  url: string
}

export interface TelegramDestinationConfigResponse {
  chat_id: string
}

export interface EmailDestinationConfigResponse {
  host: string
  port: number
  username: string | null
  from_email: string
  to_email: string
  security: EmailSecurity
}

interface BaseNotificationDestination {
  id: string
  name: string
  enabled: boolean
  created_at: string
}

export type NotificationDestination =
  | (BaseNotificationDestination & {
      destination_type: 'slack'
      config: Record<string, never>
    })
  | (BaseNotificationDestination & {
      destination_type: 'webhook'
      config: WebhookDestinationConfigResponse
    })
  | (BaseNotificationDestination & {
      destination_type: 'telegram'
      config: TelegramDestinationConfigResponse
    })
  | (BaseNotificationDestination & {
      destination_type: 'email'
      config: EmailDestinationConfigResponse
    })

export interface WebhookDestinationConfigUpdate {
  url?: string | null
  secret?: string | null
}

export interface TelegramDestinationConfigUpdate {
  bot_token?: string | null
  chat_id?: string | null
}

export interface EmailDestinationConfigUpdate {
  host?: string | null
  port?: number | null
  username?: string | null
  password?: string | null
  from_email?: string | null
  to_email?: string | null
  security?: EmailSecurity | null
}

export interface SlackDestinationConfigUpdate {
  webhook_url?: string
}

export type NotificationDestinationConfigUpdate =
  | SlackDestinationConfigUpdate
  | WebhookDestinationConfigUpdate
  | TelegramDestinationConfigUpdate
  | EmailDestinationConfigUpdate

export interface NotificationDestinationUpdate {
  name?: string
  enabled?: boolean
  config?: NotificationDestinationConfigUpdate
}
