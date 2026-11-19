# 作者名单自动补齐脚本（GitHub Actions 运行，Python 3 标准库，无第三方依赖）
# 用法：
#   python scripts/update_authors.py                 # 补最多 400 个后写回 authors.json
#   python scripts/update_authors.py --collect-only  # 只统计缺口，不访问 Steam
#   python scripts/update_authors.py --limit=100 --out=/tmp/a.json
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

APP_ID = '2868840'
MODS = ('https://workshop.apricityx.top/api/workshop/mods'
        f'?appId={APP_ID}&page={{page}}&pageSize=100&sort=popular&days=-1&query=')
HEADERS = {'User-Agent': 'maozhan-authors-bot/1.0'}

args = {}
for a in sys.argv[1:]:
    if a.startswith('--'):
        k, _, v = a[2:].partition('=')
        args[k] = v if v else True

OUT = args.get('out') if isinstance(args.get('out'), str) else 'authors.json'
LIMIT = int(args.get('limit') or 400)
COLLECT_ONLY = bool(args.get('collect-only'))
WORKERS = 4


def get(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def collect_ids():
    ids, page, total_pages, scanned = set(), 1, 1, 0
    while page <= total_pages and page <= 200:
        try:
            data = json.loads(get(MODS.format(page=page)).decode('utf-8'))
        except Exception as e:
            print(f'page {page} failed: {e}, stop')
            break
        total_pages = data.get('totalPages') or 1
        for it in data.get('items') or []:
            scanned += 1
            if it.get('creatorSteamId'):
                ids.add(str(it['creatorSteamId']))
        page += 1
    print(f'scanned {scanned} items, {len(ids)} unique authors, {total_pages} pages')
    return ids


def fetch_profile(steam_id):
    try:
        text = get(f'https://steamcommunity.com/profiles/{steam_id}?xml=1', timeout=15).decode('utf-8', 'ignore')
    except Exception:
        return None
    name = re.search(r'<steamID><!\[CDATA\[(.*?)\]\]></steamID>', text, re.S)
    avatar = re.search(r'<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>', text, re.S)
    if not name:
        return None
    return {'name': name.group(1).strip(), 'avatar': avatar.group(1) if avatar else ''}


def main():
    try:
        with open(OUT, encoding='utf-8') as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    ids = collect_ids()
    missing = [i for i in ids if not existing.get(i, {}).get('name')]
    print(f'existing {len(existing)}, missing {len(missing)}')
    if COLLECT_ONLY:
        print('collect-only, sample:', missing[:5])
        return

    todo = missing[:LIMIT]
    done = {'ok': 0, 'fail': 0}

    def work(sid):
        p = fetch_profile(sid)
        if p:
            existing[sid] = p
            done['ok'] += 1
        else:
            done['fail'] += 1
        time.sleep(0.25)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, todo))

    ordered = {k: existing[k] for k in sorted(existing)}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    print(f"done: +{done['ok']} ok, {done['fail']} failed, total {len(ordered)}")


if __name__ == '__main__':
    main()
