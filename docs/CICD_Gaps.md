# CI/CD Gaps

Current state: CI runs type-check + unit + integration tests; CD builds and pushes three images to GHCR on every push to `main`. Neither workflow is wired to the other, and nothing actually deploys.

---

## Gap 1 — CD does not gate on CI

`cd.yml` triggers on `push: branches: [main]` independently of `ci.yml`. A broken commit pushed directly to `main` (or merged via a fast-forward) will publish images even if tests never ran.

**Fix:** Add `workflow_run` trigger in `cd.yml` with `workflows: ["CI"]` and `types: [completed]`, or consolidate into a single workflow with `needs: integration`.

---

## Gap 2 — No deployment step

CD stops at `docker push`. There is no step that SSHes into a server, updates a Kubernetes manifest, triggers a Render/Fly deploy hook, or calls any other remote. The `docker-compose.prod.yml` overlay exists but is never applied automatically.

**Fix:** Add a deploy job after `build-and-push` that connects to the target host and runs `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && up -d`.

---

## Gap 3 — No staging environment

There is one compose overlay (`docker-compose.prod.yml`) and it goes straight to production. No staging tier means every merge to `main` is a live deploy with no intermediate soak period.

**Fix:** Add a `staging` environment in GitHub Environments, deploy there first, and gate the production deploy on a manual approval or a passing smoke test against staging.

---

## Gap 4 — No post-deploy smoke test

After images are pushed (or eventually deployed), there is no automated check that the running service is healthy. A bad image that passes unit tests but fails at startup would go undetected until someone notices.

**Fix:** After the deploy step, run `curl -sf https://<host>/health` (or the functional test suite) against the deployed environment and fail the workflow if it returns non-200.

---

## Gap 5 — No rollback path

Images are tagged with both `:latest` and the commit SHA, but `docker-compose.prod.yml` pins to `:latest`. If a bad release reaches production there is no automated rollback — the SHA tags exist but require a manual `docker compose pull` with a pinned tag to use them.

**Fix:** The deploy step should reference the SHA tag, not `:latest`. On failure, add a rollback step that re-deploys the previous known-good SHA (store it as a GitHub Actions output from the prior successful run).

---

## Gap 6 — GitHub Secrets are unvalidated

`ci.yml` requires 10+ secrets to construct `.env`. If any are missing or empty the integration job fails with a confusing compose or `undefined` error, not a clear "secret X is missing" message.

**Fix:** Add an explicit validation step before `docker compose up`:
```yaml
- name: Validate secrets
  run: |
    : ${MINIO_ROOT_USER:?MINIO_ROOT_USER secret is not set}
    : ${JWT_SECRET_KEY:?JWT_SECRET_KEY secret is not set}
    # ... etc.
  env:
    MINIO_ROOT_USER: ${{ secrets.MINIO_ROOT_USER }}
    JWT_SECRET_KEY: ${{ secrets.JWT_SECRET_KEY }}
```

---

## Gap 7 — No branch protection enforced as code

There are no `CODEOWNERS` or branch-protection rules committed to the repo. Nothing prevents a direct push to `main` that skips CI entirely.

**Fix:** Add a `.github/CODEOWNERS` file and document (or automate via `gh api`) the required branch protection rules: require PR, require `ci / Integration Tests` status check, disallow force-push.
