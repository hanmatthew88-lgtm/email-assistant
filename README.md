# Email AI Assistant — Email Ingestion Service

Receives Microsoft Graph webhook push notifications when emails arrive in the
assistant mailbox, then schedules/reschedules meetings and sends calendar invites.

## Flow

```
Email arrives in assistant@company.com inbox
        ↓
Microsoft Graph fires POST /webhook
        ↓
app/main.py validates clientState, fetches full message
        ↓
app/email_parser.py → clean dict
        ↓
detect_intent() → "schedule" | "reschedule" | "unknown"
        ↓
app/scheduler.py → findMeetingTimes → createEvent → reply
```

## Azure App Registration (one-time setup)

1. Go to portal.azure.com → Azure Active Directory → App registrations → New
2. Add **Application permissions** (not delegated):
   - `Mail.Read`
   - `Mail.Send`
   - `Calendars.ReadWrite`
   - `MailboxSettings.Read`
3. Grant admin consent
4. Create a client secret and copy it

## Running locally (dev)

```bash
cp .env.example .env
# fill in your values

pip install -r requirements.txt

# Expose localhost to the internet for Graph webhooks (use ngrok or similar)
ngrok http 8000
# copy the https URL into WEBHOOK_PUBLIC_URL in .env

uvicorn app.main:app --reload

# Register the webhook subscription (one-time, renew every 3 days)
curl -X POST http://localhost:8000/subscriptions/create
```

## Deployment

Any server with a public HTTPS URL works. Recommended: Railway, Render, or a VPS.

Set all env vars from `.env.example` in your hosting dashboard.
The `/subscriptions/renew/{id}` endpoint should be called daily via cron.

## Next steps

- Replace `detect_intent()` keyword matching with a Claude API call for accurate
  intent + slot extraction (date/time/duration from natural language)
- Add a database to track subscription IDs and booked events
- Add per-company seat management and opt-in controls
