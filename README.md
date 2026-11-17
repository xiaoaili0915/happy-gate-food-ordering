# Happy Gate — online ordering website and backend

FastAPI app: customer menu, cart and checkout, order status page, legacy web kitchen page,
and the authenticated `/api/restaurant/*` API used by the owner's Android app
(separate repo: `happy-gate-orders-android`).

## Run locally

```sh
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set KITCHEN_TOKEN at least
python seed.py                  # loads data/menu_seed.json into orders.db
uvicorn app.main:app --reload --port 8080
python -m pytest tests          # 14 tests
```

## Deploy on Vercel + Neon

1. Vercel → New Project → import this GitHub repo. Vercel detects the FastAPI app in `app/main.py`
   automatically (framework preset "FastAPI"); no build command and no `vercel.json` needed.
2. Vercel project → Storage → add **Neon Postgres**. It injects `DATABASE_URL` automatically.
3. Project → Settings → Environment Variables, add:

   | Name | Value |
   | --- | --- |
   | `KITCHEN_TOKEN` | long random string; the Android app logs in with it |
   | `RESEND_API_KEY` | from resend.com (customer confirmation / rejection emails) |
   | `FROM_EMAIL` | verified sender on Resend |
   | `RESTAURANT_TIMEZONE` | `Europe/Amsterdam` |
   | `FIREBASE_CREDENTIALS` | service-account JSON, once push is set up (optional) |

4. Deploy, then load the menu once into the fresh database:

   ```sh
   curl -X POST -H "Authorization: Bearer $KITCHEN_TOKEN" https://<your-app>.vercel.app/api/restaurant/admin/seed-menu
   ```

5. Open `https://<your-app>.vercel.app/` to order, and connect the Android app with the same URL and token.

Notes: there is no background process on Vercel, so the 3-minute auto-reject runs whenever
orders are read (website status page, kitchen page, app polling). At ~20 orders a day this stays
well inside the free tiers of both Vercel and Neon.
