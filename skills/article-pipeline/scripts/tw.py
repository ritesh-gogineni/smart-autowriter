#!/usr/bin/env python3
"""tw.py - helper for the tiered-writer plugin. Standard library only.

  tw.py setup [--topic "..."]         prepare a run folder: inputs, recent posts, caches, niche pack, mode
  tw.py claim --candidate ID words..  register this run's topic; print what other runs claimed
  tw.py recent [--minutes N]          posts published in the last N minutes (pre-publish duplicate check)
  tw.py media words..                 search the pre-cleared photo index (WordPress backend only)
  tw.py media-index                   (re)build the photo index from the WordPress media library
  tw.py publish MANIFEST.json         publish (or update) a post from a manifest; prints a JSON result
  tw.py finish [--candidate ID] [--post-id N] [--post-url URL]   merge caches, mark the claim published

Config: tiered-writer.config.json in the working directory (or --config, or env TW_CONFIG).
Publishers: "docx" (Word file per article), "files" (HTML file per article) or "wordpress" (REST API).
Secrets come only from the environment: TW_WP_USER and TW_WP_APP_PASSWORD. They never go in the config
and the model never needs them: this script does all the publishing, and sends them only to the configured
https site. Going live (status "publish") also needs TW_ALLOW_PUBLISH=1, set by a human, not by the model."""
import argparse, base64, datetime as dt, html, json, os, re, shutil, sys, time, unicodedata, zipfile
import urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
PLUGIN_DIR = os.path.dirname(os.path.dirname(SKILL_DIR))
UA = 'Mozilla/5.0 (tiered-writer)'
KIND_RANK = {'wikimedia_cc': 0, 'stock_free': 1, 'ai_illustration': 2}
RUN_MARK = '.tw-run'

DEFAULTS = {
    'site': {'name': 'My Site', 'url': '', 'language': 'en-GB', 'audience': '', 'timezone': 'UTC'},
    'topic': {'description': '', 'audience': '', 'focus': [], 'avoid': []},
    'niche': 'general',
    'storage': {'backend': 'local', 'dir': '.tiered-writer/state', 'page_prefix': 'tw-state-'},
    'run_dir': '.tiered-writer/run',
    'publisher': {'type': 'docx', 'status': 'draft', 'output_dir': 'articles',
                  'wordpress': {'base_url': '', 'author_id': 0, 'meta_map': {}, 'stats_endpoint': '',
                                'always_tags': [], 'allow_create_tags': False, 'recent_tag_id': 0}},
    'research': {'inputs': []},
    'modes': [],
    'photo': {'min_width': 1000, 'license_patterns': {
        'wikimedia_cc': ['wikimedia', 'cc by', 'cc0', 'public domain'],
        'stock_free': ['unsplash', 'pixabay', 'pexels'],
        'ai_illustration': ['ai-generated', 'generated with ai', 'ai generated']}},
    'cache': {'volatile_ttl_min': 180, 'stable_ttl_min': 2880, 'open_candidate_ttl_min': 480,
              'used_candidate_ttl_min': 180, 'claim_ttl_min': 120, 'max_facts': 400, 'max_candidates': 12},
}


def deep_merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path=None):
    path = path or os.environ.get('TW_CONFIG') or 'tiered-writer.config.json'
    if not os.path.exists(path):
        return deep_merge(DEFAULTS, {})
    return deep_merge(DEFAULTS, json.load(open(path, encoding='utf8')))


CFG = DEFAULTS
TZ_OK = [True]
RUN = '.tiered-writer/run'


class Refused(Exception):
    """A safety rule stopped the command. Printed as {ok:false,error} and never retried."""


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso(t=None):
    return (t or now()).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse(s):
    try:
        return dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None


def age_min(s):
    t = parse(s or '')
    return (now() - t).total_seconds() / 60 if t else 10 ** 9


def local_time(t):
    try:
        from zoneinfo import ZoneInfo
        return t.astimezone(ZoneInfo(CFG['site']['timezone']))
    except Exception:
        TZ_OK[0] = False  # no tz database (common on Windows without the tzdata package)
        return t


# ---------------------------------------------------------------- http (credentials only ever go to the site)
def wp_root():
    u = (CFG['publisher']['wordpress'].get('base_url') or '').rstrip('/')
    p = urllib.parse.urlparse(u)
    if not p.hostname or (p.scheme != 'https' and p.hostname not in ('localhost', '127.0.0.1')):
        raise Refused(f'wordpress.base_url must be an https:// address (got {u!r}); '
                      'over plain http the password would travel in clear text')
    return u


def wp_base():
    return wp_root() + '/wp-json'


def auth_header(url):
    """Basic auth for the configured WordPress site only, never for research inputs or any other URL."""
    u, p = os.environ.get('TW_WP_USER', ''), os.environ.get('TW_WP_APP_PASSWORD', '')
    if not (u and p):
        return ''
    try:
        if not url.startswith(wp_base() + '/'):
            return ''
    except Refused:
        return ''
    return 'Basic ' + base64.b64encode(f'{u}:{p}'.encode()).decode()


class SameSiteRedirect(urllib.request.HTTPRedirectHandler):
    """urllib forwards the Authorization header on redirects, even to another host. Drop it unless the
    redirect stays on the same scheme and host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        a, b = urllib.parse.urlparse(req.full_url), urllib.parse.urlparse(newurl)
        if new is not None and (a.scheme, a.netloc) != (b.scheme, b.netloc):
            new.headers.pop('Authorization', None)
            new.unredirected_hdrs.pop('Authorization', None)
        return new


OPENER = urllib.request.build_opener(SameSiteRedirect)


def http(url, body=None, method=None, auth=True, raw=None, headers=None, retries=2):
    """JSON in/out. `raw` sends bytes as the body instead. Retries on failure."""
    err = None
    for _ in range(retries + 1):
        try:
            h = {'User-Agent': UA}
            a = auth_header(url) if auth else ''
            if a:
                h['Authorization'] = a
            data = None
            if raw is not None:
                data = raw
            elif body is not None:
                data = json.dumps(body).encode()
                h['Content-Type'] = 'application/json'
            h.update(headers or {})
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            with OPENER.open(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            err = RuntimeError(f'HTTP {e.code} {url}: {e.read()[:300]!r}')
            if e.code in (400, 401, 403, 404):
                break
            time.sleep(2)
        except Exception as e:  # noqa
            err = e
            time.sleep(2)
    raise err


def save(name, data):
    with open(os.path.join(RUN, name), 'w', encoding='utf8') as f:
        f.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))


def txt(s):
    return html.unescape(re.sub('<[^>]+>', '', s or '')).strip()


def plain(s):
    """Text for fields that should never hold markup: titles, excerpts, captions, SEO fields."""
    return re.sub(r'[<>]', '', txt(str(s or ''))).strip()


def norm(s):
    return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()


def safe_slug(s, title=''):
    s = re.sub(r'[^a-z0-9]+', '-', norm(str(s or title or ''))).strip('-')[:90].strip('-')
    return s or 'article-' + now().strftime('%Y%m%d-%H%M%S')


# ---------------------------------------------------------------- run folder and manifest paths
def same_or_inside(path, root):
    path, root = os.path.normcase(path), os.path.normcase(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def run_file(p):
    """Manifest paths must point inside the run folder, so a manipulated manifest cannot publish
    a key, a .env file or anything else on this machine."""
    full, root = os.path.realpath(str(p)), os.path.realpath(RUN)
    if not same_or_inside(full, root) or full == root:
        raise Refused(f'{p} is outside the run folder {root}; only files in the run folder can be published')
    if not os.path.isfile(full):
        raise Refused(f'{p} does not exist')
    return full


def reset_run_dir():
    """Empty the run folder for a new run. Refuses anything that is not a run folder this script made,
    so a mistyped run_dir can never wipe a project."""
    root, cwd = os.path.realpath(RUN), os.path.realpath(os.getcwd())
    home = os.path.realpath(os.path.expanduser('~'))
    if os.path.dirname(root) == root or same_or_inside(cwd, root) or os.path.normcase(root) == os.path.normcase(home):
        print(f'FATAL: run_dir {root} is the project, home or a parent folder. Point run_dir at a dedicated '
              'folder such as .tiered-writer/run')
        sys.exit(2)
    if os.path.isdir(root) and os.listdir(root) and not os.path.exists(os.path.join(root, RUN_MARK)):
        print(f'FATAL: run_dir {root} already has files and was not made by tiered-writer, so it will not be '
              'emptied. Choose another run_dir or empty it yourself.')
        sys.exit(2)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    with open(os.path.join(root, RUN_MARK), 'w', encoding='utf8') as f:
        f.write('tiered-writer run folder: emptied at the start of every run\n')


def post_status():
    s = CFG['publisher'].get('status') or 'draft'
    if s not in ('draft', 'pending', 'publish'):
        s = 'draft'
    if s == 'publish' and os.environ.get('TW_ALLOW_PUBLISH') != '1':
        print('note: status "publish" also needs TW_ALLOW_PUBLISH=1 in the environment; saved as draft',
              file=sys.stderr)
        return 'draft'
    return s


# ---------------------------------------------------------------- HTML safety
ALLOWED_TAGS = {'p', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'strong', 'b', 'em', 'i', 'a', 'table', 'thead', 'tbody',
                'tr', 'th', 'td', 'div', 'span', 'br', 'small', 'blockquote', 'figure', 'figcaption'}
DROP_WITH_CONTENT = {'script', 'style', 'iframe', 'object', 'embed', 'noscript', 'template', 'svg', 'math', 'form',
                     'textarea', 'select', 'button', 'frameset', 'head', 'title', 'canvas', 'video', 'audio'}
BAD_CSS = re.compile(r'expression|url\s*\(|javascript|@import|behavio|binding|position\s*:\s*(fixed|absolute|sticky)',
                     re.I)


class Sanitizer(HTMLParser):
    """Rebuilds article HTML from an allowlist. Model output can carry text planted by a web page, and a
    WordPress Editor may post unfiltered HTML, so nothing executable may survive."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.open, self.drop, self.removed = [], [], 0, set()

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.drop += 1
            self.removed.add(tag)
            return
        if self.drop:
            return
        if tag not in ALLOWED_TAGS:
            self.removed.add(tag)
            return
        keep = []
        for k, v in attrs:
            v = (v or '').strip()
            if tag == 'a' and k == 'href':
                if re.match(r'(https?://|mailto:|#|/)', v, re.I):
                    keep.append((k, v))
                else:
                    self.removed.add('href=' + v.split(':')[0][:20])
            elif tag == 'a' and k == 'target':
                if v == '_blank':
                    keep += [('target', '_blank'), ('rel', 'noopener')]
            elif k == 'style':
                if v and '\\' not in v and not BAD_CSS.search(v):
                    keep.append((k, v))
                elif v:
                    self.removed.add('unsafe style')
            elif k in ('aria-label', 'title'):
                keep.append((k, v))
            elif k in ('colspan', 'rowspan') and tag in ('td', 'th') and v.isdigit():
                keep.append((k, v))
            elif k.startswith('on'):
                self.removed.add(k)
        self.out.append(f'<{tag}' + ''.join(f' {k}="{html.escape(v)}"' for k, v in keep) + '>')
        if tag != 'br':
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.removed.add(tag)
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.drop = max(0, self.drop - 1)
            return
        if self.drop or tag not in self.open:
            return
        while self.open:
            t = self.open.pop()
            self.out.append(f'</{t}>')
            if t == tag:
                break

    def handle_data(self, d):
        if not self.drop:
            self.out.append(html.escape(d, quote=False))


def clean_html(s):
    p = Sanitizer()
    p.feed(s or '')
    p.close()
    p.out += [f'</{t}>' for t in reversed(p.open)]
    if p.removed:
        print('sanitised, removed: ' + ', '.join(sorted(p.removed)), file=sys.stderr)
    return ''.join(p.out)


# ---------------------------------------------------------------- state storage
class LocalStore:
    def __init__(self, d):
        self.d = d
        os.makedirs(d, exist_ok=True)

    def get(self, name):
        p = os.path.join(self.d, name + '.json')
        return open(p, encoding='utf8').read() if os.path.exists(p) else None

    def put(self, name, text):
        tmp = os.path.join(self.d, name + '.json.tmp')
        with open(tmp, 'w', encoding='utf8') as f:
            f.write(text)
        os.replace(tmp, os.path.join(self.d, name + '.json'))


class WPPageStore:
    """State kept in private WordPress pages, so separate cloud runs (fresh sandboxes) share it."""

    def __init__(self, prefix):
        self.b = wp_base() + '/wp/v2'
        self.prefix = prefix

    def _page(self, name):
        r = http(f"{self.b}/pages?slug={self.prefix}{name}&status=private&context=edit&_fields=id,content")
        return r[0] if r else None

    def get(self, name):
        p = self._page(name)
        return p['content']['raw'] if p else None

    def put(self, name, text):
        p = self._page(name)
        slug = self.prefix + name
        if p:
            http(f"{self.b}/pages/{p['id']}", {'content': text}, method='POST')
        else:
            http(f"{self.b}/pages", {'title': slug, 'slug': slug, 'status': 'private', 'content': text}, method='POST')


def store():
    s = CFG['storage']
    if s['backend'] == 'wordpress_pages':
        return WPPageStore(s['page_prefix'])
    return LocalStore(s['dir'])


def jload(st, name, default):
    try:
        t = st.get(name)
        if t and t.strip().startswith(('{', '[')):
            return json.loads(t)
    except Exception:
        pass
    return default


# ---------------------------------------------------------------- publisher: recent posts
def recent_posts(n=100):
    """Return [{id,date_gmt,title,link,categories,tags}] newest first."""
    if CFG['publisher']['type'] == 'wordpress':
        rows = []
        for pg in range(1, (n + 49) // 50 + 1):
            rows += http(f"{wp_base()}/wp/v2/posts?per_page=50&page={pg}&_fields=id,date_gmt,title,link,categories,tags",
                         auth=False)
        return [{'id': r['id'], 'date_gmt': r['date_gmt'], 'title': txt(r['title']['rendered']), 'link': r['link'],
                 'categories': r.get('categories', []), 'tags': r.get('tags', [])} for r in rows[:n]]
    out_dir = CFG['publisher']['output_dir']
    rows = []
    if os.path.isdir(out_dir):
        for fn in os.listdir(out_dir):
            if fn.endswith('.json'):
                try:
                    d = json.load(open(os.path.join(out_dir, fn), encoding='utf8'))
                    rows.append({'id': d.get('slug', fn), 'date_gmt': d.get('published_utc', ''), 'title': d.get('title', ''),
                                 'link': d.get('file') or os.path.join(out_dir, d.get('slug', fn) + '.html'),
                                 'categories': [], 'tags': []})
                except Exception:
                    pass
    return sorted(rows, key=lambda r: r['date_gmt'], reverse=True)[:n]


def age_of(row):
    d = (row.get('date_gmt') or '')[:19]
    return age_min(d + 'Z') if d else 10 ** 9


# ---------------------------------------------------------------- setup
def pick_mode(t):
    for m in CFG.get('modes', []):
        if t.hour in m.get('hours_utc', []) and t.minute < m.get('before_minute', 60):
            return m['name']
    return 'NORMAL'


def setup(a):
    if a.topic:
        CFG['topic']['description'] = a.topic
    if not CFG['topic']['description'].strip():
        print('FATAL: no topic area. Set "topic.description" in tiered-writer.config.json or run: '
              'tw.py setup --topic "<the subject area to cover>"')
        sys.exit(2)
    if CFG['publisher']['type'] == 'wordpress':
        try:
            wp_root()
        except Refused as e:
            print(f'FATAL: {e}')
            sys.exit(2)
    reset_run_dir()
    out, bad = [], 0

    def step(label, fn):
        nonlocal bad
        try:
            out.append(f'ok   {label}: {fn()}')
        except Exception as e:  # noqa
            bad += 1
            out.append(f'FAIL {label}: {e}')

    def recent():
        rows = recent_posts(100)
        save('recent.json', rows)
        return f'{len(rows)} posts'
    step('recent.json', recent)

    wp = CFG['publisher']['wordpress']
    if CFG['publisher']['type'] == 'wordpress' and wp.get('stats_endpoint'):
        step('stats.json', lambda: (save('stats.json', http(wp_base() + wp['stats_endpoint'])), 'saved')[1])

    for inp in CFG['research'].get('inputs', []):
        name = os.path.basename(inp['save_as'])
        step(name, lambda inp=inp, name=name: (save(name, http(inp['url'], auth=False)), 'saved')[1])

    st = store()
    initial = {'cache_research': {'updated_utc': iso(), 'news_checked_until_utc': None, 'performance': {}, 'candidates': []},
               'cache_facts': {'updated_utc': iso(), 'facts': []}}
    for name, init in initial.items():
        def cc(name=name, init=init):
            data = jload(st, name, None)
            if data is None:
                st.put(name, json.dumps(init))
                data = init
            save(name + '.json', data)
            n = len(data.get('candidates', data.get('facts', [])))
            return f"{n} entries, updated {int(age_min(data.get('updated_utc')))} min ago"
        step(name + '.json', cc)

    if CFG['storage']['backend'] == 'wordpress_pages':
        step('media_index.json', lambda: (save('media_index.json', jload(st, 'media_index', {'items': []})), 'saved')[1])
    else:
        step('media_index.json', lambda: (save('media_index.json', {'items': []}), 'empty (no library on this backend)')[1])

    # niche pack and shared references, copied next to the run files so subagents can read them
    niche = CFG['niche']
    cands = [niche, os.path.join('niches', niche, 'niche.md'), os.path.join(PLUGIN_DIR, 'niches', niche, 'niche.md'),
             os.path.join(PLUGIN_DIR, 'examples', niche, 'niche.md')]
    src = next((c for c in cands if os.path.isfile(c)), None)
    if src:
        shutil.copy(src, os.path.join(RUN, 'niche.md'))
        out.append(f'ok   niche.md: {src}')
    else:
        bad += 1
        out.append(f'FAIL niche.md: no niche pack found for {niche!r}')
    shutil.copytree(os.path.join(SKILL_DIR, 'references'), os.path.join(RUN, 'references'))
    save('config.json', CFG)

    t = now()
    mode = pick_mode(t)
    lt = local_time(t)
    zone = CFG['site']['timezone'] if TZ_OK[0] else 'UTC (timezone data missing: pip install tzdata for local time)'
    save('mode.txt', f"MODE: {mode}\nRun start: {t.strftime('%Y-%m-%d %H:%M')} UTC = {lt.strftime('%a %d %b %H:%M')} {zone}\n")
    out.append(f'mode: {mode}')
    out.append(f"publisher: {CFG['publisher']['type']}, status {post_status()}")
    out.append(f'run dir: {os.path.abspath(RUN)}')
    print('\n'.join(out))
    if not src:
        print('FATAL: niche pack missing')
        sys.exit(2)


# ---------------------------------------------------------------- claims / recent
def load_claims(st):
    return jload(st, 'claims', {}).get('claims', [])


def save_claims(st, cl):
    st.put('claims', json.dumps({'updated_utc': iso(), 'claims': cl}))


def claim_cmd(a):
    st = store()
    mine = a.candidate or 'unknown'
    ttl = CFG['cache']['claim_ttl_min']
    cl = [c for c in load_claims(st) if age_min(c.get('claimed_utc')) <= ttl]
    others = [c for c in cl if c.get('id') != mine]
    print(f'OTHER ACTIVE CLAIMS (other runs, last {ttl} minutes):')
    if not others:
        print('  none')
    for c in sorted(others, key=lambda c: age_min(c.get('claimed_utc'))):
        extra = f" -> post {c.get('post_id')} {c.get('post_url', '')}" if c.get('post_id') else ''
        print(f"  [{c.get('status', '?')}] {int(age_min(c.get('claimed_utc')))} min ago: {c.get('topic', '')} (id {c.get('id')}){extra}")
    cl = [c for c in cl if c.get('id') != mine]
    cl.append({'id': mine, 'topic': ' '.join(a.terms), 'claimed_utc': iso(), 'status': 'writing'})
    save_claims(st, cl)
    print(f"claimed: {mine} / {' '.join(a.terms)}")


def recent_cmd(a):
    mins = a.minutes or 90
    n = 0
    for r in recent_posts(15):
        age = age_of(r)
        if age <= mins:
            n += 1
            print(f"id={r['id']} {int(age)} min ago {r['title']} | {r['link']}")
    if not n:
        print(f'no posts published in the last {mins} minutes')


# ---------------------------------------------------------------- media library (WordPress)
def media_kind(r):
    pats = CFG['photo']['license_patterns']
    cl = txt(r['caption']['rendered']).lower()
    ti = txt(r['title']['rendered']).lower()
    alt = (r.get('alt_text') or '').lower()
    for kind in ('wikimedia_cc', 'stock_free', 'ai_illustration'):
        for p in pats.get(kind, []):
            if p in cl or (kind == 'ai_illustration' and alt.startswith(p)) or (kind == 'stock_free' and ti.startswith('photo by')):
                return kind
    return None


def media_index_cmd(_a):
    if CFG['publisher']['type'] != 'wordpress':
        print('media-index needs publisher.type = wordpress')
        return
    items, pg = [], 1
    while True:
        try:
            rows = http(f"{wp_base()}/wp/v2/media?per_page=100&page={pg}&orderby=id&order=desc&_fields="
                        "id,date,source_url,alt_text,caption,title,mime_type,media_details", auth=False)
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            k = media_kind(r)
            if k and str(r.get('mime_type', '')).startswith('image/'):
                md = r.get('media_details') or {}
                items.append({'id': r['id'], 'kind': k, 'url': r['source_url'], 'w': md.get('width') or 0, 'h': md.get('height') or 0,
                              'date': r['date'][:10], 'alt': r['alt_text'] or '', 'title': txt(r['title']['rendered']),
                              'caption': txt(r['caption']['rendered'])})
        pg += 1
    store().put('media_index', json.dumps({'built': iso(), 'items': items}, ensure_ascii=False))
    by = {}
    for it in items:
        by[it['kind']] = by.get(it['kind'], 0) + 1
    print('indexed', len(items), by)


def media_cmd(a):
    path = os.path.join(RUN, 'media_index.json')
    items = json.load(open(path, encoding='utf8')).get('items', []) if os.path.exists(path) else []
    ts = [norm(t) for t in a.terms if t.strip()]
    if not ts:
        print('usage: tw.py media <words..>')
        return
    scored = []
    for it in items:
        text = norm(' '.join([it.get('alt', ''), it.get('title', ''), it.get('caption', '')]))
        sc = sum(1 for t in ts if t in text)
        if sc and (it.get('w') or 0) >= CFG['photo']['min_width']:
            scored.append((sc, -KIND_RANK.get(it['kind'], 9), it.get('date', ''), it))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    if not scored:
        print('no pre-cleared library images match', ts)
        return
    for sc, _, _, it in scored[:12]:
        print(f"id={it['id']} kind={it['kind']} {it['w']}x{it['h']} matched={sc}/{len(ts)} date={it['date']}")
        print(f"  alt: {it['alt'][:160]}")
        print(f"  caption: {it['caption'][:160]}")
        print(f"  url: {it['url']}")


# ---------------------------------------------------------------- manifest
def manifest_text(m, key):
    """content / excerpt: from <key>_file (which must be inside RUN) or inline in the manifest."""
    if m.get(key + '_file'):
        return open(run_file(m[key + '_file']), encoding='utf8').read()
    return str(m.get(key) or '')


def image_bytes(img):
    """The featured image file from the manifest: inside RUN, and really a JPEG or PNG."""
    if not img.get('file'):
        return None, None
    data = open(run_file(img['file']), 'rb').read()
    if data[:3] == b'\xff\xd8\xff':
        return data, 'jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return data, 'png'
    raise Refused(f"{img['file']} is not a JPEG or PNG image")


# ---------------------------------------------------------------- publisher: WordPress
def resolve_terms(kind, names, create):
    ids = []
    for n in names:
        if isinstance(n, int):
            ids.append(n)
            continue
        q = urllib.parse.quote(str(n))
        found = http(f"{wp_base()}/wp/v2/{kind}?search={q}&per_page=50&_fields=id,name,slug")
        hit = next((f for f in found if norm(f['name']) == norm(n) or f['slug'] == norm(n).replace(' ', '-')), None)
        if hit:
            ids.append(hit['id'])
        elif create:
            ids.append(http(f"{wp_base()}/wp/v2/{kind}", {'name': plain(n)}, method='POST')['id'])
        else:
            print(f'warning: {kind[:-1]} {n!r} not found, skipped', file=sys.stderr)
    return ids


def check_update_target(pid, status):
    """Updates may only touch posts this pipeline wrote (the configured author, or carrying one of the
    always_tags), and never a live post while the pipeline is in draft mode."""
    wp = CFG['publisher']['wordpress']
    post = http(f"{wp_base()}/wp/v2/posts/{pid}?context=edit&_fields=id,status,author,tags")
    ours = bool(wp.get('author_id')) and post.get('author') == wp['author_id']
    if not ours and wp.get('always_tags'):
        ours = bool(set(resolve_terms('tags', wp['always_tags'], create=False)) & set(post.get('tags') or []))
    if not ours:
        raise Refused(f'post {pid} was not written by this pipeline (it needs author_id {wp.get("author_id")} or one of '
                      f'the always_tags {wp.get("always_tags")}); a human must update it')
    if post['status'] == 'publish' and status != 'publish':
        raise Refused(f'post {pid} is live and the pipeline is in draft mode, so it will not change a live post; '
                      'a human must apply the update')


def publish_wordpress(m):
    wp, status = CFG['publisher']['wordpress'], post_status()
    body = {'title': plain(m['title']), 'content': clean_html(manifest_text(m, 'content')),
            'excerpt': plain(manifest_text(m, 'excerpt')), 'status': status}
    pid = int(m['update_post_id']) if m.get('update_post_id') else None
    if pid:
        check_update_target(pid, status)
    if m.get('slug'):
        body['slug'] = safe_slug(m['slug'])
    if wp.get('author_id'):
        body['author'] = wp['author_id']
    cats = resolve_terms('categories', m.get('categories', []), create=False)
    tags = (resolve_terms('tags', list(wp.get('always_tags', [])), create=True)
            + resolve_terms('tags', list(m.get('tags', [])), wp.get('allow_create_tags', False)))
    if cats:
        body['categories'] = cats
    if tags:
        body['tags'] = sorted(set(tags))
    meta = {wpkey: plain(m[key]) for key, wpkey in (wp.get('meta_map') or {}).items() if m.get(key)}
    if meta:
        body['meta'] = meta
    img = m.get('image') or {}
    if img.get('existing_media_id'):
        chk = http(f"{wp_base()}/wp/v2/media/{int(img['existing_media_id'])}?_fields=id")
        body['featured_media'] = chk['id']
    elif img.get('file'):
        data, kind = image_bytes(img)
        fn = f"{safe_slug(m.get('slug'), m.get('title'))}.{'png' if kind == 'png' else 'jpg'}"
        up = http(f"{wp_base()}/wp/v2/media", raw=data, method='POST',
                  headers={'Content-Disposition': f'attachment; filename={fn}', 'Content-Type': f'image/{kind}'})
        http(f"{wp_base()}/wp/v2/media/{up['id']}", {'alt_text': plain(img.get('alt_text')),
                                                     'caption': plain(img.get('caption'))}, method='POST')
        body['featured_media'] = up['id']
    if pid:
        body.pop('slug', None)
        body.pop('status', None)  # an update keeps the post's current status
        post = http(f"{wp_base()}/wp/v2/posts/{pid}", body, method='POST')
    else:
        try:
            post = http(f"{wp_base()}/wp/v2/posts", body, method='POST')
        except RuntimeError as e:
            if 'meta' in body and 'meta' in str(e).lower():
                body.pop('meta')
                post = http(f"{wp_base()}/wp/v2/posts", body, method='POST')
            else:
                raise
    back = http(f"{wp_base()}/wp/v2/posts/{post['id']}?context=edit&_fields=id,status,title,content,featured_media,link")
    ok = (back['status'] in (status, 'publish', 'draft', 'future', 'pending') and bool(back['content']['raw'].strip())
          and (not body.get('featured_media') or back['featured_media'] == body['featured_media']))
    return {'ok': ok, 'id': post['id'], 'status': back['status'], 'link': post.get('link') or back.get('link'),
            'featured_media': back['featured_media']}


# ---------------------------------------------------------------- publisher: Word (.docx), standard library only
W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
OFFICE_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def xt(s):
    return html.escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(s)), quote=True)


def docx_styles(lang):
    def heading(n, size):
        return (f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
                '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/>'
                f'<w:spacing w:before="280" w:after="100"/><w:outlineLvl w:val="{n - 1}"/></w:pPr>'
                f'<w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr></w:style>')
    border = ''.join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
                     for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'))
    return (XML_HEAD + f'<w:styles {W_NS}><w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/>'
            f'<w:lang w:val="{xt(lang)}"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
            '<w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
            '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>'
            '<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="120"/></w:pPr>'
            '<w:rPr><w:b/><w:sz w:val="44"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/>'
            '<w:next w:val="Normal"/><w:qFormat/><w:rPr><w:i/><w:color w:val="555555"/><w:sz w:val="26"/></w:rPr></w:style>'
            + heading(1, 32) + heading(2, 26) + heading(3, 24) +
            '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>'
            '<w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="60"/><w:contextualSpacing/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/>'
            '<w:qFormat/><w:pPr><w:ind w:left="720" w:right="720"/></w:pPr><w:rPr><w:i/><w:color w:val="404040"/></w:rPr></w:style>'
            '<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/>'
            '<w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr></w:style>'
            '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
            '<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>'
            f'<w:tblPr><w:tblBorders>{border}</w:tblBorders><w:tblCellMar><w:top w:w="40" w:type="dxa"/>'
            '<w:left w:w="108" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
            '</w:tblCellMar></w:tblPr></w:style></w:styles>')


def docx_numbering(kinds):
    abstract = []
    for aid, fmt in ((0, 'bullet'), (1, 'decimal')):
        lv = ''
        for lvl in range(3):
            text = ('•', '◦', '▪')[lvl] if fmt == 'bullet' else f'%{lvl + 1}.'
            lv += (f'<w:lvl w:ilvl="{lvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
                   f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{720 * (lvl + 1)}" w:hanging="360"/></w:pPr></w:lvl>')
        abstract.append(f'<w:abstractNum w:abstractNumId="{aid}"><w:multiLevelType w:val="hybridMultilevel"/>{lv}</w:abstractNum>')
    nums = ''.join(f'<w:num w:numId="{n}"><w:abstractNumId w:val="{0 if k == "bullet" else 1}"/>'
                   + ('<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>' if k == 'decimal' else '')
                   + '</w:num>' for n, k in enumerate(kinds, 1))
    return XML_HEAD + f'<w:numbering {W_NS}>{"".join(abstract)}{nums}</w:numbering>'


def docx_table(rows):
    n = max(len(r) for r in rows)
    w = 9000 // n
    out = []
    for r in rows:
        cells = r + [[] for _ in range(n - len(r))]
        out.append('<w:tr>' + ''.join(f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/></w:tcPr>{"".join(c) or "<w:p/>"}</w:tc>'
                                      for c in cells) + '</w:tr>')
    grid = f'<w:gridCol w:w="{w}"/>' * n
    return (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(out)}</w:tbl>')


class DocxBody(HTMLParser):
    """Turns sanitised article HTML into WordprocessingML: headings, paragraphs, nested lists, bold, italic,
    links and tables. Inline-CSS graphics degrade to their text (labels and values), which stays readable."""
    HEAD = {'h1': 'Heading1', 'h2': 'Heading1', 'h3': 'Heading2', 'h4': 'Heading3'}
    BLOCK = ('p', 'div', 'blockquote', 'figure', 'figcaption')

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.links, self.nums, self.lists = [], [], [], []
        self.para, self.tbl, self.cell, self.href = None, None, None, None
        self.b = self.i = self.small = 0

    def _sink(self):
        return self.cell if self.cell is not None else self.out

    def _open(self, style=None, num=None):
        self._close()
        self.para = {'style': style, 'num': num, 'runs': [], 'text': False}

    def _close(self):
        p, self.para = self.para, None
        if not p or not p['text']:
            return
        ppr = f'<w:pStyle w:val="{p["style"]}"/>' if p['style'] else ''
        if p['num']:
            ppr += f'<w:numPr><w:ilvl w:val="{p["num"][1]}"/><w:numId w:val="{p["num"][0]}"/></w:numPr>'
        self._sink().append(f'<w:p><w:pPr>{ppr}</w:pPr>{"".join(p["runs"])}</w:p>')

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK:
            if not (self.para and not self.para['text']):  # keep <li><p>.. and <td><div>.. as one paragraph
                self._open('Quote' if tag == 'blockquote' else None)
        elif tag in self.HEAD:
            self._open(self.HEAD[tag])
        elif tag in ('ul', 'ol'):
            self._close()
            self.nums.append('decimal' if tag == 'ol' else 'bullet')
            self.lists.append(len(self.nums))
        elif tag == 'li':
            self._open('ListParagraph', (self.lists[-1], min(len(self.lists) - 1, 2)) if self.lists else None)
        elif tag == 'br':
            if self.para:
                self.para['runs'].append('<w:r><w:br/></w:r>')
        elif tag in ('strong', 'b'):
            self.b += 1
        elif tag in ('em', 'i'):
            self.i += 1
        elif tag == 'small':
            self.small += 1
        elif tag == 'a':
            href = dict(attrs).get('href') or ''
            if re.match(r'(https?://|mailto:)', href, re.I):
                self.links.append(href)
                self.href = f'rIdL{len(self.links)}'
        elif tag == 'table' and self.tbl is None:
            self._close()
            self.tbl = []
        elif tag == 'tr' and self.tbl is not None:
            self._close()
            self.tbl.append([])
        elif tag in ('td', 'th') and self.tbl:
            self._close()
            self.cell = []
            self.tbl[-1].append(self.cell)
            if tag == 'th':
                self.b += 1

    def handle_endtag(self, tag):
        if tag in self.BLOCK or tag in self.HEAD or tag == 'li':
            self._close()
        elif tag in ('ul', 'ol'):
            self._close()
            if self.lists:
                self.lists.pop()
        elif tag in ('strong', 'b'):
            self.b = max(0, self.b - 1)
        elif tag in ('em', 'i'):
            self.i = max(0, self.i - 1)
        elif tag == 'small':
            self.small = max(0, self.small - 1)
        elif tag == 'a':
            self.href = None
        elif tag in ('td', 'th') and self.cell is not None:
            self._close()
            self.cell = None
            if tag == 'th':
                self.b = max(0, self.b - 1)
        elif tag == 'table' and self.tbl is not None:
            self._close()
            rows, self.tbl = [r for r in self.tbl if r], None
            if rows:
                self.out += [docx_table(rows), '<w:p><w:pPr><w:spacing w:after="0"/></w:pPr></w:p>']

    def handle_data(self, d):
        t = re.sub(r'\s+', ' ', d)
        if not t.strip() and not (self.para and self.para['text']):
            return
        if self.para is None:
            self._open()
        if not self.para['text']:
            t = t.lstrip()
        rpr = (('<w:rStyle w:val="Hyperlink"/>' if self.href else '') + ('<w:b/>' if self.b else '')
               + ('<w:i/>' if self.i else '') + ('<w:sz w:val="18"/>' if self.small else ''))
        run = f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{xt(t)}</w:t></w:r>'
        self.para['runs'].append(f'<w:hyperlink r:id="{self.href}">{run}</w:hyperlink>' if self.href else run)
        self.para['text'] = True


def image_size(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m == 0xFF or m == 0x01 or 0xD0 <= m <= 0xD8:
            i += 1 if m == 0xFF else 2
            continue
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7:i + 9], 'big'), int.from_bytes(data[i + 5:i + 7], 'big')
        i += 2 + int.from_bytes(data[i + 2:i + 4], 'big')
    return None


def write_docx(path, title, excerpt, content, img_data=None, img_kind=None, alt=''):
    body = DocxBody()
    body.feed(content)
    body.close()
    body._close()
    parts = [f'<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t xml:space="preserve">{xt(title)}</w:t></w:r></w:p>']
    if excerpt:
        parts.append(f'<w:p><w:pPr><w:pStyle w:val="Subtitle"/></w:pPr><w:r><w:t xml:space="preserve">{xt(excerpt)}</w:t></w:r></w:p>')
    rels = [('rIdS', 'styles', 'styles.xml'), ('rIdN', 'numbering', 'numbering.xml')]
    size = image_size(img_data) if img_data else None
    if size and size[0] and size[1]:
        cx = 5760720  # 6.3 inches: fits A4 and Letter text width
        cy = cx * size[1] // size[0]
        rels.append(('rIdImg', 'image', f'media/image1.{img_kind}'))
        parts.append(
            f'<w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="1" name="Featured image" descr="{xt(alt)}"/><wp:cNvGraphicFramePr>'
            '<a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic>'
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr>'
            '<pic:cNvPr id="1" name="featured"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdImg"/>'
            f'<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/>'
            '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic>'
            '</wp:inline></w:drawing></w:r></w:p>')
    parts += body.out
    lang = CFG['site'].get('language') or 'en-GB'
    letter = lang.lower() in ('en-us', 'en-ca', 'es-mx')
    pg = '<w:pgSz w:w="12240" w:h="15840"/>' if letter else '<w:pgSz w:w="11906" w:h="16838"/>'
    mar = 1440 if letter else 1134
    sect = (f'<w:sectPr>{pg}<w:pgMar w:top="{mar}" w:right="{mar}" w:bottom="{mar}" w:left="{mar}" '
            'w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>')
    document = XML_HEAD + f'<w:document {W_NS}><w:body>{"".join(parts)}{sect}</w:body></w:document>'
    doc_rels = (XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + ''.join(f'<Relationship Id="{i}" Type="{OFFICE_REL}/{t}" Target="{xt(tg)}"/>' for i, t, tg in rels)
                + ''.join(f'<Relationship Id="rIdL{n}" Type="{OFFICE_REL}/hyperlink" Target="{xt(u)}" TargetMode="External"/>'
                          for n, u in enumerate(body.links, 1))
                + '</Relationships>')
    types = (XML_HEAD + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="xml" ContentType="application/xml"/>'
             '<Default Extension="jpeg" ContentType="image/jpeg"/><Default Extension="png" ContentType="image/png"/>'
             '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
             '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
             '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
    root_rels = (XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rId1" Type="{OFFICE_REL}/officeDocument" Target="word/document.xml"/>'
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
                 'Target="docProps/core.xml"/></Relationships>')
    core = (XML_HEAD + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{xt(title)}</dc:title><dc:creator>{xt(CFG["site"].get("name") or "")}</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{iso()}</dcterms:created></cp:coreProperties>')
    tmp = path + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', types)
        z.writestr('_rels/.rels', root_rels)
        z.writestr('docProps/core.xml', core)
        z.writestr('word/document.xml', document)
        z.writestr('word/styles.xml', docx_styles(lang))
        z.writestr('word/numbering.xml', docx_numbering(body.nums))
        z.writestr('word/_rels/document.xml.rels', doc_rels)
        if size:
            z.writestr(f'word/media/image1.{img_kind}', img_data)
    os.replace(tmp, path)


# ---------------------------------------------------------------- publisher: local files (.docx or .html)
def publish_local(m, kind):
    out = CFG['publisher']['output_dir']
    os.makedirs(out, exist_ok=True)
    slug = safe_slug(m.get('slug'), m.get('title'))
    title, excerpt = plain(m['title']), plain(manifest_text(m, 'excerpt'))
    content = clean_html(manifest_text(m, 'content'))
    img = m.get('image') or {}
    data, img_kind = image_bytes(img)
    if kind == 'docx':
        target = os.path.join(out, slug + '.docx')
        write_docx(target, title, excerpt, content, data, img_kind, plain(img.get('alt_text')))
    else:
        target = os.path.join(out, slug + '.html')
        with open(target, 'w', encoding='utf8') as f:
            f.write(content)
        if data:
            with open(os.path.join(out, f"{slug}.{'png' if img_kind == 'png' else 'jpg'}"), 'wb') as f:
                f.write(data)
    status = post_status()
    rec = {k: v for k, v in m.items() if k not in ('content', 'update_post_id')}
    rec['tags'] = list(CFG['publisher']['wordpress'].get('always_tags', [])) + list(m.get('tags', []))
    rec.update({'title': title, 'slug': slug, 'published_utc': iso(), 'status': status, 'file': target})
    with open(os.path.join(out, slug + '.json'), 'w', encoding='utf8') as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    return {'ok': True, 'id': slug, 'status': status, 'link': target}


def publish_cmd(a):
    try:
        m = json.load(open(run_file(a.terms[0]), encoding='utf8'))
        kind = CFG['publisher']['type']
        res = publish_wordpress(m) if kind == 'wordpress' else publish_local(m, 'docx' if kind == 'docx' else 'html')
    except Refused as e:
        res = {'ok': False, 'error': f'refused: {e}'}
    print(json.dumps(res))
    if not res['ok']:
        sys.exit(1)


# ---------------------------------------------------------------- finish
def fkey(f):
    return tuple(str(f.get(k, '')).strip().lower() for k in ('subject', 'attribute', 'value'))


def finish(a):
    c, st, res = CFG['cache'], store(), []
    try:
        newp = os.path.join(RUN, 'cache_research_new.json')
        mine = json.load(open(newp if os.path.exists(newp) else os.path.join(RUN, 'cache_research.json'), encoding='utf8'))
        theirs = jload(st, 'cache_research', {})
        cands = {}
        for x in theirs.get('candidates', []) + mine.get('candidates', []):
            k = x.get('id')
            if not k:
                continue
            if k not in cands or age_min(x.get('built_utc')) < age_min(cands[k].get('built_utc')) or x.get('status') == 'used':
                cands[k] = {**cands.get(k, {}), **x}
        if a.candidate and a.candidate in cands:
            cands[a.candidate].update({'status': 'used', 'used_utc': iso(), 'post_id': a.post_id, 'post_url': a.post_url})
        keep = [x for x in cands.values()
                if (x.get('status') == 'used' and age_min(x.get('used_utc')) <= c['used_candidate_ttl_min'])
                or (x.get('status') != 'used' and age_min(x.get('built_utc')) <= c['open_candidate_ttl_min'])]
        keep.sort(key=lambda x: (x.get('status') == 'used', -float(x.get('score') or 0)))
        doc = {'updated_utc': iso(), 'news_checked_until_utc': mine.get('news_checked_until_utc') or theirs.get('news_checked_until_utc'),
               'performance': mine.get('performance') or theirs.get('performance') or {}, 'candidates': keep[:c['max_candidates']]}
        st.put('cache_research', json.dumps(doc, ensure_ascii=False))
        res.append(f"research cache: {len(doc['candidates'])} candidates kept")
    except Exception as e:  # noqa
        res.append(f'research cache NOT updated: {e}')
    try:
        newp = os.path.join(RUN, 'facts_new.json')
        new = json.load(open(newp, encoding='utf8')) if os.path.exists(newp) else []
        new = new.get('facts', []) if isinstance(new, dict) else new
        theirs = jload(st, 'cache_facts', {})
        facts = {}
        for f in theirs.get('facts', []) + new:
            if f.get('verdict', 'SUPPORTED') != 'SUPPORTED' or not f.get('subject'):
                continue
            f.setdefault('verified_utc', iso())
            k = fkey(f)
            if k not in facts or age_min(f['verified_utc']) < age_min(facts[k]['verified_utc']):
                facts[k] = f
        keep = [f for f in facts.values()
                if age_min(f['verified_utc']) <= (c['volatile_ttl_min'] if f.get('volatility') == 'volatile' else c['stable_ttl_min'])]
        keep.sort(key=lambda f: age_min(f['verified_utc']))
        st.put('cache_facts', json.dumps({'updated_utc': iso(), 'facts': keep[:c['max_facts']]}, ensure_ascii=False))
        res.append(f"fact cache: {len(new)} new facts offered, {min(len(keep), c['max_facts'])} kept")
    except Exception as e:  # noqa
        res.append(f'fact cache NOT updated: {e}')
    try:
        if a.candidate:
            cl = load_claims(st)
            for x in cl:
                if x.get('id') == a.candidate:
                    x.update({'status': 'published', 'post_id': a.post_id, 'post_url': a.post_url, 'published_utc': iso()})
            save_claims(st, cl)
            res.append('claim marked published')
    except Exception as e:  # noqa
        res.append(f'claim not updated: {e}')
    print('\n'.join(res))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['setup', 'claim', 'recent', 'media', 'media-index', 'publish', 'finish'])
    ap.add_argument('terms', nargs='*')
    ap.add_argument('--config')
    ap.add_argument('--topic', help='setup only: the subject area to cover in this run (overrides topic.description)')
    ap.add_argument('--candidate')
    ap.add_argument('--post-id')
    ap.add_argument('--post-url')
    ap.add_argument('--minutes', type=int)
    a = ap.parse_intermixed_args()  # options and free words may appear in any order
    CFG = load_config(a.config)
    RUN = os.environ.get('TW_RUN') or CFG['run_dir']
    try:
        {'setup': setup, 'claim': claim_cmd, 'recent': recent_cmd, 'media': media_cmd, 'media-index': media_index_cmd,
         'publish': publish_cmd, 'finish': finish}[a.cmd](a)
    except Refused as e:
        print(f'FATAL: {e}')
        sys.exit(2)
