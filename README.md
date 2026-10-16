# White-label spa platform (Django starter)

A multi-tenant Django project for the white-label spa and salon platform. A platform admin creates
businesses ("tenants") that each get their own branded booking site, web address, owner login and
data, all running on one codebase and one database.

## What's included

| Area | What it does |
| --- | --- |
| **Platform console** (`/admin/` on the platform domain) | Create and manage businesses, plans, domains and staff memberships. Adding a business provisions it in one step. |
| **Tenant provisioning** | A new business automatically gets a free subdomain (`<slug>.<platform domain>`), an owner login with a temporary password, a first branch and a starter service menu for its type (spa, barbershop, nail bar, hair salon, wellness). |
| **Host-based tenant routing** | `TenantMiddleware` picks the business from the host name: its subdomain or its own custom domain. Unknown hosts get a 404; suspended or cancelled businesses go offline. |
| **Data isolation** | Every per-business table inherits `TenantScopedModel`. Its default manager filters to the current business automatically, and saving a row for another business is refused. |
| **Plans and limits** | Starter, Growth and Business plans (seeded by a migration). Branch and staff limits are enforced. Custom domains need Growth and up, and full white-label (no "Powered by") needs Business. |
| **Branded booking site** | The business's own colours, lettering, tagline and services. Customers book a slot within opening hours and an M-Pesa deposit request is raised (stubbed). |
| **Business dashboard** | `/dashboard/` on the business's address: today's appointments, check-in and status actions, plan usage and branding settings, including a custom domain. Access is by membership role. |
| **Tests** | 35 tests covering provisioning, routing, isolation, plan limits, booking and dashboard permissions. |

## Quick start (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Settings come from environment variables (see .env.example); defaults work for local use.
python manage.py migrate        # also creates the three plans
python manage.py seed_demo      # platform admin + 3 demo businesses with bookings
python manage.py runserver
```

Then open:

| Address | What you see | Login |
| --- | --- | --- |
| http://localhost:8000/admin/ | Platform console | `admin` / `demo-pass-2026` |
| http://amani.localhost:8000/ | Amani Day Spa booking site (Business plan, no "Powered by") | — |
| http://amani.localhost:8000/dashboard/ | Amani's business dashboard | `owner@amani.test` / `demo-pass-2026` |
| http://fade.localhost:8000/ | Fade Factory Barbers (Growth) | `owner@fade.test` |
| http://lulu.localhost:8000/ | Lulu Nail Studio (Starter, on trial) | `owner@lulu.test` |

Chrome, Edge and Firefox send `*.localhost` to your own machine with no setup. Safari doesn't: add
`127.0.0.1 amani.localhost fade.localhost lulu.localhost` to `/etc/hosts`. Sign in with the email
address as the username.

The demo also gives Amani a custom domain, `book.amanispa.test`. To try it, add it to `/etc/hosts`
too.

## Creating a business

**In the platform console:** Businesses (tenants) → Tenants → **Add tenant**. Fill in the business,
its plan and branding, and the owner's email. On save, a message shows the booking-site link and
the owner's temporary password. Share the password securely; it isn't shown again.

**From the command line:**

```bash
python manage.py create_tenant "Tulia Retreat Spa" tulia owner@tulia.co.ke \
    --plan growth --type spa --city Naivasha --owner-name "Achieng Otieno" --owner-phone 0712345678
```

**From code** (for example a future self-signup page):

```python
from apps.tenants.services import provision_tenant
result = provision_tenant(name="Tulia Retreat Spa", slug="tulia", owner_email="owner@tulia.co.ke", plan_code="growth")
result.tenant, result.owner, result.temporary_password
```

## How the multi-tenancy works

```
request ─► TenantMiddleware ─┬─ platform host (localhost, www.)  ─► config/urls.py        (landing + admin)
                             ├─ <slug>.localhost / custom domain  ─► config/tenant_urls.py (site + dashboard)
                             │      sets request.tenant and the current-tenant ContextVar
                             └─ unknown host                       ─► 404
```

- `apps/tenants/context.py` holds the current business in a `ContextVar`, which is safe under ASGI
  and async code. Background jobs and scripts wrap their work in `with tenant_context(tenant): ...`.
- `TenantScopedModel.objects` filters by that business, and `.all_objects` deliberately sees every
  business. The platform console runs with no business set, so it sees everything and has a
  "by tenant" filter.
- A person has one login (`accounts.User`). What they can do inside a business comes from
  `TenantMembership` (owner, manager, receptionist, therapist or finance). Sessions are scoped to
  each host, so signing in on one business's site never signs you in on another's.
- Each business is paid into its own M-Pesa paybill or till, and invoices under its own KRA PIN. The
  platform never holds customer money.

## Project layout

```
config/            settings, platform URLs, tenant URLs
apps/accounts/     custom User (email, phone)
apps/tenants/      Plan, Tenant, Domain, TenantMembership, TenantScopedModel,
                   middleware, provisioning service, platform admin, commands
apps/spa/          Branch, Service, StaffMember, Customer, Booking,
                   booking site, business dashboard, M-Pesa stub
templates/         platform/, site/ (branded booking site), dashboard/, registration/
static/app.css     shared styles; --brand comes from each tenant
```

## Production notes

1. Set `DJANGO_DEBUG=false`, a strong `DJANGO_SECRET_KEY`, `PLATFORM_DOMAIN=yourplatform.co.ke`,
   `DATABASE_URL=postgres://...` and `DJANGO_CSRF_TRUSTED_ORIGINS=https://*.yourplatform.co.ke`.
2. DNS: a wildcard record `*.yourplatform.co.ke` pointing at your server or load balancer. Get a
   wildcard TLS certificate through a Let's Encrypt DNS challenge.
3. Custom domains: the business points a CNAME at your platform. Issue certificates on demand, for
   example with Caddy's on-demand TLS, checking each domain against the `Domain` table first.
4. Run `python manage.py collectstatic` and serve with `gunicorn config.wsgi` behind Nginx or Caddy.

## Next steps

These are not built yet. They follow the proposal's roadmap.

- **M-Pesa Daraja:** replace `apps/spa/payments.py` with a real STK push and a callback view that
  confirms bookings. Store each business's Daraja credentials in a secrets store keyed by tenant ID,
  never in the `Tenant` table.
- **KRA eTIMS:** an invoicing service that issues an eTIMS invoice per sale under each business's PIN.
- **PostgreSQL row-level security:** add RLS policies on `tenant_id` as a second line of defence
  behind the ORM filter.
- **Subscription billing:** charge plans monthly by M-Pesa, and move unpaid businesses to "Payment
  overdue" and then "Suspended".
- **Custom-domain verification:** a DNS check that sets `Domain.verified_at` before a custom domain
  becomes primary.
- **Reseller console:** a partner role that sees and bills only its own businesses.
- **Staff rosters, POS, inventory, loyalty and reports**, as specified in the proposal.

## Running the tests

```bash
python manage.py test
```
