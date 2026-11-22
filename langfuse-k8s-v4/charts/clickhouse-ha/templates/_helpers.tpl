{{- define "ch.name" -}}{{ .Release.Name }}{{- end -}}
{{- define "ch.keeper" -}}{{ .Release.Name }}-keeper{{- end -}}
{{- define "ch.labels" -}}
app.kubernetes.io/name: clickhouse-ha
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
{{- define "ch.selector" -}}
app.kubernetes.io/name: clickhouse-ha
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
{{- define "ch.image" -}}
{{- if .image.digest -}}{{ .image.repository }}@{{ .image.digest }}{{- else -}}{{ .image.repository }}:{{ .image.tag }}{{- end -}}
{{- end -}}
{{- define "ch.affinity" -}}
{{- if eq .Values.podAntiAffinityPreset "hard" }}
podAntiAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    - topologyKey: kubernetes.io/hostname
      labelSelector:
        matchLabels: {{- include "ch.selector" (dict "Release" .Release "component" .component) | nindent 10 }}
{{- else if eq .Values.podAntiAffinityPreset "soft" }}
podAntiAffinity:
  preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        topologyKey: kubernetes.io/hostname
        labelSelector:
          matchLabels: {{- include "ch.selector" (dict "Release" .Release "component" .component) | nindent 12 }}
{{- end }}
{{- end -}}
