{{- define "uptime-platform.migrationWaitInitContainer" -}}
- name: wait-for-migrations
  image: "{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}"
  imagePullPolicy: {{ .Values.backend.image.pullPolicy }}
  securityContext:
    {{- include "uptime-platform.containerSecurityContext" . | nindent 4 }}
  env:
    - name: DATABASE_URL
      valueFrom:
        secretKeyRef:
          name: {{ include "uptime-platform.secretName" . }}
          key: DATABASE_URL
    - name: MIGRATION_WAIT_ATTEMPTS
      value: {{ .Values.migrations.waitAttempts | quote }}
    - name: MIGRATION_WAIT_INTERVAL_SECONDS
      value: {{ .Values.migrations.waitIntervalSeconds | quote }}
  command:
    - /bin/sh
    - -c
    - |
      python - <<'PY'
      import asyncio
      import os
      import asyncpg
      from alembic.config import Config
      from alembic.script import ScriptDirectory

      config = Config("alembic.ini")
      expected = ScriptDirectory.from_config(config).get_current_head()
      dsn = os.environ["DATABASE_URL"].replace(
          "postgresql+asyncpg://", "postgresql://", 1
      )
      attempts = int(os.environ["MIGRATION_WAIT_ATTEMPTS"])
      interval = int(os.environ["MIGRATION_WAIT_INTERVAL_SECONDS"])

      async def wait_for_migrations() -> None:
          last_error = None
          for _ in range(attempts):
              try:
                  connection = await asyncpg.connect(dsn)
                  try:
                      current = await connection.fetchval(
                          "SELECT version_num FROM alembic_version LIMIT 1"
                      )
                  except Exception:
                      current = None
                  finally:
                      await connection.close()

                  if current == expected:
                      return
              except Exception as exc:
                  last_error = exc

              await asyncio.sleep(interval)

          raise RuntimeError(
              f"database migrations did not reach {expected}; last error: {last_error}"
          )

      asyncio.run(wait_for_migrations())
      PY
{{- end -}}
