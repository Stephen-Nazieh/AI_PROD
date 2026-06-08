---
agent_id: payment_gateway_engineer
type: engineering_devops
model_target: qwen3-coder-32b-mlx
---

# Stripe Developer Skill

> **Briefing Header**
> 1. Specialty: Stripe payment integration for Next.js apps — checkout, subscriptions, webhooks, customer portal
> 2. Target output directory: Project-specific `app/api/` and `lib/stripe/` trees
> 3. Stylistic tone: Security-conscious, precise about live vs. test mode, PCI-aware
> 4. Prioritized asset paths: Project root → `lib/stripe/` → `app/api/webhooks/`
> 5. Pause-and-confirm parameters: Live API key usage, webhook secret values, pricing/product ID selection, refund or cancellation logic

Comprehensive skill for building payment integrations in Next.js applications with Stripe. Covers five domains: **Checkout & Payments**, **Products & Pricing**, **Subscriptions & Billing**, **Webhooks**, and **Customer Portal**.

## Default Stack

- **Framework**: Next.js (App Router)
- **Server SDK**: `stripe` (Node.js)
- **Client SDK**: `@stripe/stripe-js` + `@stripe/react-stripe-js`
- **Database**: Supabase (Postgres with RLS)
- **Deployment**: Vercel
- **Language**: TypeScript

## Key Principles

1. **Never expose `STRIPE_SECRET_KEY` to the client.** Use `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` for client-side only. The secret key lives server-side exclusively.
2. **Use Server Actions or Route Handlers** to create Checkout Sessions — never create them from the client.
3. **Always verify webhook signatures** using `stripe.webhooks.constructEvent()`. Never trust unverified webhook payloads.
4. **Store subscription status locally** in your Supabase database. Don't query the Stripe API on every request.
5. **Test mode first, always.** Use `pk_test_` and `sk_test_` keys. Test card: `4242 4242 4242 4242`, any future expiry, any CVC.
6. **Return 200 quickly** from webhook handlers. Do async processing after acknowledging receipt.
7. **Use Price IDs, not raw amounts** — create Products and Prices in the Stripe Dashboard or API, then reference them by ID.
8. **Handle `cancel_at_period_end`** — when a user cancels, Stripe keeps the subscription active until the period ends.
9. **Idempotency** — Stripe can send the same webhook event more than once. Use `event.id` to deduplicate if needed.

## Environment Variables

```env
# .env.local
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...   # Client-safe
STRIPE_SECRET_KEY=sk_test_...                     # Server-only
STRIPE_WEBHOOK_SECRET=whsec_...                   # For webhook signature verification
```

## Stripe Client Setup Pattern

### Server-side (singleton)

```ts
// lib/stripe.ts
import 'server-only'
import Stripe from 'stripe'

export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)
```

### Client-side (singleton via lazy load)

```ts
// lib/stripe-client.ts
import { loadStripe } from '@stripe/stripe-js'

let stripePromise: ReturnType<typeof loadStripe>

export function getStripe() {
  if (!stripePromise) {
    stripePromise = loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY!)
  }
  return stripePromise
}
```

## Test Cards

| Scenario                        | Card Number        |
|---------------------------------|--------------------|
| Payment succeeds                | `4242424242424242`  |
| Payment requires authentication | `4000002500003155`  |
| Payment is declined             | `4000000000009995`  |

Use any future expiry date and any 3-digit CVC.
