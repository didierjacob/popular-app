# 🚀 Deployment Guide - Popular App

## Prerequisites
- [x] MongoDB Atlas configured
- [x] Brevo SMTP configured
- [x] Deployment files created

---

## Step 1: Deploy Backend on Render

### Option A: Automatic deployment (recommended)

1. Go to **https://render.com** and sign in (GitHub recommended)

2. Click **"New" → "Web Service"**

3. Connect your GitHub repo or use **"Public Git repository"**

4. Configuration:
   - **Name**: `popular-api`
   - **Region**: Frankfurt (EU)
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`

5. Click **"Advanced"** and add the **Environment Variables**:

```
MONGO_URL = <YOUR_MONGODB_CONNECTION_STRING>
DB_NAME = popular_production
SMTP_HOST = smtp-relay.brevo.com
SMTP_PORT = 587
SMTP_USER = <YOUR_BREVO_LOGIN>
SMTP_PASSWORD = <YOUR_BREVO_API_KEY>
SMTP_FROM_EMAIL = <YOUR_FROM_EMAIL>
SMTP_FROM_NAME = Popular App
REPORT_EMAIL = <YOUR_EMAIL>
```

⚠️ **IMPORTANT**: Never commit real credentials to Git. Use environment variables on your hosting platform.

6. Click **"Create Web Service"**

7. Wait for deployment (~5 minutes)

8. Your API will be available at: `https://popular-api.onrender.com`

---

## Step 2: Configure Mobile App

Once backend is deployed, update the frontend:

### File: `/app/frontend/.env`
```
EXPO_PUBLIC_API_URL=https://popular-api.onrender.com
```

---

## Step 3: Test Deployment

1. **Test API**:
```bash
curl https://popular-api.onrender.com/api/
```

2. **Test Stats**:
```bash
curl https://popular-api.onrender.com/api/admin/stats
```

---

## Step 4: Build Mobile App

### For Android (APK):
```bash
cd frontend
eas build --platform android --profile preview
```

### For iOS (IPA):
```bash
cd frontend  
eas build --platform ios --profile preview
```

---

## Environment Variables Reference

| Variable | Description |
|----------|-------------|
| MONGO_URL | MongoDB Atlas connection string |
| DB_NAME | Database name (popular_production) |
| SMTP_HOST | Brevo SMTP server |
| SMTP_PORT | SMTP port (587) |
| SMTP_USER | Brevo login email |
| SMTP_PASSWORD | Brevo API key |
| SMTP_FROM_EMAIL | Sender email address |
| REPORT_EMAIL | Email for daily reports |

---

## Estimated Costs

| Service | Plan | Cost |
|---------|------|------|
| Render | Free | $0 |
| MongoDB Atlas | M0 Free | $0 |
| Brevo | Free (300 emails/day) | $0 |
| **Total** | | **$0/month** |

⚠️ Note: Render free plan sleeps after 15 min of inactivity. First request may take ~30s.
