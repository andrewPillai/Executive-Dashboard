# Automated Deployment Setup

This project is configured for automatic deployment using GitHub Actions.

## One-Time Setup (5 minutes)

### 1. Deploy Frontend to Vercel

1. Go to https://vercel.com/new
2. Import `andrewPillai/Executive-Dashboard` GitHub repository
3. Framework: **Vite**
4. Root Directory: `application/frontend`
5. Build Command: `npm run build`
6. Output Directory: `dist`
7. Click **Deploy**
8. After deployment completes:
   - Copy your **Project ID** (Settings → General)
   - Copy your **Org ID** (Settings → Team)

### 2. Deploy Backend to Railway

1. Go to https://railway.app
2. Create new project
3. Click **Deploy from GitHub Repo**
4. Select `andrewPillai/Executive-Dashboard`
5. After deployment:
   - Go to Settings → Tokens
   - Create new token and copy it

### 3. Get API Tokens

**For Vercel:**
- Go to https://vercel.com/account/tokens
- Create token named `VERCEL_TOKEN`

**For Railway:**
- Go to https://railway.app/account/tokens
- Create token named `RAILWAY_TOKEN`

### 4. Add GitHub Secrets

1. Go to your repo: https://github.com/andrewPillai/Executive-Dashboard
2. Settings → Secrets and variables → Actions
3. Add these secrets:
   - `VERCEL_TOKEN` (from Vercel account)
   - `VERCEL_ORG_ID` (from Vercel project settings)
   - `VERCEL_PROJECT_ID` (from Vercel project settings)
   - `RAILWAY_TOKEN` (from Railway account)

### 5. Test Deployment

Push a test commit to your branch:
```bash
git push
```

Watch the deployment:
- Go to Actions tab on GitHub
- You'll see `Deploy Frontend to Vercel` and `Deploy Backend to Railway` workflows running
- Once complete, you'll have live URLs

## Your Live Dashboard

- **Frontend:** `https://your-vercel-app.vercel.app`
- **Backend API:** `https://your-railway-app.up.railway.app/api`

## How It Works

Every time you push to `claude/gracious-bell-0wujfa`:
1. GitHub Actions automatically runs the workflows
2. Frontend builds with Vite and deploys to Vercel
3. Backend builds Docker image and deploys to Railway
4. Your live app updates within 2-3 minutes

## Cost

Both Vercel and Railway offer **free tiers**:
- Vercel: 100GB bandwidth/month free
- Railway: $5/month credit (enough for small projects)

No credit card needed for either!
