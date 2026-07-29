# Deploying the engine service to Render

The pinned host (DEVELOPMENT_PLAN §1.1). Everything below is one manual pass in
the Render + Vercel dashboards; the repo side is already done (`Dockerfile`,
`render.yaml`, `/health` probe, fail-closed auth).

## Steps

1. **Render → New → Blueprint**, point it at `Jotelab/jotelab-ai`, branch
   `main`. Render reads `render.yaml`, builds the Dockerfile, and generates
   `ENGINE_API_KEY`.
2. Wait for the health check to go green (`/health` needs no auth).
3. Copy from the Render dashboard into the **web app's** production env
   (Vercel → physics-jotelab → Settings → Environment Variables):
   - `ENGINE_BASE_URL` = the service URL, e.g. `https://jotelab-engine.onrender.com`
   - `ENGINE_API_KEY` = the generated value (Render → jotelab-engine → Environment)
4. Redeploy the web app so the env takes effect.

## How to test

```bash
# 1. service is up and serves every registered topic
curl -s https://jotelab-engine.onrender.com/health

# 2. a verified instance round-trips (replace $KEY)
curl -s -X POST https://jotelab-engine.onrender.com/generate \
  -H 'Content-Type: application/json' -H "X-Engine-Api-Key: $KEY" \
  -d '{"topic":"suvat","difficulty":"easy","given":["u","a","t"],"find":"v","seed":42}'
# -> final_answer.exact "9", unit m/s

# 3. the wrong key is refused
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  https://jotelab-engine.onrender.com/generate \
  -H 'X-Engine-Api-Key: wrong' -H 'Content-Type: application/json' -d '{}'
# -> 401

# 4. production web app reaches it end to end: visit /learn on the deployed
#    site — a Thai SUVAT problem renders (not the "ยังเชื่อมต่อเอนจินไม่ได้" box).
```

## Notes

- **Cold starts:** the starter plan sleeps; the risk register already flags
  this. Engine calls themselves are ms-fast once warm.
- **Key rotation:** the service re-reads `ENGINE_API_KEY` from the environment
  on every request — rotate in Render, then update Vercel; no restart needed.
