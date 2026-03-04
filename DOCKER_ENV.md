# Docker Environment Setup

## Initial Setup

1. Copy the example environment file:
   ```bash
   cp .env.docker.example .env.docker
   ```

2. Generate a secure SECRET_KEY:
   ```bash
   openssl rand -base64 32
   ```

3. Edit `.env.docker` and update:
   - `SECRET_KEY` - Use the generated value from step 2
   - `API_INTERNAL_URL` - Update IP if Docker network changes
   - Other values as needed for your environment

4. Start the containers:
   ```bash
   docker compose up -d
   ```

## Important Files

- `.env.docker.example` - Template (committed to git)
- `.env.docker` - Your actual config (NOT committed, gitignored)

## Security Notes

- **Never commit `.env.docker`** - It contains secrets
- Always use `.env.docker.example` as the template
- Generate a unique SECRET_KEY for each environment
- Update `API_INTERNAL_URL` if Docker assigns a different IP

## Finding Docker Internal IP

If you need to update the backend IP:

```bash
docker compose exec web ping -c 1 macfax_api | grep PING
```

Or:
```bash
docker network inspect macfax_web | grep -A 3 macfax_api
```
