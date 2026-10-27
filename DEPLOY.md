# Deploying BuildTrack

- **API (backend):** Render web service, from `backend/` (settings in [`render.yaml`](render.yaml)).
- **Website (frontend):** Vercel, from `frontend/` (page routing in [`frontend/vercel.json`](frontend/vercel.json)).
- **Database:** MongoDB Atlas.

The website used to be Angular. It is now **React (Vite)**, so the existing Vercel project's build settings must change (step 3).

## 0. Point the deployments at this repo

The live Render and Vercel deployments were built from the **old repo**. Until they are connected to `RanishVishwakarma/BuildTrack-Enhanced`, they keep deploying the old code.

First check **whose accounts** they live in:

- **Your own Render/Vercel accounts:** switch the repo (option A). The URLs and environment variables stay.
- **The internship or company accounts:** you may lose access, and they are not yours to change. Create new ones in your own accounts (option B). It is free and takes about 15 minutes.

**Option A: switch the existing projects to the new repo**
- **Render:** service → **Settings → Build & Deploy → Repository → Edit** → choose `RanishVishwakarma/BuildTrack-Enhanced` and branch `main`. If the new repo is not listed, first grant Render access to it: **Account Settings → GitHub → Configure**.
- **Vercel:** project → **Settings → Git → Disconnect**, then **Connect Git Repository** → choose `RanishVishwakarma/BuildTrack-Enhanced`. If it is not listed, grant Vercel access via **Adjust GitHub App Permissions**.
- Then apply the new settings in steps 2 and 3. The old repo's settings (Angular, old paths) no longer fit.

**Option B: create new deployments in your own accounts**
- **Render:** **New → Blueprint** → pick this repo. [`render.yaml`](render.yaml) creates the API service, and you fill in the values marked as secrets (step 2 table).
- **Vercel:** **Add New → Project** → import this repo → set **Root Directory** to `frontend`. Vercel detects Vite. Add `VITE_API_BASE_URL` (step 3) and deploy.
- The URLs change: put the new Vercel URL in Render's `BACKEND_CORS_ORIGINS`, and the new Render URL in Vercel's `VITE_API_BASE_URL`.
- Once the new ones work, pause or delete the old deployments so nobody uses the outdated version.

## 1. Push the code

Render and Vercel deploy from GitHub, so commit and push `main` first. Both redeploy automatically after a push once they are set up.

## 2. Render: update the API service

Open the existing service → **Settings**:

| Setting | Value |
|---|---|
| Root Directory | `backend` |
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/v1/health` |

Then **Environment**. Values in `< >` are yours, and the secrets never go in the repo.

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.13.4` |
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` |
| `MONGODB_URL` | `<your Atlas connection string, with the new password>` |
| `MONGODB_DB_NAME` | `buildtrack` |
| `JWT_SECRET_KEY` | `<a long random value>`. Changing it signs everyone out |
| `BACKEND_CORS_ORIGINS` | `<your Vercel address>`, e.g. `https://buildtrack.vercel.app` (comma-separate several, no trailing slash) |
| `AI_ENABLED` | `false` (no paid AI) |
| `AI_PROVIDER` | `quick` (free answers; there is no Ollama on Render) |
| `APP_TIMEZONE` | `Asia/Kolkata` |
| `COMPANY_GSTIN` | `<your GSTIN>` (optional; enables the CGST/SGST/IGST split) |

Remove old variables that no longer exist, such as any Anthropic key you are not using. Then **Manual Deploy → Deploy latest commit**.

**Check:** open `https://<your-api>.onrender.com/api/v1/health`. It should answer `200`.

## 3. Vercel: switch the website from Angular to Vite

Open the existing project → **Settings → Build and Deployment**:

| Setting | Old (Angular) | New |
|---|---|---|
| Framework Preset | Angular | **Vite** |
| Root Directory | (as before) | **`frontend`** |
| Build Command | `ng build` | **`npm run build`** |
| Output Directory | `dist/<name>/browser` | **`dist`** |
| Install Command | — | `npm install` (default) |

**Settings → Environment Variables** (Production):

| Key | Value |
|---|---|
| `VITE_API_BASE_URL` | `https://<your-api>.onrender.com/api/v1` |

`VITE_API_BASE_URL` is baked into the site **when it is built**, so redeploy after changing it: **Deployments → ⋯ → Redeploy**. Remove old Angular variables if any.

**Check:** open the site, refresh a deep page such as `/projects` (it should not 404), and sign in.

## 4. MongoDB Atlas

- **Network Access** must allow Render. Render's free tier has no fixed IP address, so this needs `0.0.0.0/0`, which is safe only with a strong database password.
- Change the database password if it was ever shared, then update `MONGODB_URL` on Render.

## 5. Data updates after this release

These scripts are one-off and safe to re-run: each previews first and changes nothing without `--apply`. **Skip this section if production uses the same Atlas database you develop against.** These were already run there.

Run them from `backend/` with `MONGODB_URL` set to the production database:

```bash
.venv\Scripts\python.exe scripts\fix_attendance_dates.py        # then add --apply
.venv\Scripts\python.exe scripts\link_worker_logins.py          # then add --apply
.venv\Scripts\python.exe scripts\grant_client_access.py         # then add --apply
```

- **`fix_attendance_dates.py`:** moves attendance to the correct calendar day and removes duplicate marks.
- **`link_worker_logins.py`:** links existing worker accounts to their worker records.
- **`grant_client_access.py`:** keeps clients' current project access as explicit grants.

Demo data (optional; it adds sample projects to that database): `scripts\seed_demo.py`. Remove it with `--remove`.

## 6. After deploying

- **Approve staff:** in **Settings → Users**, project manager, site engineer and contractor sign-ups now wait as *Pending* until you click **Approve**.
- **Assign projects:** open each project as admin and choose its **Project manager**. That manager gets access; unassigned projects are visible only to admins.
- **Vendors:** check each vendor's **GST number** so purchase orders split tax correctly.

## Good to know

- **Render free tier sleeps** after about 15 minutes idle, so the first request takes 30–60 seconds. The background monitoring checks only run while it is awake.
- **Uploaded files** (invoice copies, evidence) are saved on Render's disk, which is wiped on every deploy. For lasting files, add a Render Disk (paid) or move uploads to cloud storage.
- **Agent mode needs Ollama**, which Render does not have. Online, the tab says Ollama is not running, while **Ask AI** works with free quick answers. Demo Agent mode from your own computer (`ollama serve`).
- **"Failed to fetch" or CORS errors** after deploying almost always mean `BACKEND_CORS_ORIGINS` does not exactly match the Vercel address (no trailing slash), or `VITE_API_BASE_URL` was changed without a redeploy.
