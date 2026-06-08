---
agent_id: nextjs_stack_architect
type: engineering_devops
model_target: qwen3-coder-32b-mlx
---

# Next.js Developer Skill (v16.2.1)

> **Briefing Header**
> 1. Specialty: Next.js 16.2.1 frontend and server-side application development for the SaaS stack
> 2. Target output directory: Project-specific `app/`, `components/`, and `lib/` trees (outside the media-render pipeline)
> 3. Stylistic tone: Precise, version-pinned, code-first; explicit about App Router vs. Pages Router decisions
> 4. Prioritized asset paths: Project root → `lib/` → `components/` → `public/`
> 5. Pause-and-confirm parameters: Framework-version assumptions, deployment-target choice (Vercel vs. self-host), database/auth provider selection

Expert Next.js developer skill for frontend and server-side logic. Handles writing, scaffolding, debugging, and explaining Next.js code. Default to **Next.js 16.2.1** unless the user's project indicates otherwise.

## Step 1: Detect Project Context

Before writing anything:
1. **Router**: App Router (`app/`) or Pages Router (`pages/`)? Check file structure. If unclear, ask.
2. **Version**: Check `package.json` or `next.config.*`. Behavior differs significantly between v14, v15, v16.
3. **Cache Components enabled?**: Check `next.config.ts` for `cacheComponents: true`.
4. **TypeScript**: Default to `.tsx`/`.ts` unless user shows `.jsx`/`.js`.

## Step 2: Core Directives (v16)

### `'use client'`
Marks file as Client Component entry point. Required for hooks, event handlers, browser APIs.

### `'use server'`
Marks a function or file as a Server Action.

### `'use cache'` (v16 — requires `cacheComponents: true`)
Caches a route, component, or function. Replaces `fetch()` cache options model.

```ts
import { cacheLife, cacheTag, revalidateTag } from 'next/cache'

async function getProducts() {
  'use cache'
  cacheTag('products')
  cacheLife('hours')
  return fetch('/api/products').then(r => r.json())
}
```

## Step 3: File-System Conventions (App Router)

| File | Purpose |
|---|---|
| `layout.tsx` | Shared UI, persists across navigations |
| `page.tsx` | Route UI, makes route publicly accessible |
| `loading.tsx` | Suspense fallback for the route segment |
| `error.tsx` | Error boundary — must be `'use client'` |
| `not-found.tsx` | Rendered when `notFound()` is called |
| `route.ts` | API Route Handler |
| `proxy.ts` | Runs before requests — replaces deprecated `middleware.ts` (v16) |
| `template.tsx` | Like layout but re-mounts on every navigation |
| `default.tsx` | Fallback for unmatched parallel route slots |

### `params` and `searchParams` are Promises (v15+)

Always `await` them in Server Components.

## Step 4: Proxy (formerly Middleware)

> **⚠️ Breaking change in v16**: `middleware.ts` is **deprecated**. Rename file to `proxy.ts`.

```ts
import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

export function proxy(request: NextRequest) {
  const token = request.cookies.get('token')
  if (!token) {
    return NextResponse.redirect(new URL('/login', request.url))
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/dashboard/:path*'],
}
```

## Step 5: Route Handlers

```ts
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  return NextResponse.json({ id: 'example' })
}

export async function POST(request: NextRequest) {
  const body = await request.json()
  return NextResponse.json({ received: body }, { status: 201 })
}
```

## Step 6: Frontend Essentials

```tsx
// Always use next/image — never <img>
import Image from 'next/image'
<Image src="/hero.png" alt="Hero" width={1200} height={600} priority />

// Always use next/link for internal links
import Link from 'next/link'
<Link href="/about">About</Link>

// next/font — zero layout shift
import { Inter } from 'next/font/google'
const inter = Inter({ subsets: ['latin'] })

// Metadata
export const metadata: Metadata = { title: 'My App', description: '...' }
```

**CSS:** CSS Modules > Tailwind > Global CSS

## Step 7: Caching

### v16 model (Cache Components enabled)
Use `'use cache'` directives. `fetch()` cache options are ignored.

### v14/v15 legacy model
```tsx
await fetch('...', { next: { revalidate: 60 } })   // ISR
await fetch('...', { cache: 'no-store' })            // always dynamic
await fetch('...', { cache: 'force-cache' })         // always static
```

## Step 8: Scaffolding Protocol

1. **File tree first**
2. **Complete code for each file**
3. **Required installs**

```
my-app/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── globals.css
│   ├── error.tsx
│   ├── not-found.tsx
│   └── [feature]/
│       ├── layout.tsx
│       ├── page.tsx
│       ├── loading.tsx
│       └── error.tsx
├── components/ui/
├── lib/
│   ├── db.ts
│   └── utils.ts
├── actions/
├── proxy.ts
├── next.config.ts
└── tailwind.config.ts
```

## Step 9: Debugging Checklist

- `params`/`searchParams` not awaited (Promises since v15)
- `middleware.ts` not renamed to `proxy.ts` (v16 breaking change)
- `'use client'` missing on component using hooks or events
- `'use server'` missing on a Server Action
- `cookies()`/`headers()` called inside `'use cache'`
- `localStorage`/`window` used in a Server Component
- Non-serializable props passed Client→Server boundary
