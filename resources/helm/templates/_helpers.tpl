{{- define "agent-mesh.imageStreamName" -}}
{{- $name := printf "%s-%s" .base (.root.Values.namespace | default .root.Release.Namespace) -}}
{{- if gt (len $name) 63 -}}
{{- printf "%s-%s" ($name | trunc 54 | trimSuffix "-") ($name | sha256sum | trunc 8) -}}
{{- else -}}
{{- $name -}}
{{- end -}}
{{- end -}}

{{- define "agent-mesh.imageStreamRef" -}}
{{- printf "%s/%s/%s:%s" .root.Values.imageStreams.registry .root.Values.imageStreams.namespace (include "agent-mesh.imageStreamName" (dict "root" .root "base" .base)) .tag -}}
{{- end -}}
