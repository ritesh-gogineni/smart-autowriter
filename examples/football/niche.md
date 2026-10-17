# Niche pack: football (soccer) news, UK-leaning audience

This is the worked example. "What the data says" shows the kind of findings a niche pack should hold: patterns from a site's own analytics (GA4 and Search Console), written as rules the scout can apply. They are illustrative priors, not measurements you can rely on: replace them with your own as soon as you have data.

## What the data says
- Posts are perishable: most of an article's views arrive on publish day and almost all within three days. Publish for the next search peak, not for the archive.
- Formats that answer a matchday or decision query (fantasy tips, matchday TV channel, predicted lineups, injury news, player ratings for big clubs and big games) earn far more clicks per post than tactical analysis, talking points, opinion and previews. Do not shortlist the weaker formats unless there is a huge story.
- Click-through is highest on intent-matching titles: player ratings, injury updates and '<club> news'. Titles that mirror these queries win ('<Player> Injury Update and Return Date', '<Club> Player Ratings').
- Lineup and fixture queries are a large, under-claimed pool with high impressions and low click-through, often because several of your own posts split the same query. When a fixture already has a lineup, team-news or TV page from the last 72 hours, prefer UPDATING that canonical page unless a new page targets a clearly different query or a new development.
- Big clubs draw; smaller clubs only work for matchday lineup, team-news and injury queries, not features.
- Google Discover is lottery-shaped: a single post can take most of its clicks. The winners tend to be talking-points pieces on a big national-team result with a star name and a clear human story, published within hours of the final whistle.
- What tends to lose: reaction pieces with no query behind them, pundit quotes, match reports and ratings outside big clubs, previews of smaller matches, lesser leagues, history pieces, price-change posts, overnight reaction pieces, headlines with no big club or player.
- Example target mix: fixture-intent pages (lineups, team news, matchday TV channel) about a third; fantasy heavier in the days before a deadline; then injury updates, ratings for big games, big-story news, and experiments with the rest. Tune it to your own numbers.

## Formats and word ranges
| Format | Query shape | Words | Graphic |
|---|---|---|---|
| Predicted lineups / team news | '<Team A> vs <Team B> predicted lineups' | 400-600 | pitch |
| Matchday TV channel and kick-off | '<A> vs <B> TV channel' (matchday morning only) | 250-400 | none or small table |
| Injury update | '<Player> injury update and return date' | 400-600 | status tracker |
| Fantasy tips (FPL etc.) | 'FPL GW<n> captain picks' | 600-900 | picks table |
| Talking points / what we learned | '<Result>: 5 talking points' | 600-800 | none or bar chart |
| Player ratings | '<Club> player ratings' | 500-700 | ratings table |

## Sources
Trust first: the competition's official site, club sites, the public Fantasy Premier League API (`bootstrap-static` and `fixtures`), UEFA, BBC Sport, Sky Sports, and named tier-1 journalists' own reports. Never: aggregators, betting or tips sites, fan blogs, social posts without a named reporter.

## Volatile vs stable facts
- Volatile: injury statuses and return dates, doubts, predicted or confirmed lineups, suspensions still pending, fantasy flags, prices and ownership, team-news claims, transfer reports.
- Stable: fixtures, kick-off times, TV channels, finished scores, a player's club or nationality, dated quotes from past press conferences, historical stats.
- NEVER cache anything that comes from the fantasy API: always check it against a fresh download.

## Calendar and key dates
Read deadlines and fixtures from the input files (`fpl_bootstrap.json`, `fpl_fixtures.json`) and state: the next fantasy deadline, the fixtures in the next 48 hours with local kick-off times, and what is due now (lineups the day before, refreshed when confirmed lineups land about 75 minutes before kick-off; TV channel on the morning of the match, 07:00-12:00 local; ratings within hours of the final whistle for big games). Add your own season's key dates here and refresh weekly.

## Timing
Most readers are on mobile, and this example assumes a UK-leaning audience; write for UK daytime and give kick-off times in UK time. In the small hours (about 23:00-06:00 UK) almost nobody reads, so publish what people will search for when they wake up (today's and tomorrow's lineups, the TV channel for today's games, fantasy deadline pieces, injury round-ups), not breaking reaction.

## Experiments
Topic types worth testing: women's football, European table permutations, 'Who is X?' explainers, salary and contract explainers, transfer-window explainers. DISCOVER ATTEMPT: 'talking points' or 'what we learned' on a big result from the last 24 hours involving a major nation or star, led by a person and a human storyline (for example 'France 4-1 Belgium: 5 Talking Points from Zidane's Comeback'), with a sharp recognisable photo. Skip the attempt if the story is already covered by a post that did well.

## Extra style rules
- British English (favourite, defence, programme, Man Utd, Spurs).
- Predicted lineups are predictions: say so, and base them on the latest team news and press conferences.
- Do not cite match events (scores, goals, scorers, cards, substitutions) or fixtures; cite team news that comes from a media report rather than the club or manager.
- Extra banned words: arms race, war (for transfers), 'Enter [name].'
- Verify fixtures, kick-off times, scores and league positions against an official source before using them.

## Graphics that fit
- **Predicted XI pitch**: a `div` with a green background (`linear-gradient(#2e7d32,#1b5e20)`), rounded corners, padding 12px; one row per line of the formation from goalkeeper to attack, each row a flex container with `justify-content:space-around; flex-wrap:wrap`; each player a rounded white pill with dark 13px text (surname, optionally number). Under it a small table for the bench, doubts and absences.
- **Fantasy picks table**: Player, Team, Price, Owned %, Next three fixtures; colour fixture cells by the 1-5 difficulty scale in graphics.md.
- **Injury tracker**: Player, Issue, Chance of playing, Expected return, Source, with a coloured status dot.
- **Ratings table**, **bar chart**: as in graphics.md.

## Categories and tags
Always the site's News category plus the club's category; add a league or competition category where one exists. Tags are set in the config (`always_tags`) plus any experiment tag, for example `test-<topic>`.
