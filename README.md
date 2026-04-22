# Find Help Near You

A mobile-first web app for finding local support services (food, clothing, job help, English classes, etc.) by zip code.

## Setup

### 1. Get a Google Maps API Key

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → enable **Maps Platform**
3. Enable these three APIs: **Geocoding**, **Places**, **Maps JavaScript**
4. Create an API key under Credentials

### 2. Configure your key

```bash
cp .env.example .env.local
# then open .env.local and paste your key
```

### 3. Deploy to Vercel (free)

```bash
npm install -g vercel
vercel
# Follow the prompts — it will ask you to log in and link a project
```

Then in the Vercel dashboard, add `GOOGLE_MAPS_API_KEY` as an Environment Variable.

## Local development

```bash
npm install -g vercel
vercel dev
# App runs at http://localhost:3000
```

## Project structure

```
index.html        # Single-page app (two screens: search & results)
style.css         # Mobile-first styles
app.js            # Frontend logic
api/
  search.js       # Serverless function: geocodes zip + searches Places API
vercel.json       # Routing config
.env.example      # Template for API keys
```

## Customizing service categories

Edit the category buttons in `index.html`. Each button has two data attributes:

- `data-category` — the search query sent to Google Places
- `data-label` — the display name shown to users
