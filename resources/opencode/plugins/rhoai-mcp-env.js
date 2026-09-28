/**
 * rhoai-mcp-env plugin
 *
 * Injects RHOAI_MCP_URL and OCP_TOKEN into the OpenCode shell environment
 * via the shell.env hook so that the rhoai-mcp MCP server config can use
 * {env:RHOAI_MCP_URL} and {env:OCP_TOKEN} without any hardcoded values.
 *
 * Route discovery strategy (no namespace configuration required):
 *   1. Cluster-wide label search  — oc get route -A -l app=rhoai-mcp
 *      Fast, single call. Requires cluster-wide 'get routes' permission.
 *
 *   2. Per-permitted-namespace search — if step 1 is denied, fetches the list
 *      of namespaces the user can access (oc projects -q) and searches each
 *      one in parallel. Works within any permission scope.
 *
 * The Helm chart sets app=rhoai-mcp on the Route — that label is the only
 * thing this plugin relies on. No namespace config needed anywhere.
 */

export const RhoaiMcpEnvPlugin = async ({ $ }) => {
  return {
    "shell.env": async () => {
      // ── Token and Route discovery run concurrently ─────────────────────────
      // allSettled ensures both errors are reported if both fail simultaneously,
      // rather than Promise.all which surfaces only the first rejection.
      const [tokenOutcome, hostOutcome] = await Promise.allSettled([
        resolveToken($),
        resolveHost($)
      ])

      const errors = [tokenOutcome, hostOutcome]
        .filter(o => o.status === "rejected")
        .map(o => o.reason?.message ?? String(o.reason))

      if (errors.length) {
        throw new Error(errors.join("\n"))
      }

      return {
        RHOAI_MCP_URL: `https://${hostOutcome.value}`,
        OCP_TOKEN: tokenOutcome.value
      }
    }
  }
}

// ── Token ────────────────────────────────────────────────────────────────────

async function resolveToken($) {
  try {
    const result = await $`oc whoami -t`
    return result.stdout.trim()
  } catch (err) {
    throw new Error(
      "[rhoai-mcp-env] oc whoami -t failed — ensure you are logged in to OpenShift.\n" +
      err.message
    )
  }
}

// ── Route host ───────────────────────────────────────────────────────────────

async function resolveHost($) {
  // Strategy 1: cluster-wide label search (single call, fast)
  const host = await clusterWideSearch($)
  if (host) return host

  // Strategy 2: search every namespace the user is permitted to access
  return permittedNamespaceSearch($)
}

async function clusterWideSearch($) {
  try {
    const result = await $`oc get route -A -l app=rhoai-mcp -o jsonpath={.items[0].spec.host}`
    return result.stdout.trim() || null
  } catch (err) {
    // Only fall through for permission errors. Any other failure (oc not found,
    // cluster unreachable, etc.) is a real error that should not be silenced.
    if (/forbidden|cannot list|not allowed/i.test(err.message ?? err.stderr ?? "")) {
      return null
    }
    throw new Error(
      "[rhoai-mcp-env] Cluster-wide Route search failed unexpectedly.\n" +
      (err.message ?? String(err))
    )
  }
}

async function permittedNamespaceSearch($) {
  // Fetch all namespaces the user can see
  let namespaces
  try {
    const result = await $`oc projects -q`
    namespaces = result.stdout
      .split("\n")
      .map(n => n.trim())
      .filter(Boolean)
  } catch (err) {
    throw new Error(
      "[rhoai-mcp-env] Could not list accessible namespaces via 'oc projects -q'.\n" +
      err.message
    )
  }

  if (!namespaces.length) {
    throw new Error(
      "[rhoai-mcp-env] No accessible namespaces found. " +
      "Ensure you are logged in to OpenShift."
    )
  }

  // Search all permitted namespaces in parallel
  const results = await Promise.allSettled(
    namespaces.map(ns =>
      $`oc get route -n ${ns} -l app=rhoai-mcp -o jsonpath={.items[0].spec.host}`
    )
  )

  const host = results
    .filter(r => r.status === "fulfilled")
    .map(r => r.value.stdout.trim())
    .find(h => h.length > 0)

  if (!host) {
    throw new Error(
      "[rhoai-mcp-env] No Route with label app=rhoai-mcp found in any " +
      `of the ${namespaces.length} accessible namespace(s). ` +
      "Has the Helm chart been deployed?"
    )
  }

  return host
}
