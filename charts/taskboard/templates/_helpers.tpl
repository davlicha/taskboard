{{/* Ім'я чарта */}}
{{- define "taskboard.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Повне ім'я об'єктів: будується з імені релізу, тому чарт можна встановити
кілька разів в один кластер / namespace.
*/}}
{{- define "taskboard.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/* Ім'я компонента: <fullname>-<component> */}}
{{- define "taskboard.componentName" -}}
{{- printf "%s-%s" (include "taskboard.fullname" .root) .component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "taskboard.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Загальний набір міток. Виклик: include "taskboard.labels" (dict "root" $ "component" "api") */}}
{{- define "taskboard.labels" -}}
helm.sh/chart: {{ include "taskboard.chart" .root }}
{{ include "taskboard.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/part-of: taskboard
{{- end }}

{{/* Мітки для selector — незмінні між версіями */}}
{{- define "taskboard.selectorLabels" -}}
app.kubernetes.io/name: {{ include "taskboard.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- if .component }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
{{- end }}

{{/* Образ: repository:tag (tag за замовчуванням = appVersion) */}}
{{- define "taskboard.image" -}}
{{- printf "%s:%s" .image.repository (.image.tag | default .root.Chart.AppVersion | toString) }}
{{- end }}

{{/* Секрет з обліковими даними БД */}}
{{- define "taskboard.dbSecretName" -}}
{{- .Values.postgres.auth.existingSecret | default (include "taskboard.componentName" (dict "root" . "component" "db")) }}
{{- end }}

{{- define "taskboard.dbHost" -}}
{{- include "taskboard.componentName" (dict "root" . "component" "postgres") }}
{{- end }}

{{/* Шаблон пода API — спільний для Deployment і Rollout (ЛР-6) */}}
{{- define "taskboard.api.podTemplate" -}}
metadata:
  labels:
    {{- include "taskboard.labels" (dict "root" . "component" "api") | nindent 4 }}
    app.kubernetes.io/version: {{ .Values.api.image.tag | default .Chart.AppVersion | quote }}
  annotations:
    checksum/config: {{ include (print .Template.BasePath "/api-configmap.yaml") . | sha256sum }}
spec:
  {{- with .Values.imagePullSecrets }}
  imagePullSecrets:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  terminationGracePeriodSeconds: 30
  containers:
    - name: api
      image: {{ include "taskboard.image" (dict "root" . "image" .Values.api.image) }}
      imagePullPolicy: {{ .Values.api.image.pullPolicy }}
      ports:
        - name: http
          containerPort: 8000
      envFrom:
        - configMapRef:
            name: {{ include "taskboard.componentName" (dict "root" . "component" "api") }}
      env:
        - name: POSTGRES_USER
          valueFrom: { secretKeyRef: { name: {{ include "taskboard.dbSecretName" . }}, key: POSTGRES_USER } }
        - name: POSTGRES_PASSWORD
          valueFrom: { secretKeyRef: { name: {{ include "taskboard.dbSecretName" . }}, key: POSTGRES_PASSWORD } }
        - name: POSTGRES_DB
          valueFrom: { secretKeyRef: { name: {{ include "taskboard.dbSecretName" . }}, key: POSTGRES_DB } }
        - name: DATABASE_URL
          value: "postgresql+psycopg://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@{{ include "taskboard.dbHost" . }}:5432/$(POSTGRES_DB)"
        - name: INSTANCE_ID
          valueFrom: { fieldRef: { fieldPath: metadata.name } }
        # ЛР-7: прямо в шаблоні пода, а не в спільному ConfigMap — значення належить
        # конкретному ReplicaSet, і після abort stable-поди не підхоплять "погане" значення
        - name: FAIL_RATE
          value: {{ .Values.api.failRate | quote }}
        - name: SLOW_MS
          value: {{ .Values.api.slowMs | quote }}
      resources:
        {{- toYaml .Values.api.resources | nindent 8 }}
      readinessProbe:
        httpGet: { path: /health, port: http }
        initialDelaySeconds: 3
        periodSeconds: 5
      lifecycle:
        preStop:
          exec: { command: ["sleep", "5"] }
      livenessProbe:
        httpGet: { path: /livez, port: http }
        initialDelaySeconds: 10
        periodSeconds: 10
{{- end }}
