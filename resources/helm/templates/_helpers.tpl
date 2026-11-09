{{- define "agent-mesh.imageStreamName" -}}
{{- $name := printf "%s-%s" .base (.root.Values.namespace | default .root.Release.Namespace) -}}
{{- if gt (len $name) 63 -}}
{{- printf "%s-%s" ($name | trunc 54 | trimSuffix "-") ($name | sha256sum | trunc 8) -}}
{{- else -}}
{{- $name -}}
{{- end -}}
{{- end -}}

{{- define "agent-mesh.imageStreamRef" -}}
{{- printf "%s/%s/%s:%s" .root.Values.imageStreams.registry .root.Values.namespace (include "agent-mesh.imageStreamName" (dict "root" .root "base" .base)) .tag -}}
{{- end -}}

{{- define "agent-mesh.awsCompatibleStorage.fullname" -}}
{{- $storage := index .Values "aws-compatible-storage" -}}
{{- $storage.fullnameOverride | default "aws-compatible-storage" -}}
{{- end -}}

{{- define "agent-mesh.awsCompatibleStorage.secretName" -}}
{{- $storage := index .Values "aws-compatible-storage" -}}
{{- $storage.s3.existingSecret | default (printf "%s-credentials" (include "agent-mesh.awsCompatibleStorage.fullname" .)) -}}
{{- end -}}

{{- define "agent-mesh.awsCompatibleStorage.apiPort" -}}
{{- $storage := index .Values "aws-compatible-storage" -}}
{{- if and $storage.service $storage.service.s3Port -}}
{{- $storage.service.s3Port -}}
{{- else if eq .Values.objectStoreBackend "minio" -}}
{{- 9000 -}}
{{- else -}}
{{- 7480 -}}
{{- end -}}
{{- end -}}

{{- define "agent-mesh.awsCompatibleStorage.uiPort" -}}
{{- $storage := index .Values "aws-compatible-storage" -}}
{{- $storage.service.port | default 5000 -}}
{{- end -}}
