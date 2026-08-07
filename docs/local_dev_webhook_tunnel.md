# Local Dev Webhook Tunnel (YCloud)

Reference doc for exposing the local FastAPI webhook endpoint to YCloud during
Phase 1 development. See the [roadmap](ROADMAPS/whatsapp_schedule_copilot_poc_roadmap_v0.1.md)
for phase context and [webhook.site vs. tunnel rationale](#why-not-webhooksite).

## Current tunnel

| | |
|---|---|
| Tool | `cloudflared` (quick tunnel, no account) |
| Public URL | `https://fiction-strictly-yard-plan.trycloudflare.com` |
| Webhook path to register in YCloud | `https://fiction-strictly-yard-plan.trycloudflare.com/webhooks/ycloud` |
| Local target | `http://localhost:8005` (`cd backend && python -m uvicorn app.main:app --reload --port 8005`) |
| Started | 2026-08-04 |

**This URL changes every time the tunnel restarts.** When it does, re-register the
new `/webhooks/ycloud` URL in the YCloud dashboard (Developer → Webhooks) and
update this doc.

## Expiration

No fixed expiration — a `trycloudflare.com` quick tunnel lives exactly as long
as the local `cloudflared` process keeps running. It dies immediately if the
process is stopped or the machine sleeps/restarts; there's no separate 7-day
clock like webhook.site. No uptime SLA — Cloudflare positions these as
testing/dev only, not for anything production-facing. Free tier caps at 200
concurrent in-flight requests, far beyond what a dev/pilot number would hit.

## Restarting the tunnel

```bash
# Terminal 1 — backend
cd backend && conda activate agenda && python -m uvicorn app.main:app --reload --port 8005

# Terminal 2 — tunnel
cloudflared tunnel --url http://localhost:8005
```

Copy the new `https://<random-words>.trycloudflare.com` URL from the tunnel's
startup log, update it in the YCloud dashboard, and update this doc.

## Why not webhook.site? {#why-not-webhooksite}

Used briefly for the Day 0 spike (confirmed inbound + outbound-echo delivery).
Not suitable for ongoing development: URLs expire after 7 days regardless of
activity, it can't run our verify-token/signature logic or persist to
`agenda_db`, and real conversation content would sit on a third-party server —
avoid once testing moves past a one-off delivery check.
