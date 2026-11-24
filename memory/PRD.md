# Decision Trust — PRD

## Original problem statement
Help me build app from my git repo decision-trust (private repo KaranNMakim/decision-trust). Keep existing features as-is, add sign-in (Google + email/password) and Stripe pay-per-use credits.

## Status (June 2026)
- BLOCKED: repo is private; no GitHub access in this workspace. User chose to connect GitHub to Emergent and start a new task from the repo.
- Nothing implemented yet.

## Approved plan (Phase 1)
- Import repo, fix only what blocks running
- Emergent-managed auth (Google + email/password), per-user data isolation
- Credits: 3 free on signup; packs 10/$10, 50/$45, 200/$160; 1 credit per main analysis action
- Stripe claimable sandbox (test mode), billing history page

## Backlog
- P1: Team accounts with shared credits, owner admin view, low-balance emails/receipts
- P2: Monthly plans, enterprise invoices, per-action credit pricing
