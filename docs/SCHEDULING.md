# Scheduling

One invocation of the skill writes one article. To publish on a schedule, trigger it from something that runs on a timer.

## Claude routines (cloud)

Create a routine whose prompt is short, for example:

> Run the article-pipeline skill once for this repository. Follow the skill exactly and finish with its report.

Practical notes:
- Set the routine's model to your strongest model: the skill is the editor, and the scout, writer and checker choose their own cheaper models from their agent files.
- Cloud runs start in a **fresh sandbox**, so local cache files vanish between runs. Use `"storage": {"backend": "wordpress_pages"}`: caches, claims and the photo index then live in private WordPress pages (`tw-state-*`) and are shared by every run, including parallel ones.
- Provide `TW_WP_USER` and `TW_WP_APP_PASSWORD` through the routine's environment or secrets mechanism, not in the prompt. To let scheduled runs go live, set `TW_ALLOW_PUBLISH=1` there too (and `"status": "publish"` in the config). Leave it out and every post stays a draft.
- Check the routine system's minimum interval. To run more often than that, create two routines offset by half the interval; the claim registry and the pre-publish check stop them duplicating a story.
- Add the plugin's repo as part of the routine's environment so `skills/article-pipeline/scripts/tw.py` and the niche pack are present.

## cron or CI (your own machine)

```
*/30 * * * *  cd /path/to/project && claude -p "Run the article-pipeline skill once." >> pipeline.log 2>&1
```

Local storage works here because the machine keeps its files. Use `wordpress_pages` instead if more than one machine runs the pipeline.

## Cadence

More runs are not automatically better: every article competes with your own earlier articles for the same queries. Start at one article every few hours in draft mode, read the output, and speed up only if quality and traffic hold.
