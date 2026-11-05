/**
 * rhoai-mcp-env plugin
 *
 * Injects RHOAI_MCP_URL and RHOAI_MCP_TOKEN into the OpenCode shell environment
 * via the shell.env hook so that the rhoai-mcp MCP server config can use
 * {env:RHOAI_MCP_URL} and {env:RHOAI_MCP_TOKEN} without any hardcoded values.
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
  const log = async (msg) => {
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] ${msg}" >> /tmp/rhoai-mcp-debug.log`
  }

  return {
    "shell.env": async () => {
      await log("Starting discovery...")
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
        await log("Discovery failed: " + errors.join("\n"))
        throw new Error(errors.join("\n"))
      }

      await log(`Success: URL=https://${hostOutcome.value}, Token=${tokenOutcome.value.substring(0, 10)}...`)
      return {
        RHOAI_MCP_URL: `https://${hostOutcome.value}`,
        ...(tokenOutcome.value ? { RHOAI_MCP_TOKEN: tokenOutcome.value } : {})
      }
    }
  }
}

// ── Token ────────────────────────────────────────────────────────────────────

async function resolveToken($) {
  try {
    const result = await $`oc whoami -t`
    const token = result.stdout.trim()
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] resolveToken: found token ${token.substring(0, 10)}..." >> /tmp/rhoai-mcp-debug.log`
    return token
  } catch (err) {
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] resolveToken failed: ${err.message}" >> /tmp/rhoai-mcp-debug.log`
    throw new Error(
      "[rhoai-mcp-env] oc whoami -t failed — ensure you are logged in to OpenShift.\n" +
      err.message
    )
  }
}

// ── Route host ───────────────────────────────────────────────────────────────

async function resolveHost($) {
  await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] resolveHost: starting..." >> /tmp/rhoai-mcp-debug.log`
  // Strategy 1: cluster-wide label search (single call, fast)
  const host = await clusterWideSearch($)
  if (host) {
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] resolveHost: found host via clusterWideSearch: ${host}" >> /tmp/rhoai-mcp-debug.log`
    return host
  }

  // Strategy 2: search every namespace the user is permitted to access
  await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] resolveHost: falling back to permittedNamespaceSearch" >> /tmp/rhoai-mcp-debug.log`
  return permittedNamespaceSearch($)
}

async function clusterWideSearch($) {
  try {
    const result = await $`oc get route -A -l app=rhoai-mcp -o jsonpath={.items[0].spec.host}`
    const host = result.stdout.trim() || null
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] clusterWideSearch result: ${host}" >> /tmp/rhoai-mcp-debug.log`
    return host
  } catch (err) {
    if (/forbidden|cannot list|not allowed/i.test(err.message ?? err.stderr ?? "")) {
      await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] clusterWideSearch: permission denied, falling back" >> /tmp/rhoai-mcp-debug.log`
      return null
    }
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] clusterWideSearch unexpected error: ${err.message}" >> /tmp/rhoai-mcp-debug.log`
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
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] permittedNamespaceSearch: found ${namespaces.length} namespaces" >> /tmp/rhoai-mcp-debug.log`
  } catch (err) {
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] permittedNamespaceSearch: oc projects -q failed: ${err.message}" >> /tmp/rhoai-mcp-debug.log`
    throw new Error(
      "[rhoai-mcp-env] Could not list accessible namespaces via 'oc projects -q'.\n" +
      err.message
    )
  }

  if (!namespaces.length) {
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] permittedNamespaceSearch: no namespaces found" >> /tmp/rhoai-mcp-debug.log`
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
    await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] permittedNamespaceSearch: no route found in any namespace" >> /tmp/rhoai-mcp-debug.log`
    throw new Error(
      "[rhoai-mcp-env] No Route with label app=rhoai-mcp found in any " +
      `of the ${namespaces.length} accessible namespace(s). ` +
      "Has the Helm chart been deployed?"
    )
  }

  await $`echo "$(date '+%Y-%m-%d %H:%M:%S') [rhoai-mcp-env] permittedNamespaceSearch: found host ${host}" >> /tmp/rhoai-mcp-debug.log`
  return host
}
