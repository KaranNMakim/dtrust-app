# Decision Trust — Bring the Existing App Live, With Sign-In and Pay-Per-Use

Decision Trust helps enterprises trust their data by catching when two dashboards tell different stories about the same thing, or the same story in conflicting ways.
This project takes the existing private repo (KaranNMakim/decision-trust), gets it running as-is, and adds sign-in plus pay-per-use billing on top.

## Who it's for
- Data, analytics and BI teams in enterprises who need to know which numbers to believe.
- Business leaders who make decisions from dashboards and want proof those dashboards agree.
- The app owner, who wants to charge customers per use.

## Core features and experience
- **Existing Decision Trust features, unchanged**: whatever the repo does today (comparing dashboards, flagging conflicts, trust scores, reports) is kept with its current look and behaviour. Anything broken is fixed so it runs, but it is not redesigned.
- **Sign-in**: people must create an account and sign in before they can reach the app. They can sign in with Google or with email and password. Each person sees only their own work and results.
- **Pay-per-use credits**:
  - Customers buy credit packs through a secure card checkout.
  - Each paid action (for example, running one dashboard comparison or trust check) uses credits.
  - A visible credit balance is always on screen. When credits run out, the paid action is blocked and the customer is offered a top-up.
  - New accounts get a small number of free credits so they can try the product first.
  - A billing page lists past purchases and credit usage.
- **Starting prices (editable later)**:
  - 10 credits — $10
  - 50 credits — $45
  - 200 credits — $160
  - 1 credit = 1 paid action

## User flow
1. A visitor lands on the sign-in page and signs up with Google or email.
2. They land in the existing Decision Trust app with free starter credits shown in the header.
3. They use the app as they would today. Each paid action shows its credit cost and deducts it once it finishes successfully.
4. When credits run low or run out, they choose a pack, pay by card on Stripe's checkout page, and return to the app with the new balance.
5. They can check their purchases and usage history on the billing page at any time.

## UI/UX feel
- The existing app's design stays as it is.
- The new screens (sign-in, credit balance, buy credits, billing history) are styled to match it, so they feel like part of the same product rather than add-ons.

## Implementation phases
**Phase 1 — MVP (built now)**
- Pull in the private repo once GitHub is connected, and get it running in this environment.
- Fix only what stops it running.
- Add Google and email sign-in, and keep each user's data private to them.
- Add credit packs with Stripe checkout, the credit balance, deducting credits per paid action, free starter credits and the billing history page.
- Payments run in test mode first. Going live happens when the owner claims the Stripe account, and no API keys are needed.

**Phase 2**
- Team or company accounts that share one credit pool.
- Admin view for the owner: customers, revenue and usage.
- Low-balance email alerts and receipts.

**Phase 3**
- Optional monthly plans alongside pay-per-use.
- Usage-based invoices for large enterprise customers.
- Different credit costs per action, depending on how heavy each check is.

## Assumptions
- The repo is private, so GitHub must be connected to Emergent (or the code shared) before building starts. Its contents haven't been reviewed yet. "As-is" means keeping whatever features and design it has.
- Sign-in uses Emergent-managed login with both Google and email/password. Other sign-in methods would need manual setup.
- "Pay per use" means buying prepaid credit packs that are used up per action, not billing a card after each action.
- The paid action is the app's main analysis action (such as running a dashboard comparison or trust check). Viewing past results is free.
- Each new account gets 3 free credits.
- Prices are in US dollars, using the packs listed above.
- Payments go through Stripe in test mode at first, using a claimable Stripe account, so no keys are needed now. Stripe handles sales tax automatically where it is eligible.
- Accounts are individual, one person each. Team accounts come in Phase 2.
- There is no admin dashboard in Phase 1.
