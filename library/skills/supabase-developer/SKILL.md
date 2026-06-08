---
name: Supabase Developer Skill
description: engineering_devops
metadata:
  paperclip:
    tags:
    - engineering_devops
    source_file: 01_SKILLS/supabase_developer.md
    format_detected: yaml_frontmatter
    original_agent_id: database_platform_engineer
    model_target: qwen3-coder-32b-mlx
---

# Supabase Developer Skill

Comprehensive skill for building Next.js applications with Supabase. Covers four domains: **Database**, **Auth**, **JavaScript Client**, and **Next.js Integration**.

## Default Stack

- **Framework**: Next.js (App Router)
- **Client library**: `@supabase/supabase-js` v2
- **SSR package**: `@supabase/ssr`
- **Language**: TypeScript
- **ORM**: None (direct supabase-js queries)

## Key Principles

1. **Always enable RLS** on public-facing tables. No exceptions.
2. **Use `(select auth.uid())` in RLS policies** (wrapped in select for performance).
3. **Never expose the service_role key** to the client. Use the anon/publishable key.
4. **Use PKCE flow** for SSR authentication (default in `@supabase/ssr`).
5. **Create a new Supabase client per request** on the server. The browser client is a singleton.
6. **Use `supabase.auth.getClaims()`** in server code to validate JWTs. Never trust `getSession()` on the server.
7. **Add indexes** on columns used in RLS policies.
8. **Specify the `TO` role** in RLS policies (`to authenticated`, `to anon`).

## Routing

### Database
If the request involves tables, schemas, views, columns, data types, indexes, joins, foreign keys, JSON/JSONB, or any SQL DDL/DML:
→ Use Database references

### Auth
If the request involves sign up, sign in, sign out, password reset, OAuth, magic link, OTP, MFA, sessions, JWTs, RLS policies tied to `auth.uid()`, or user management:
→ Use Auth references

### JavaScript Client
If the request involves `supabase.from()`, `.select()`, `.insert()`, `.update()`, `.delete()`, `.rpc()`, filters, modifiers, or any `supabase.auth.*` method calls:
→ Use JS Client references

### Next.js Integration
If the request involves `@supabase/ssr`, `createBrowserClient`, `createServerClient`, middleware/proxy auth, cookie-based sessions, or wiring Supabase into a Next.js app:
→ Use Next.js Integration references
