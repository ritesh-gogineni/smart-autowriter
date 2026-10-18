# Niche pack: general (topic comes from the config)

This default pack works for any subject. The subject itself is set by the user in `config.json` under `topic` (description, audience, focus areas, things to avoid) or passed for one run with `autowriter.py setup --topic "..."`. Read the `topic` block in `RUN/config.json` before anything else: it defines what is in scope. Anything outside it is not a candidate.

For better results copy `niches/_template/niche.md` to `niches/<name>/niche.md`, fill it with your own evidence, and set `"niche": "<name>"` in the config. See `examples/uk-renters/niche.md` for a complete one.

## What the data says
No site-specific data is available. Work from search evidence only: autocomplete suggestions, what the top results look like, and `stats.json` when it exists. Favour:
- topics tied to a dated event, release, deadline or change (they have a search peak you can publish ahead of);
- exact-question queries ('how to', 'when does', 'is X worth it', 'X vs Y', 'X not working', 'X update') over general features;
- updating the site's own canonical page when it already covers the query.
Avoid reaction pieces and opinion with no query behind them, and anything the top results already answer better than you can.

## Formats and word ranges
Choose from: news explainer 400-600 words; how-to or guide 700-1200; comparison (with a table) 700-1000; 'what to know before' preview 400-600; update or changelog explainer 300-500; Q&A / FAQ 500-800. Do not pad: stop when the information runs out.

## Sources
Trust first: the primary source for the topic (official site, documentation, regulator, standards body, company announcement, the original paper or dataset), then established outlets and named experts reporting first-hand. Never: aggregators, content farms, tips or affiliate-only sites, anonymous forums, social posts without a named source.

## Volatile vs stable facts
- Volatile: prices, availability, versions and release dates still pending, statuses, rankings, statistics that update, anything described as reported, rumoured or expected.
- Stable: past events and dates, definitions, historical figures, specifications that do not change, biographical facts.
- Never cache anything that comes from a live data feed named in the config inputs.

## Calendar and key dates
Use the config inputs and the news to list what is due in the next 48 hours to two weeks, and what that implies is due now.

## Timing
Use `site.timezone` and `site.audience`. When few people are reading (roughly 23:00-06:00 local), publish what readers will search for when they wake up rather than breaking reaction.

## Experiments
When the run mode is EXPERIMENT, pick a topic type the site has not tried much that is still inside the configured topic, and tag it as an experiment so its results can be compared later.

## Extra style rules
Use the spelling variant of `site.language`. No extra banned words beyond the shared list.

## Categories and tags
Use only categories that already exist on the site. Tags come from the config `always_tags` plus any experiment tag.
