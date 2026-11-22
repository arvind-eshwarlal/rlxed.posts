# Real Stories: two-step carousel pipeline

Nothing here runs by itself. Every post needs two clicks from you.

## Daily use
1. **Actions** tab > **Step 1 - Create story carousel** > **Run workflow**. Leave the story id as `next` (or type an id from `content/stories.json`) and run it.
2. Open the finished run. The **Summary** shows the slides, the caption, the Threads text and the checks. Nothing is posted yet.
3. Happy? **Actions** > **Step 2 - Approve and publish** > **Run workflow** > type the story id exactly as shown in the preview > run. It posts to Instagram, then Threads and Facebook.
4. Not happy? Edit the story in `content/stories.json` and run Step 1 again. A new draft replaces the old one.

Tip: tick **dry_run** in Step 2 to rehearse. It checks everything, posts nothing and keeps the draft.

## Safety rules built in
- Typing the story id in Step 2 is your approval. A wrong id, a missing draft, or a story already published stops the run before anything is posted.
- A story that is already published cannot be drafted again.
- Step 1 refuses a draft whose slides are too wordy, whose text would be too small, that has no sources, or whose caption is too long for Threads.
- If Instagram works but Threads or Facebook fails, the story is still recorded as published (so it is never double-posted) and the run turns red. Fix the missing platform with the existing **Cross-post an existing post** workflow, using `content/generated/<post id>` as the folder.
- The old scheduled workflow is not used. These two workflows only start when you click.

## Fixing something you spotted in the preview
1. Open `content/stories.json` on GitHub, click the pencil (Edit) icon, find the story (search for its id with Ctrl+F).
2. Change only the words between the quote marks. Keep every quote mark and comma. `[brackets]` show in blue.
3. Click **Commit changes**, then run **Step 1** again with that story's id. The new draft replaces the old one. Do not run Step 2 on the old preview.
4. Wording that is the same on every post (the series label and the closing "send this" slide) lives in `content/story_settings.json`. Anything about the design itself (fonts, colours, layout) lives in `scripts/render_story.py`: ask Claude for an updated file.
5. If the preview shows a red error instead, it lists exactly what to change (too many words, a missing source, and so on).

If it is already posted: this pipeline cannot delete posts. Delete the post in the Instagram, Facebook and Threads apps. To repost a corrected version, give the story a new id (for example `takacs-1939-v2`) and run Step 1 again. The old id stays blocked on purpose so it can never be posted twice.

## The closing brand slide
The very last slide is your "follow us" slide. Its words come from `content/cta.json` (the file you already edit). In `content/story_settings.json`, set `brand_slide` to:
- `"light"`: your existing white slide, identical to what the old pipeline made (default);
- `"dark"`: the same words on the dark design, with a white logo;
- `"off"`: no brand slide (then you may use up to 9 story slides).

## Where things live
- `content/stories.json`: your stories (slides, caption, sources, hashtags, status `ready` or `hold`).
- `content/story_settings.json`: series label, the automatic last slide, limits.
- `state/story_state.json`: which stories are published (created on the first publish).
- `content/drafts/`: the one current draft (public, like the rest of this repo, until you approve it).
- `content/generated/`: approved and published posts.

## Writing a story
Slides are plain text. `[Square brackets]` show in blue. First slide = hook (max 14 words); other slides max 22 words; 3 to 8 story slides. Two closing slides are added automatically: the "send this" slide (words in `content/story_settings.json`) and the brand slide (see below). Sources are added to the caption automatically.

### Read-through check (do this before approving)
The preview lists the slides as one numbered story. Read it as a stranger who has seen only the slides before each one:
- Is every term or event explained before a later slide relies on it (for example, why there is a "bronze-medal match", or what the Paralympics are)?
- Does the story run in a sensible order, with a link between each slide and the next?
- Does every "also", "then", "again" or "but" have something before it to refer to?
- Does the closing slide pay off what the first slide promised?
