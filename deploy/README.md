# Deployed stack definitions (Portainer, endpoint 3)

Version-controlled **copies** of the Portainer stack compose files. Portainer is the deploy
source of truth (`/data/compose/<id>/docker-compose.yml` on the NAS) — editing a file here
changes nothing until you redeploy it.

| Stack | File | Runs |
|---|---|---|
| 1 `bar-assistant` | [bar-assistant-stack.yml](bar-assistant-stack.yml) | BA API (`:3000`), Salt Rim (`:3001`), Meilisearch, Redis, autoheal |
| 2 `nginx` | [nginx-proxy-manager-stack.yml](nginx-proxy-manager-stack.yml) | Nginx Proxy Manager — public TLS entrypoint |
| 5 `bar-assistant-mcp` | [bar-assistant-mcp-stack.yml](bar-assistant-mcp-stack.yml) | Remote MCP server (`:8100`, HTTP+OAuth) |
| 8 `bar-assistant-sandbox` | _not tracked_ | Throwaway flavor sandbox (`:3002`/`:3003`) |

## Redeploying

```
PUT https://192.168.1.64:19943/api/stacks/<id>?endpointId=3
{"StackFileContent": "<file contents>", "Env": [...], "Prune": false}
```

**Env values are not in these files.** Stack 1 has four (`MEILI_MASTER_KEY`, `API_URL`,
`MEILISEARCH_URL`, `ALLOW_REGISTRATION`) stored in Portainer's stack Env — they must be passed
back on every PUT or they are lost. Stacks 2 and 5 have empty Env.

A PUT **recreates** containers; a restart does not re-pull a rebuilt image tag. Recreating
stack 5 drops in-memory OAuth tokens, so iOS must re-auth (which is when it picks up
`usage_rules.md` changes).

## Keep these in sync

Drift here is invisible to git — that is how `bar-assistant-web` ended up running as a renamed
`4983e5040672_bar-assistant-web` container. After changing a stack in Portainer, update the
matching file.

See CLAUDE.md (Redeploying / Triaging a down stack) and the `deployment_guide` +
`infra_nas_npm` memories for the wider architecture.
