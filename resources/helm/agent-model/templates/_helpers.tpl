{{/* Resolve model defaults first, then apply user overrides. */}}
{{- define "agent-model.config" -}}
{{- $profile := index .Values.profiles .Values.modelVariant -}}
{{- if not $profile -}}
{{- fail "modelVariant must be qwen or muse-glimmer" -}}
{{- end -}}
{{- mergeOverwrite (deepCopy $profile) (omit .Values "profiles" "modelVariant") | toYaml -}}
{{- end -}}

{{/* Stable names allow changing models within a release. */}}
{{- define "agent-model.fullname" -}}
{{- .Release.Name | trunc 57 | trimSuffix "-" -}}
{{- end -}}
