#!/bin/sh
# Retain omitted embedding and agent settings while replacing other application settings.
set -eu

fail() {
    printf '%s\n' "Error updating application secret: $1" >&2
    exit 1
}

[ "$#" -gt 0 ] || fail "An environment key allowlist is required."
: "${KFP_NAMESPACE:?KFP_NAMESPACE must be set}"

# Keep secret payloads in memory and off command lines and diagnostic output.
if ! existing=$(oc get secret code-understanding-env -n "$KFP_NAMESPACE" \
    --ignore-not-found -o json --request-timeout=30s 2>/dev/null); then
    fail "Could not read code-understanding-env. Check permissions and connectivity, then retry."
fi

verb=create
if [ -n "$existing" ]; then
    verb=replace
fi

if ! document=$(printf '%s\n' "${existing:-null}" | jq --args '
    $ARGS.positional as $keys
    | env as $environment
    | (. // {
        apiVersion: "v1",
        kind: "Secret",
        metadata: {name: "code-understanding-env", namespace: $environment.KFP_NAMESPACE},
        type: "Opaque"
    })
    | .data = ((.data // {}) | with_entries(select(
        .key as $key
        | ($keys | index($key)) != null
          and ($key | startswith("EMBED_LLM_") or startswith("CODE_LLM_"))
    )))
    | reduce $keys[] as $key (.;
        if $environment | has($key) then
            .data[$key] = ($environment[$key] | @base64)
        else . end
    )
' "$@" 2>/dev/null); then
    fail "Could not prepare code-understanding-env. Check its contents and the environment key allowlist."
fi

# Preserve metadata and resourceVersion so concurrent updates fail safely.
if ! printf '%s\n' "$document" | oc "$verb" -n "$KFP_NAMESPACE" -f - \
    --request-timeout=30s >/dev/null 2>&1; then
    fail "Could not $verb code-understanding-env. Check permissions or concurrent updates, then retry."
fi
printf '%s\n' "Secret code-understanding-env updated; omitted embedding and agent settings preserved."
