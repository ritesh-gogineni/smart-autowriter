# smart-autowriter

A Claude Code plugin that works as a **newsroom and blog autowriter**. You give it a broad topic area (a beat, such as "UK renters' rights and housing costs" or "Premier League football"). Each run, it finds what is happening in that area, picks the one story most worth publishing, researches it, writes it, fact-checks it and delivers it as a **Word document** or a **WordPress draft**.

It is a **multi-model pipeline**: the strongest model decides, cheaper models do the work.

| Stage | Model | Job |
|---|---|---|
| Orchestrator (the skill) | Opus (recommended) | Picks the topic and headline, reviews the draft, applies the fact-check, publishes |
| `scout` | Sonnet | Researches, scores a shortlist, builds fact dossiers |
| `writer` | Sonnet | Writes the article, builds inline HTML graphics, prepares the photo |
| `checker` | Haiku | Fact-checks every claim, skipping claims already verified |

Around that sit the parts that make it safe to run on a schedule:

- **Shared caches**: research dossiers and verified facts are reused across runs, with separate lifetimes for volatile and stable facts.
- **Duplicate guards**: a topic-claim registry plus a pre-publish recent-posts check, so parallel runs do not write the same story twice.
- **Licence-aware photos**: only Creative Commons, free-stock or generated images are used; a library-first search avoids re-downloading and re-uploading.
- **Safety enforced in code, not just in the prompt**: a helper script does all publishing. It strips scripts and unsafe HTML, publishes only files from the run folder, sends credentials only to your https site, and updates only posts the pipeline wrote. See [Security](#security).
- **Draft by default**: nothing goes live unless you set the status to `publish` *and* set `AUTOWRITER_ALLOW_PUBLISH=1` yourself.


## Install

```
/plugin marketplace add ritesh-gogineni/smart-autowriter
/plugin install smart-autowriter@smart-autowriter
```

Requires Python 3.8+ (standard library only) and a Claude Code session that can use the Agent tool.

## Quickstart (5 minutes, no WordPress needed)

1. Copy `config.example.json` to `smart-autowriter.config.json` in your project. Edit `topic`: the broad area you cover (`description`), who reads it, what to focus on and what to avoid. Then edit `site`. Leave `publisher.type` as `docx`: each article is saved as a Word document in `./articles/`.
2. The default `"niche": "general"` pack works for any topic area. For better results copy `niches/_template/niche.md` to `niches/<yourname>/niche.md`, fill it in with your own evidence, and set `"niche": "<yourname>"`. `examples/football/niche.md` is a fully worked example.
3. In Claude Code, on your strongest model, run `/smart-autowriter:article-pipeline` (plugin skills are namespaced), or ask in plain words: *"Run the article-pipeline skill once on home composting."* (this overrides the configured topic area for one run). Each run picks one story in the area and writes one article.
4. Open `./articles/<slug>.docx` and read the run report.

## Output options

Set `publisher.type` in the config:

| Type | Output | Needs |
|---|---|---|
| `docx` (default) | `articles/<slug>.docx`: title, standfirst, featured photo, body with headings, lists, tables and live links, photo credit. Plus `<slug>.json` with the SEO title, description, tags and sources | Nothing (no extra Python packages) |
| `files` | `articles/<slug>.html` plus the photo, for pasting into any CMS | Nothing |
| `wordpress` | A post created through the REST API, as a draft by default | An https site and an application password |

Inline graphics are built as HTML. In Word, tables come through as real tables. Bar charts and other CSS-only graphics come through as their labels and values.

## Publish to WordPress

1. Create a **dedicated WordPress user** for the pipeline and give it an Application Password (Users, Profile, Application Passwords). Do not use your own admin account.
   - **Author** role is the safest: it can only create and edit its own posts. It is enough with the default local storage.
   - **Editor** role is needed only for `"storage": {"backend": "wordpress_pages"}` (cloud runs), because caches are kept in private pages.
2. Export the credentials; they are never put in the config or the prompt:
   ```
   export AUTOWRITER_WP_USER='pipeline-bot'
   export AUTOWRITER_WP_APP_PASSWORD='xxxx xxxx xxxx xxxx xxxx xxxx'
   ```
3. In the config set `"publisher": {"type": "wordpress", "status": "draft", "wordpress": {"base_url": "https://your-site", "author_id": <the bot user's id>, ...}}`. `base_url` must be https. Create the tags in `always_tags` (for example `ai-assisted`) in WordPress first if the bot is an Author, since Authors cannot create tags. Map your SEO plugin's meta keys in `meta_map` (the keys must be registered for the REST API on your site, otherwise WordPress ignores them).
4. Keep `status` at `draft` until you have reviewed several runs. To go live, set `"status": "publish"` **and** export `AUTOWRITER_ALLOW_PUBLISH=1` in the environment that runs Claude Code. Without both, posts are saved as drafts.

## Scheduling

The plugin does one run per invocation; scheduling is yours. See [docs/SCHEDULING.md](docs/SCHEDULING.md) for Claude routines and cron, and for why cloud runs need `"storage": {"backend": "wordpress_pages"}` (each cloud run starts in a fresh sandbox, so local cache files would be lost).

## How a run works

`setup` → scout (research, cached) → you pick the topic and **claim** it → you write the headline set and the brief → writer → your review → checker (cached) → you apply the fact-check → duplicate check → `publish` → `finish` (caches written back) → report.

Details are in `skills/article-pipeline/SKILL.md`; the three agents are in `agents/`; house style, graphics and photo rules are in `skills/article-pipeline/references/`.

## Make it yours

The pipeline is generic and you set the topic; a **niche pack** holds everything specific to your subject: what formats win, which sources to trust, what counts as volatile, key dates, timing, banned words. `examples/football/niche.md` is a complete example; `niches/_template/niche.md` is the blank form. Fill the "What the data says" section with your own analytics: it is the single biggest lever on quality.

## Results

Honest status: the pipeline has run on one site. **Traffic results are still being measured** and will be published here with the method (GA4 plus Search Console, before and after, posts of equal age). Until then, treat the design as a reasonable architecture, not a proven growth recipe. Pull requests with your own results are welcome.

## Responsible use

- **Keep a human in the loop.** The default is `draft`. Search engines penalise scaled, low-value content; the fact-check stage reduces errors but does not replace an editor.
- **Disclose AI assistance** to your readers (the example config adds an `ai-assisted` tag).
- **Respect image licences.** The photo policy only allows Creative Commons, free-stock or generated images, and requires a visible credit. Do not loosen it.
- **Never put credentials in prompts, configs or commits.** `.gitignore` excludes the config file and run folders.

## Security

The agents read the open web, and any page can contain text written to manipulate an AI. The skill tells every stage to treat web content as data, but prompts are not a security boundary. So the publishing helper (`scripts/autowriter.py`) enforces these rules itself, whatever the model asks for:

- **Article HTML is rebuilt from an allowlist** (paragraphs, headings, lists, tables, links, inline styles). Scripts, iframes, images, event handlers, `javascript:` links and CSS that loads URLs are removed, and the removals are reported. This matters on WordPress, where Editors may post unfiltered HTML.
- **Only files inside the run folder can be published.** A manifest cannot point at `~/.ssh`, `.env` or anything else on the machine. The featured image must be a real JPEG or PNG.
- **Credentials go only to the configured site**, over https. They are never sent to research URLs, and they are dropped if the site redirects to another host.
- **Updates only touch posts the pipeline wrote**: posts by `author_id` or carrying one of `always_tags`. In draft mode a live post is never changed.
- **Going live needs two keys**: `"status": "publish"` in the config and `AUTOWRITER_ALLOW_PUBLISH=1` in the environment.
- **The run folder is emptied only if the helper created it**, so a mistyped `run_dir` cannot wipe a project.
- Slugs are cleaned, so file output cannot escape `output_dir`. Titles, excerpts, captions and SEO fields are stored as plain text. New tags are created only from `always_tags` unless you set `allow_create_tags`.

What it cannot do: the credentials are environment variables in the same session the model runs in, and the skill only *tells* the model not to read them. Treat the application password as exposed to the session. Give it to a dedicated low-privilege user (see above), and revoke it in WordPress if anything looks wrong. Fact-checking reduces errors but does not remove them: keep a human editor in the loop, especially for news about real people.

## License

MIT, see [LICENSE](LICENSE).
