# Decision Trust — PRD

## Original problem statement
Build the app from the user's git repo decision-trust (KaranNMakim/decision-trust: FastAPI backend + Next.js frontend). Keep existing features and design as-is, and add sign-in (Google + email/password), private per-user data, and pay-per-use credits.
Later requests: a free Basic plan with basic features outside the paywall; a premium "contact" panel (subject + reason) emailed to karanmakim@outlook.com, changed to "Join premium waitlist".

## User choices
- Payments: Razorpay, INR (Stripe test account unavailable for India). Razorpay keys NOT added yet, so payments are disabled.
- Auth: Emergent-managed Clerk (Google + email/password).
- Email: Emergent-managed email (Resend), sent to karanmakim@outlook.com.

## Architecture
- Backend: /app/backend/server.py (FastAPI) mounts the repo's routes (app/main.py, /api/v1/*), which require sign-in via a router dependency (app/tenancy.py binds each user's own in-memory TrustEngine seeded from data/acme). billing.py handles credits, the ledger and Razorpay orders/verify/webhook. premium.py is the waitlist plus email. clerk_auth.py handles Clerk.
- Frontend: the Next.js pages were converted to CRA + react-router (src/pages/*). The original design (Tailwind tokens, dt-ui components) is kept. Shell = sidebar + top bar (waitlist, plan badge, credits, Buy, user menu).
- Mongo: users (credits), credit_ledger, payment_transactions, premium_waitlist.

## Implemented (2026-11-24)
- Repo ported and running. Sign-in pages. Each user's workspace is private.
- Basic (free) plan: Trust Index, metrics and scores, conflicts and migration plans, recommendations, Trust Graph, calibration, steward actions, BI file preview.
- Credits: 3 free at signup. Ask, Reconcile, Ingest CSV, Extract commit and Export each cost 1 credit. At 0 credits the request is refused (402) and the buy dialog opens. Packs: 10 for ₹850, 50 for ₹3,800, 200 for ₹13,500.
- Plan & billing page: balance, plan cards (Basic / Pay per use / Premium coming soon), packs, purchases, credit activity.
- Premium waitlist dialog with subject and reason. Each signup is saved and emailed to the owner (limit 3 per day per user).
- Tests: iteration_1 100%, iteration_2 passed; its reconcile prefill bug and waitlist duplicate issues are fixed.

## Paywall model (Option 1, 2026-11-24)
- Two workspaces per user, switched from the sidebar (X-Workspace header).
- **Acme demo**: sample company, everything free (Ask, Reconcile, Export too). It's read-only for new data (ingest and extract commit return 403) and resets on restart.
- **My workspace**: starts empty. Changes are saved as an event log (Mongo workspace_events) and replayed on load, so they survive restarts. Ask, Reconcile, Export, CSV ingest and extract commit cost 1 credit each. Browsing and steward actions are free.
- Sample files can be downloaded from /samples/* on the Ingest page.
- Tests: iteration_3 backend 28/28. Its Reconcile stale-dashboard bug and the robustness notes are fixed.

## Known limits
- Razorpay keys missing, so Buy is disabled. Owner was asked about UPI options (Razorpay supports UPI) and hasn't answered yet.
- Demo workspaces live in memory and reset on restart (fine). My workspace is replayed from its event log the first time it's opened after a restart. Engines are held in memory with no eviction.
- Claude explanations are off (no ANTHROPIC_API_KEY), so template answers are used.
- The original repo tests in backend/tests target the old single-tenant app; the new tests are in backend/tests_saas.

## Backlog
- P0: Add Razorpay keys to turn on payments (UPI, cards, netbanking).
- P1: Owner admin view (waitlist, customers, revenue); low-balance emails and receipts.
- P2: Team accounts with shared credits; monthly plans; per-action credit pricing; turn on Claude explanations.
