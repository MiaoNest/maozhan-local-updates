# 作者名单自动补齐脚本（GitHub Actions 运行，Python 3 标准库，无第三方依赖）
# 用法：
#   python scripts/update_authors.py                 # 补最多 1200 个后写回 authors.json
#   python scripts/update_authors.py --collect-only  # 只统计缺口，不访问 Steam
#   python scripts/update_authors.py --limit=100 --out=/tmp/a.json
import json
import html
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
LIMIT = int(args.get('limit') or 1200)
COLLECT_ONLY = bool(args.get('collect-only'))
WORKERS = 3
DELAY = 0.5


def get(url, timeout=20, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def collect_ids():
    ids, page, total_pages, scanned = set(), 1, 1, 0
    fails = 0
    while page <= total_pages and page <= 200:
        try:
            data = json.loads(get(MODS.format(page=page)).decode('utf-8'))
        except Exception as e:
            fails += 1
            print(f'page {page} failed: {e} (skip, {fails} fails)')
            if fails >= 12:
                print('too many page failures, stop')
                break
            page += 1
            continue
        total_pages = data.get('totalPages') or 1
        for it in data.get('items') or []:
            scanned += 1
            if it.get('creatorSteamId') and str(it['creatorSteamId']) != '0':
                ids.add(str(it['creatorSteamId']))
        page += 1
    print(f'scanned {scanned} items, {len(ids)} unique authors, {total_pages} pages, {fails} page fails')
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
    nm = html.unescape(name.group(1)).strip()
    # 未开通 Steam 社区资料的账号（steamID 为空）直接丢弃，避免写入空名条目
    if not nm:
        return None
    av = (avatar.group(1).strip() if avatar else '')
    if av and not re.fullmatch(r'https://[^/]+/[0-9a-f]{40}_full\.jpg', av):
        av = ''
    return {'name': nm, 'avatar': av}


def main():
    try:
        with open(OUT, encoding='utf-8') as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    # 归一化历史数据：反转义 HTML 实体、去掉首尾空白（空名条目稍后统一丢弃）
    existing = {k: {'name': html.unescape(v.get('name') or '').strip(), 'avatar': v.get('avatar') or ''}
                for k, v in existing.items()}
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
        time.sleep(DELAY)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, todo))

    ordered = {k: existing[k] for k in sorted(existing) if (existing[k].get('name') or '').strip()}
    dropped = len(existing) - len(ordered)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')
    print(f"done: +{done['ok']} ok, {done['fail']} failed, dropped {dropped} empty, total {len(ordered)}")


if __name__ == '__main__':
    main()
