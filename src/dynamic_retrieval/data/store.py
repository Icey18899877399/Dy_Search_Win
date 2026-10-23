"""Read-only archive adaptation and point-in-time SQLite views (standard library only)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import zlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

FORMAT = 'dynamic-retrieval-index-v1'


def utc_iso(value: str) -> str:
    """Require an explicit timezone; never guess archive local time or midnight."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Timestamp must be a timezone-aware ISO string')
    try:
        dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Invalid ISO timestamp: {value!r}') from exc
    if dt.tzinfo is None:
        raise ValueError('Timestamp has no timezone')
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def canonical_url(value: str) -> str:
    """Strip only known tracking keys/fragment; preserve meaningful path and query."""
    if not isinstance(value, str):
        return ''
    try:
        p = urlsplit(value.strip())
        if p.scheme.lower() not in ('https', 'http') or not p.hostname or p.username or p.password:
            return ''
        host = p.hostname.lower()
        if ':' in host:
            host = '[' + host + ']'
        port = p.port
        if port and not ((p.scheme.lower() == 'https' and port == 443) or (p.scheme.lower() == 'http' and port == 80)):
            host += ':' + str(port)
        tracking = {'gclid','fbclid','dclid','msclkid','mc_cid','mc_eid'}
        query = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in tracking]
        return urlunsplit((p.scheme.lower(), host, p.path or '/', urlencode(query), ''))
    except ValueError:
        return ''


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _id(*values):
    return hashlib.sha256(_json(values).encode('utf-8')).hexdigest()


def _source(article, url):
    name = article.get('source')
    if isinstance(name, dict):
        name = name.get('name') or name.get('id')
    if isinstance(name, str) and name.strip():
        name = re.sub(r'\s+', ' ', name.strip()).casefold()
        return 'publisher:' + name
    return 'domain:' + (urlsplit(url).hostname or '').lower()


def _date(value, field, counts):
    if not value:
        counts['missing_' + field] += 1
        return None
    try:
        return utc_iso(value)
    except ValueError:
        counts['invalid_' + field] += 1
        return None


def _articles(value, counts):
    """Known list containers only; never descend into arbitrary market/label fields."""
    if isinstance(value, list):
        for article in value:
            if isinstance(article, dict):
                yield article
            else:
                counts['invalid_article_records'] += 1
    elif isinstance(value, dict):
        for key in ('articles', 'newsapi_articles', 'google_news_articles'):
            if key in value:
                yield from _articles(value[key], counts)
    elif value is not None:
        counts['invalid_article_containers'] += 1


def _schema(connection):
    connection.executescript('''
    CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE tasks(id TEXT PRIMARY KEY,market_id TEXT NOT NULL,event_id TEXT NOT NULL,
      question TEXT NOT NULL,description TEXT NOT NULL,outcomes TEXT NOT NULL,
      observed_at TEXT NOT NULL,metadata_quality TEXT NOT NULL,source_file TEXT NOT NULL);
    CREATE INDEX task_cutoff ON tasks(market_id,observed_at);
    CREATE TABLE bodies(content_hash TEXT PRIMARY KEY,payload BLOB NOT NULL);
    CREATE TABLE documents(id TEXT PRIMARY KEY,canonical_url TEXT NOT NULL,source_id TEXT NOT NULL,
      provider TEXT NOT NULL,title TEXT NOT NULL,has_text INTEGER NOT NULL,published_at TEXT NOT NULL,
      observed_at TEXT NOT NULL,content_hash TEXT NOT NULL,event_id TEXT NOT NULL,
      source_file TEXT NOT NULL,scrape_status TEXT NOT NULL);
    CREATE INDEX document_cutoff ON documents(event_id,canonical_url,observed_at,published_at);
    CREATE TABLE labels(id TEXT PRIMARY KEY,market_id TEXT NOT NULL,observed_at TEXT NOT NULL,payload TEXT NOT NULL);
    CREATE INDEX label_market ON labels(market_id,observed_at);
    ''')


def _owned_database(path, root):
    if not path.exists():
        return
    try:
        old = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            meta = dict(old.execute('SELECT key,value FROM meta'))
        finally:
            old.close()
        if meta.get('format') != FORMAT or meta.get('data_root') != str(root):
            raise ValueError('Output database is unrelated or belongs to another source root')
    except sqlite3.Error as exc:
        raise ValueError('Refusing to replace an unrelated/non-index database') from exc


def _ingest(connection, obj, rel, counts):
    if not isinstance(obj, dict):
        counts['unrecognized_files'] += 1
        return 'unrecognized'
    # Labels remain in a separate table even if their file was placed in market/raw_news.
    if 'resolved_markets' in obj:
        rows = obj['resolved_markets']
        if not isinstance(rows, list):
            counts['invalid_label_containers'] += 1
            return 'labels_invalid'
        for row in rows:
            if not isinstance(row, dict) or not row.get('market_id'):
                counts['invalid_label_records'] += 1
                continue
            observed = _date(obj.get('recorded_at') or row.get('recorded_at'), 'label_observed_at', counts)
            if not observed:
                continue
            payload = dict(row, observed_at=observed, source_file=rel,
                           is_proxy=True, label_quality='archive_proxy_not_verified_outcome')
            stable = {k:v for k,v in payload.items() if k != 'source_file'}
            connection.execute('INSERT OR IGNORE INTO labels VALUES(?,?,?,?)',
                               (_id(stable), str(row['market_id']), observed, _json(payload)))
        return 'labels'
    events = obj.get('events')
    if not isinstance(events, list):
        counts['unrecognized_files'] += 1
        return 'unrecognized'
    if any(part.casefold() == 'ground_truth' for part in Path(rel).parts):
        counts['ground_truth_nonlabel_files_excluded'] += 1
        return 'ground_truth_excluded'
    has_full = False
    has_articles = False
    for event in events:
        if not isinstance(event, dict) or not event.get('event_id'):
            counts['invalid_event_records'] += 1
            continue
        eid = str(event['event_id'])
        markets = event.get('markets', [])
        if not isinstance(markets, list):
            counts['invalid_market_containers'] += 1
            markets = []
        for market in markets:
            if not isinstance(market, dict) or not market.get('market_id') or not market.get('question'):
                counts['invalid_market_records'] += 1
                continue
            # Do not let records with resolution fields become task definitions.
            if 'resolve_type' in market or 'final_prices' in market:
                counts['label_like_markets_excluded'] += 1
                continue
            outcomes = market.get('outcomes')
            if isinstance(outcomes, str):
                try: outcomes = json.loads(outcomes)
                except (ValueError, TypeError): outcomes = None
            explicit_outcomes = isinstance(outcomes, list)
            full = explicit_outcomes and 'description' in market
            has_full = has_full or full
            nonbinary = explicit_outcomes and (len(outcomes) != 2 or {str(o).casefold() for o in outcomes} != {'yes','no'})
            if nonbinary:
                counts['nonbinary_markets_excluded'] += 1
            observed = _date((obj.get('collected_at') if full else obj.get('scraped_at'))
                             or obj.get('collected_at') or obj.get('scraped_at'), 'task_observed_at', counts)
            if not observed:
                continue
            quality = ('full_nonbinary_excluded' if nonbinary else 'full_metadata' if full
                       else 'partial_explicit_binary' if explicit_outcomes else 'partial_inferred_binary')
            row = dict(market_id=str(market['market_id']),event_id=eid,
                       question=str(market['question']),description=str(market.get('description') or '') if full else '',
                       outcomes=outcomes if explicit_outcomes else ['Yes','No'],observed_at=observed,metadata_quality=quality)
            connection.execute('INSERT OR IGNORE INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',
                               (_id(row),row['market_id'],eid,row['question'],row['description'],_json(row['outcomes']),observed,quality,rel))
            counts['task_records_seen'] += 1
        containers = [event[k] for k in ('articles','news') if k in event]
        for container in containers:
            has_articles = True
            for article in _articles(container, counts):
                counts['article_records_seen'] += 1
                url = canonical_url(article.get('resolved_url') or article.get('url'))
                if not url:
                    counts['invalid_article_urls'] += 1
                    continue
                published = _date(article.get('published_at'), 'published_at', counts)
                # A scraped body only becomes available at its body's batch time.
                body_key = next((key for key in ('full_text','text') if isinstance(article.get(key),str) and article[key].strip()),None)
                text = article[body_key].strip() if body_key else ''
                observed_value = obj.get('scraped_at') if body_key else (obj.get('scraped_at') or obj.get('collected_at'))
                observed = _date(observed_value, 'document_observed_at', counts)
                if not published or not observed:
                    continue
                if published > observed:
                    counts['published_after_observation'] += 1
                status = str(article.get('scrape_status') or ('success' if text else 'metadata_only'))
                if not text:
                    counts['empty_text_records'] += 1
                if text and ('fail' in status.casefold() or 'error' in status.casefold()):
                    counts['failed_status_with_text'] += 1
                content_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
                if text and not connection.execute('SELECT 1 FROM bodies WHERE content_hash=?',(content_hash,)).fetchone():
                    connection.execute('INSERT INTO bodies VALUES(?,?)',(content_hash,zlib.compress(text.encode('utf-8'))))
                row = dict(canonical_url=url, source_id=_source(article,url),provider=str(article.get('provider') or ''),
                           title=str(article.get('title') or ''),text=text,published_at=published,observed_at=observed,
                           content_hash=content_hash,event_id=eid,scrape_status=status)
                connection.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                                   (_id(row),url,row['source_id'],row['provider'],row['title'],int(bool(text)),published,observed,content_hash,eid,rel,status))
    return ('metadata+' if has_full else 'partial+') + ('articles' if has_articles else 'no_articles')


def build_index(data_root: Path, db_path: Path) -> dict:
    """Atomically rebuild an owned index; inspect all JSON files one file at a time.

    Raw archives are never modified. Source read/parse/schema/date errors are counted;
    output filesystem/SQLite failures abort and preserve the previous database.
    """
    root, db = Path(data_root).resolve(), Path(db_path).resolve()
    if not root.is_dir():
        raise ValueError('Data root is not a directory')
    if db == root or root in db.parents:
        raise ValueError('Output must be outside the read-only source tree')
    if db.name.casefold() == 'audit.json':
        raise ValueError('audit.json is reserved for the index audit, not the database')
    _owned_database(db, root)
    db.parent.mkdir(parents=True, exist_ok=True)
    audit_path = db.parent / 'audit.json'
    if audit_path.exists():
        try:
            if json.loads(audit_path.read_text(encoding='utf-8')).get('format') != FORMAT:
                raise ValueError('Refusing to overwrite an unrelated audit.json')
        except (ValueError, AttributeError) as exc:
            raise ValueError('Refusing to overwrite an unrelated audit.json') from exc
    fd, name = tempfile.mkstemp(prefix=db.name + '.',suffix='.building',dir=db.parent)
    os.close(fd)
    temp = Path(name)
    audit_tmp = None
    connection = None
    counts = Counter({k:0 for k in ('parse_errors','unrecognized_files','missing_published_at','invalid_published_at')})
    manifest = []
    schemas = Counter()
    try:
        connection = sqlite3.connect(temp)
        connection.execute('PRAGMA journal_mode=DELETE')
        connection.execute('PRAGMA cache_size=-16384')
        _schema(connection)
        connection.execute('BEGIN')
        connection.executemany('INSERT INTO meta VALUES(?,?)',[('format',FORMAT),('data_root',str(root))])
        for path in sorted(root.rglob('*.json')):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            entry = {'path':rel,'size_bytes':path.stat().st_size}
            digest = hashlib.sha256()
            counts['files'] += 1
            counts['source_bytes'] += entry['size_bytes']
            try:
                with path.open('rb') as source:
                    for block in iter(lambda:source.read(1024*1024),b''):
                        digest.update(block)
                entry['sha256'] = digest.hexdigest()
                with path.open('r',encoding='utf-8-sig') as source:
                    obj = json.load(source)
            except OSError as exc:
                counts['read_errors'] += 1
                entry.update(schema='read_error',error=str(exc)[:300])
            except (json.JSONDecodeError, UnicodeError) as exc:
                counts['parse_errors'] += 1
                entry.update(schema='parse_error',error=str(exc)[:300])
            else:
                before = counts.copy()
                entry['schema'] = _ingest(connection,obj,rel,counts)
                entry['counters'] = dict(counts-before)
                del obj
            schemas[entry['schema']] += 1
            manifest.append(entry)
        for table in ('tasks','documents','labels'):
            counts[table] = connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
        counts['unique_markets'] = connection.execute('SELECT COUNT(DISTINCT market_id) FROM tasks').fetchone()[0]
        counts['body_versions'] = connection.execute("SELECT COUNT(*) FROM documents WHERE has_text=1").fetchone()[0]
        counts['unique_bodies'] = connection.execute('SELECT COUNT(*) FROM bodies').fetchone()[0]
        counts['compressed_body_bytes'] = connection.execute('SELECT COALESCE(SUM(length(payload)),0) FROM bodies').fetchone()[0]
        counts['unique_event_urls'] = connection.execute("SELECT COUNT(*) FROM (SELECT DISTINCT event_id,canonical_url FROM documents WHERE has_text=1)").fetchone()[0]
        audit = {'format':FORMAT,'data_root':str(root),'counts':dict(counts),'schemas':dict(schemas),
                 'source_read_failures':counts['read_errors'],
                 'coverage_status':'partial_source_read' if counts['read_errors'] else 'all_enumerated_json_read',
                 'source_manifest':manifest,'time_policy':'UTC; body observed_at=batch scraped_at; both published_at and observed_at <= cutoff',
                 'label_policy':'Separate archive proxies; never exposed through tasks/documents',
                 'limitations':['Source timestamp accuracy is not independently verified.',
                    'Only full_text/text bodies enter document queries; snippets/descriptions are not body substitutes.',
                    'Publisher names normalize case/whitespace only; aliases are not silently merged.',
                    'Publication intervals represent observed samples, not complete publisher output.']}
        connection.execute('INSERT INTO meta VALUES(?,?)',('audit',_json(audit)))
        connection.commit()
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('Index integrity check failed')
        connection.close(); connection = None
        fd, audit_name = tempfile.mkstemp(prefix='audit.',suffix='.building',dir=db.parent)
        os.close(fd); audit_tmp = Path(audit_name)
        audit_tmp.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
        # Publish the small audit first. Keep its previous bytes on the same volume
        # so failure of the database's atomic replacement can restore the old pair.
        # Failure publishing audit therefore never changes the database.
        previous_audit = None
        retain_recovery = False
        try:
            if audit_path.exists():
                fd, previous_name = tempfile.mkstemp(prefix='audit.',suffix='.previous',dir=db.parent)
                previous_audit = Path(previous_name)
                with os.fdopen(fd,'wb') as backup:
                    backup.write(audit_path.read_bytes())
            os.replace(audit_tmp,audit_path)
            try:
                os.replace(temp,db)
            except BaseException:
                try:
                    if previous_audit is None:
                        audit_path.unlink(missing_ok=True)
                    else:
                        os.replace(previous_audit,audit_path)
                except OSError as recovery_error:
                    retain_recovery = True
                    raise RuntimeError(f'Index publication failed; audit rollback failed; prior audit retained at {previous_audit}') from recovery_error
                raise
        finally:
            if previous_audit is not None and not retain_recovery:
                previous_audit.unlink(missing_ok=True)
        return audit
    finally:
        if connection is not None:
            connection.close()
        temp.unlink(missing_ok=True)
        Path(str(temp)+'-journal').unlink(missing_ok=True)
        if audit_tmp is not None:
            audit_tmp.unlink(missing_ok=True)


class Store:
    """Read-only forecasting views; labels require an explicit separate method call."""
    def __init__(self, db_path: Path):
        self.path = Path(db_path).resolve()
        self.connection = sqlite3.connect(self.path.as_uri() + '?mode=ro',uri=True)
        self.connection.row_factory = sqlite3.Row
        try:
            value = self.connection.execute("SELECT value FROM meta WHERE key='format'").fetchone()
            if value is None or value[0] != FORMAT:
                raise ValueError('Not a dynamic retrieval index')
        except Exception:
            self.connection.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self):
        self.connection.close()

    def tasks(self, cutoff: str) -> list[dict]:
        cutoff = utc_iso(cutoff)
        rows = self.connection.execute('''
          SELECT market_id,event_id,question,description,outcomes,observed_at,metadata_quality,source_file
          FROM (SELECT *,ROW_NUMBER() OVER(PARTITION BY market_id ORDER BY
            (metadata_quality IN ('full_metadata','full_nonbinary_excluded')) DESC,observed_at DESC,id ASC) AS rn
            FROM tasks WHERE observed_at<=?) WHERE rn=1 AND metadata_quality<>'full_nonbinary_excluded' ORDER BY market_id
        ''',(cutoff,))
        result = []
        for row in rows:
            record = dict(row)
            record['outcomes'] = json.loads(record['outcomes'])
            result.append(record)
        return result

    def documents(self, event_id: str, cutoff: str) -> list[dict]:
        cutoff = utc_iso(cutoff)
        rows = self.connection.execute('''
          SELECT selected.id,canonical_url,source_id,provider,title,published_at,observed_at,
                 selected.content_hash,event_id,source_file,scrape_status,bodies.payload AS body_payload
          FROM (SELECT *,ROW_NUMBER() OVER(PARTITION BY event_id,canonical_url
              ORDER BY observed_at DESC,id ASC) AS rn FROM documents
              WHERE event_id=? AND observed_at<=? AND published_at<=? AND has_text=1
                AND lower(scrape_status) NOT LIKE '%fail%' AND lower(scrape_status) NOT LIKE '%error%')
          AS selected JOIN bodies ON bodies.content_hash=selected.content_hash
          WHERE rn=1 ORDER BY published_at,source_id,selected.id
        ''',(str(event_id),cutoff,cutoff))
        result=[]
        for row in rows:
            record=dict(row)
            record['text']=zlib.decompress(record.pop('body_payload')).decode('utf-8')
            result.append(record)
        return result

    def labels(self, market_id: str) -> list[dict]:
        return [json.loads(row['payload']) for row in self.connection.execute(
            'SELECT payload FROM labels WHERE market_id=? ORDER BY observed_at,id',(str(market_id),))]
