# rlxed Instagram Carousel Automation

Posts an automated carousel to @rlxedapp twice daily (7am & 7pm IST),
rotating through three content themes: Sports Science, Teammate Tag,
and Confessional.

## One-time setup

### 1. Add the real fonts
Download these from Google Fonts (free):
- [Quicksand](https://fonts.google.com/specimen/Quicksand) → grab the **Bold** weight
- [Ubuntu](https://fonts.google.com/specimen/Ubuntu) → grab **Regular** and **Bold**

Place the `.ttf` files in the `fonts/` folder with these exact names:
```
fonts/Quicksand-Bold.ttf
fonts/Ubuntu-Regular.ttf
fonts/Ubuntu-Bold.ttf
```
(If these aren't present, the generator falls back to a basic system font —
it'll still run, just won't look on-brand.)

### 2. Add the logo
Make sure `assets/rlxed-logo.png` is the transparent rlxed logo (already included).

### 3. Add GitHub Secrets
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**, and add:

| Secret name | Value |
|---|---|
| `IG_USER_ID` | `38924023033908560` |
| `IG_ACCESS_TOKEN` | your 60-day Instagram access token |

### 4. Enable workflow write permissions
Go to **Settings → Actions → General → Workflow permissions** and select
**"Read and write permissions"** — this lets the automation commit generated
images back to the repo.

### 5. Push this whole folder to your repo
```
git add .
git commit -m "Set up carousel automation"
git push
```

That's it — the workflow will now run automatically at 7am and 7pm IST.

## Testing before you trust the schedule

Run a manual test from the **Actions** tab on GitHub → select
"Post rlxed Instagram Carousel" → **Run workflow**. This runs the exact
same thing the schedule will run, immediately, so you can confirm it
works without waiting for 7am.

You can also test slide generation locally (won't post anything):
```
pip install pillow
python scripts/generate_carousel.py
```
This creates a new folder under `content/generated/` you can open and look at.

## Adding more content later

Open `content/queue.json` and add new items to any of the three theme
arrays, following the same `hook` / `mid` / `why` / `closure` / `caption`
/ `hashtags` structure as the existing ones. The rotation automatically
picks up new items — no code changes needed.

## Token expiry — IMPORTANT

Your access token lasts ~60 days. Mark a reminder for ~day 50 to refresh it:

```
curl "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=YOUR_CURRENT_TOKEN"
```

This returns a new token — update the `IG_ACCESS_TOKEN` GitHub secret with
the new value. If the token expires before you refresh it, the scheduled
posts will silently fail until you generate a fresh one from the Meta
dashboard and update the secret.

## How the rotation works

`state/state.json` tracks which theme comes next (science → tag →
confessional → repeat) and which item within each theme's list is next.
Every run advances both pointers and commits the updated state back to
the repo, so the next scheduled run picks up exactly where the last one
left off — even across different GitHub Actions runners.
