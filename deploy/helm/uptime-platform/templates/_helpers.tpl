{{- define "uptime-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "uptime-platform.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "uptime-platform.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "uptime-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "uptime-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "uptime-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "uptime-platform.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "uptime-platform.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "uptime-platform.configMapName" -}}
{{- printf "%s-config" (include "uptime-platform.fullname" .) -}}
{{- end -}}

{{- define "uptime-platform.postgresqlName" -}}
{{- printf "%s-postgresql" (include "uptime-platform.fullname" .) -}}
{{- end -}}

{{- define "uptime-platform.frontendName" -}}
{{- printf "%s-frontend" (include "uptime-platform.fullname" .) -}}
{{- end -}}

{{- define "uptime-platform.imagePullSecrets" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{- define "uptime-platform.containerSecurityContext" -}}
allowPrivilegeEscalation: {{ .Values.securityContext.allowPrivilegeEscalation }}
runAsNonRoot: {{ .Values.securityContext.runAsNonRoot }}
capabilities:
  drop:
{{- range .Values.securityContext.capabilities.drop }}
    - {{ . }}
{{- end }}
{{- if .Values.securityContext.addNetRaw }}
  add:
    - NET_RAW
{{- end }}
seccompProfile:
  type: {{ .Values.securityContext.seccompProfile.type }}
{{- end -}}
