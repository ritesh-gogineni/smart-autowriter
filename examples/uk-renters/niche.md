# Niche pack: personal finance for UK renters

This is the worked example. It matches the topic area in `config.example.json`. The points in "What the data says" are illustrative priors, the kind of findings a niche pack should hold; they are not measurements. Replace them with patterns from your own analytics (for example GA4 and Search Console) as soon as you have data.

## What the data says
- Rule changes and deadlines drive search. Readers search when something changes for them (a new law takes effect, the energy price cap moves, a benefit rate changes, the tax year turns), so publish ahead of the date, then update the same page when it happens.
- Exact-question queries beat general features: 'can my landlord increase my rent', 'how to get my deposit back', 'what is a section 21 notice', 'how much is the energy price cap'. Titles that mirror the question win.
- Renters act on what they read. Practical guides with steps, templates and deadlines earn more clicks and return visits than commentary.
- Evergreen explainers (deposits, rent increases, repairs, eviction notices) keep earning for months: keep one canonical page per question and UPDATE it when the rules change, instead of writing a new post each time.
- Nation matters. Housing law differs between England, Scotland, Wales and Northern Ireland, and readers search with the nation in the query. A page that mixes them up loses trust.
- What tends to lose: opinion with no question behind it, political reaction, investment content, and pieces the official guidance already answers better.
- Example target mix: rule-change explainers and 'what it means for you' pieces about a third; evergreen how-to guides about a third; cost-of-living updates (energy, council tax, benefits) a quarter; experiments the rest. Tune it to your own numbers.

## Formats and word ranges
| Format | Query shape | Words | Graphic |
|---|---|---|---|
| Rule-change explainer | '<rule> what changes for renters' | 500-800 | before/after table |
| How-to guide | 'how to <task>' (deposit back, challenge a rent increase, report disrepair) | 700-1200 | step list, checklist table |
| Rights Q&A | 'can my landlord <action>' | 500-800 | yes/no table by nation |
| Cost update | '<bill> price cap <month>' / '<benefit> rates <year>' | 400-600 | comparison table, bar chart |
| Deadline reminder | '<deadline> date <year>' | 300-500 | none or small table |

## Sources
Trust first: GOV.UK, legislation.gov.uk, the devolved governments (gov.scot, gov.wales, nidirect), HMRC, DWP, Ofgem, the ONS, local council sites, the government-approved tenancy deposit schemes, Shelter, and Citizens Advice. Then established outlets and named experts reporting first-hand. Never: lettings-agent marketing pages, comparison or affiliate sites presented as guidance, anonymous forums, social posts without a named source.

## Volatile vs stable facts
- Volatile: commencement dates still to be confirmed, energy price cap levels, benefit and Local Housing Allowance rates, council tax for the coming year, average rent figures, anything described as proposed, expected or under consultation.
- Stable: what an Act or regulation says once in force, dates that have passed, definitions (assured shorthold tenancy, section 21, section 8), how the deposit protection rules work.
- Always state which nation a rule applies to. Treat a fact verified for England as unverified for Scotland, Wales or Northern Ireland.

## Calendar and key dates
Keep this list current and check every date against the official source before using it:
- Energy price cap: Ofgem announces a new cap ahead of each quarter. Publish the explainer on announcement day and update it when the cap takes effect.
- Tax year: starts 6 April; council tax bills and many benefit rates change in April.
- Budget and fiscal events: changes to housing benefit, Local Housing Allowance and tax thresholds.
- ONS private rent statistics: published monthly.
- Commencement dates for housing law changes: the government announces them; each one is a rule-change explainer.

## Timing
Most readers are on mobile and read in the evening and at weekends, when they deal with bills and admin. Publish rule-change pieces before the change takes effect, not after. Overnight, publish evergreen guides rather than news.

## Experiments
Topic types worth testing: nation-specific versions of the top guides (Scotland and Wales), letter templates, 'what to do if' scenarios (mould, a no-fault eviction notice, a deposit dispute), and moving-house cost checklists. Tag them as experiments so their results can be compared later.

## Extra style rules
- British English (licence, programme, organisation).
- Never give regulated financial or legal advice: explain the rules and point readers to Shelter, Citizens Advice or a solicitor for their own case.
- Use the official names of schemes and notices on first mention (for example 'section 21 notice'), then plain words.
- Extra banned words: crackdown, landlord war, tenant revolution.

## Graphics that fit
- **Before/after table**: Rule, Before, After, From (date), Applies to (nation).
- **Rights by nation table**: Question, England, Scotland, Wales, Northern Ireland, with a coloured dot per cell (green yes, amber depends, red no).
- **Checklist table**: Step, What to do, Deadline, Where.
- **Bar chart** for cost comparisons, as in graphics.md.

## Categories and tags
Use the site's existing categories (for example Renting, Bills, Benefits). Tags come from the config `always_tags` plus any experiment tag, for example `test-<topic>`.
