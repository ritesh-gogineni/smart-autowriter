# Inline HTML graphics

Build ONE or TWO graphics when the piece has real data. Never build decorative filler. Every number in a graphic must come from a verified source and also appear in a nearby sentence or table, so it is not trapped in the graphic.

Rules for all graphics:
- Inline HTML and CSS only, readable at 360px wide.
- Must work in light and dark mode: for text on a transparent background use `color:inherit`; any coloured background must set its own text colour with strong contrast; use `rgba(128,128,128,0.25)` for neutral tracks and borders.
- Give each graphic a short text summary in an `aria-label`.

Types (pick what the data supports; the niche pack lists the ones that fit its subject):
- **Table**: the default for lists of items with several attributes. Sortable by eye: put the important column first.
- **Status tracker**: a table with a coloured dot (a `span` with `border-radius:50%`) per row: red out, amber doubt, green fine.
- **Bar chart**: rows of label plus a `div` whose width is the percentage (inline background `#1e88e5`, height 14px, rounded) on a neutral track, with the value printed next to the bar.
- **Ranked list with ratings**: a table of Name, Score, one-line reason, sorted by score, with the top and bottom visually marked.
- **Heat-coloured cells**: colour table cells on a 1-5 scale (1 `#00a86b`, 2 `#7bd88f`, 3 `#e0e0e0`, 4 `#ff8a65`, 5 `#d32f2f`) with dark text, white text on 5.
- **Diagram**: a flex layout (`display:flex; justify-content:space-around; flex-wrap:wrap`) of rounded pills, one row per group. See the niche pack for domain diagrams.
