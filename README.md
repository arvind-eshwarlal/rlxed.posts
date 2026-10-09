# rlxed Instagram Carousel Automation

Posts a carousel to @rlxedapp twice daily (7am & 7pm IST), rotating through three
content themes (Sports Science, Teammate Tag, Confessional).

## How slides are made now
Each slide uses one of your hand-made designs in `templates/`. The placeholder text was
erased from every design; the system remembers where your text sat (position, angle,
alignment, colour) and places the real text in exactly that spot, shrinking the font if
needed (never below 34px; if a design can't fit a caption, another design is used).

A carousel takes 4 consecutive designs from one "run" in `templates/families.json`
(consecutive = consecutive 15-degree variations of one shape). Edit that file to reorder
runs, move designs between runs, or remove designs you don't want used.

The last slide's text lives in `content/cta.json` - edit it and re-upload that one file.

## Uploading to GitHub (browser uploads are capped at about 100 files per batch)
1. Batch 1: everything EXCEPT the `templates/clean` folder (scripts, fonts, content, state, assets, README, requirements.txt, templates/templates.json, templates/families.json).
2. Batch 2: the `templates/clean` folder (99 images) on its own.
3. One-time edit to `.github/workflows/post-carousel.yml` (open it on GitHub, click the pencil icon):
   change the line `run: pip install pillow requests` to `run: pip install -r requirements.txt`, then commit.

## Secrets & permissions (already done)
`IG_USER_ID`, `IG_ACCESS_TOKEN` as repository secrets; Settings > Actions > General > Workflow permissions = Read and write.

## Testing
Actions tab > "Post rlxed Instagram Carousel" > Run workflow.

## Token expiry - IMPORTANT
The Instagram token lasts ~60 days. Refresh around day 50:
  https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=YOUR_CURRENT_TOKEN
then update the IG_ACCESS_TOKEN secret with the new value.

## Adding more content / designs
- More captions: add items to `content/queue.json` (same structure as existing).
- More designs: `python scripts/build_templates.py <folder_of_pngs_with_placeholder_text> templates`
  (needs `pip install scipy opencv-python-headless numpy pillow`), then add the new ids to `templates/families.json`.
