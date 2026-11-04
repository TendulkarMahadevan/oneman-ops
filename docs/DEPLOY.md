# Deploying OneManOps on Vultr

Target: one Vultr Cloud Compute VM running Docker Compose (Postgres, FastAPI, Next.js, Caddy). No GPU needed.
The LLM runs on Vultr Serverless Inference, so the VM only orchestrates.

> Status: these steps and files are written but **have not been run on a real Vultr account yet**.
> `docker compose config` validates and the stack was exercised locally (see README, "Verification status").
> Tick the checklist at the bottom as you go.

## 1. Create the resources (Vultr console)

1. **Cloud Compute** instance: Ubuntu 24.04 LTS, Regular Performance, 2 vCPU / 4 GB is plenty. Add your SSH key. Do not enable a GPU plan.
2. **Firewall group**: inbound allow TCP 22, 80, 443 only. Attach it to the instance. (`bootstrap_vm.sh` also enables `ufw` with the same rules.)
3. **DNS**: create an `A` record (e.g. `ops.<your-domain>`) pointing at the instance IPv4. Caddy needs it to resolve before it can issue the certificate.
4. **Serverless Inference**: in the Vultr console create an inference subscription and copy the API key.
   Pick a chat model that is available to you; list them with:

   ```bash
   curl -s -H "Authorization: Bearer $VULTR_INFERENCE_API_KEY" https://api.vultrinference.com/v1/models
   ```

   Prefer a model that follows JSON instructions reliably. Use its `id` as `VULTR_INFERENCE_MODEL`.

## 2. Prepare the VM

```bash
ssh root@<vm-ip>
git clone <your-public-repo-url> oneman-ops && cd oneman-ops
sudo bash deploy/bootstrap_vm.sh
```

## 3. Configure secrets (on the VM only)

```bash
cp .env.example .env
chmod 600 .env
# edit .env:
#   POSTGRES_PASSWORD   -> output of: openssl rand -hex 24
#   VULTR_INFERENCE_API_KEY, VULTR_INFERENCE_MODEL
#   SITE_ADDRESS        -> ops.<your-domain>
```

`.env` is gitignored. The backend refuses to start if the scoring weights do not sum to 1, if a key is set without a model, etc.

## 4. Start and seed

```bash
docker compose up -d --build
docker compose exec backend python -m app.seed      # idempotent demo data
docker compose ps                                   # all services Up / healthy
curl -s https://ops.<your-domain>/health            # {"status":"ok","database":"ok","llm":"ok",...}
```

`/health` is `degraded` if the database or Vultr inference is unreachable. Restart policies are `unless-stopped`, so the stack comes back after a reboot.

## 5. Smoke test the public URL

From any machine with Python and `httpx` (`pip install httpx`):

```bash
python scripts/smoke_test.py https://ops.<your-domain>
```

It creates a request, simulates quotes, compares, approves, uploads the four files in `samples/`, checks each outcome, tests duplicate detection, makes a human exception decision and checks the audit log. It exits non-zero on any failed check and reports the elapsed time (target: under 3 minutes).

## 6. Operations notes

- Logs: `docker compose logs -f backend`.
- Update: `git pull && docker compose up -d --build`.
- Backup the database: `docker compose exec db pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql`.
- Uploaded invoices live in the `uploads` volume; Postgres in `pgdata`; TLS certificates in `caddy_data`.
- The API has no authentication (see README limitations). If the URL is public for judging, consider putting Caddy `basic_auth` in front after the submission window, or restricting by IP.

## Checklist

- [ ] VM created, firewall group attached (22/80/443)
- [ ] DNS A record resolves to the VM
- [ ] `.env` created on the VM, not in git
- [ ] `docker compose up -d --build` healthy, `/health` reports `ok`
- [ ] Seed ran; dashboard shows data
- [ ] `scripts/smoke_test.py` passes against the public URL
- [ ] Opened on a phone; full flow completes in under 3 minutes
