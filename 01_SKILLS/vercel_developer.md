---
agent_id: deployment_platform_engineer
type: engineering_devops
model_target: qwen3-coder-32b-mlx
---

# Vercel Developer Skill

Comprehensive skill for deploying and managing Next.js applications on Vercel. Covers five domains: **Deployment**, **Environment Variables**, **Domains & SSL**, **CLI**, and **Platform Features**.

## Default Stack

- **Framework**: Next.js (App Router)
- **Deployment target**: Vercel
- **CLI**: `vercel` (latest)
- **Language**: TypeScript

## Key Principles

1. **Zero-config for Next.js.** Vercel auto-detects Next.js and configures builds, serverless functions, and routing automatically.
2. **Git push = deploy.** Connect a GitHub/GitLab/Bitbucket repo. Every push to `main` triggers a production deployment. Every PR gets a preview deployment.
3. **Environment variables must be set before deployment.** Env vars are baked into the build. If you add one after deploying, you must redeploy.
4. **`NEXT_PUBLIC_` prefix exposes to the browser.** Without this prefix, env vars are server-only. Never prefix secret keys with `NEXT_PUBLIC_`.
5. **Three environments:** Development, Preview, Production. Each can have different env var values.
6. **Preview deployments are free and automatic.** Every push to a non-production branch creates a preview with a unique URL.
7. **Rollbacks are instant.** You can roll back to any previous deployment via Dashboard or CLI.
8. **Edge Functions run globally.** Serverless Functions run in a single region by default.

## Quick Start

```bash
# Install CLI
npm i -g vercel

# Login
vercel login

# Link your project
vercel link

# Pull env vars for local dev
vercel env pull .env.local

# Deploy preview
vercel deploy

# Deploy to production
vercel --prod
```

## Environment Variables for a SaaS Stack

When deploying a Next.js + Supabase + Stripe app, set these in Vercel:

| Variable                                | Prefix?  | Description                          |
|-----------------------------------------|----------|--------------------------------------|
| `NEXT_PUBLIC_SUPABASE_URL`              | Yes      | Supabase project URL (client-safe)   |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY`         | Yes      | Supabase anon key (client-safe)      |
| `SUPABASE_SERVICE_ROLE_KEY`             | No       | Supabase service role (server-only)  |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY`    | Yes      | Stripe publishable key (client-safe) |
| `STRIPE_SECRET_KEY`                     | No       | Stripe secret key (server-only)      |
| `STRIPE_WEBHOOK_SECRET`                 | No       | Stripe webhook signing secret        |
