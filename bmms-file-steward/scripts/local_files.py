#!/usr/bin/env python3
"""只读盘点、显式计划、可回读移动和恢复。Python 3.9+，仅标准库。"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import uuid
from datetime import datetime, timezone

VERSION = 1


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data, *, new=False):
    path = Path(path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    if new:
        with path.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
    else:
        tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with tmp.open('x', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f'拒绝软链接路径：{path}')
    return path


def fingerprint(path):
    path = no_links(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f'不是普通文件：{path}')
    md5 = hashlib.md5(usedforsecurity=False)
    sha = hashlib.sha256()
    total = 0
    with path.open('rb') as f:
        opened = os.fstat(f.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f'读取前文件被替换：{path}')
        for block in iter(lambda: f.read(1024 * 1024), b''):
            md5.update(block)
            sha.update(block)
            total += len(block)
        after = os.fstat(f.fileno())
    end = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if signature(before) != signature(after) or signature(after) != signature(end) or total != end.st_size:
        raise ValueError(f'读取期间文件变化：{path}')
    return dict(size=total, md5=md5.hexdigest(), sha256=sha.hexdigest(),
                mtime_ns=end.st_mtime_ns, device=end.st_dev, inode=end.st_ino)


def same_content(a, b):
    return all(a[k] == b[k] for k in ('size', 'md5', 'sha256'))


def relative(raw):
    p = Path(raw)
    if not raw or p.is_absolute() or '..' in p.parts or p == Path('.'):
        raise ValueError(f'需要范围内相对文件路径：{raw}')
    return p


def scope_load(config):
    if config.get('version') != VERSION or not config.get('roots'):
        raise ValueError('scope需要version: 1及roots')
    roots, identities = {}, {}
    for key, value in config['roots'].items():
        root = no_links(Path(value).expanduser())
        if any(part.suffix.lower() in ('.app', '.photoslibrary', '.bundle')
               for part in (root, *root.parents)):
            raise ValueError('扫描根目录不能是应用或资料库包及其内部目录')
        if not root.is_dir():
            raise ValueError(f'存储位置未挂载或目录不可读：{key}')
        roots[key] = str(root)
        info = root.stat()
        identities[key] = dict(device=info.st_dev, inode=info.st_ino)
        if config.get('identities') is not None and config['identities'].get(key) != identities[key]:
            raise ValueError('存储根目录身份变化，请重新识别挂载并盘点')
    values = list(roots.values())
    for i, a in enumerate(values):
        for b in values[i + 1:]:
            if Path(a).is_relative_to(b) or Path(b).is_relative_to(a):
                raise ValueError('扫描根目录不能重叠')
    excludes = config.get('exclude', {})
    for key, items in excludes.items():
        if key not in roots:
            raise ValueError('exclude引用未知root')
        for item in items:
            relative(item)
    return dict(version=VERSION, roots=roots, exclude=excludes, identities=identities)


def scoped(scope, ref):
    if ref.get('root') not in scope['roots']:
        raise ValueError('路径引用未知root')
    rel = relative(ref['path'])
    for item in scope['exclude'].get(ref['root'], []):
        if rel == Path(item) or rel.is_relative_to(item):
            raise ValueError(f'命中排除项：{rel}')
    root = no_links(scope['roots'][ref['root']])
    if not root.is_dir():
        raise ValueError('存储根目录不存在；请重新核实挂载')
    info = root.stat()
    if scope['identities'][ref['root']] != dict(device=info.st_dev, inode=info.st_ino):
        raise ValueError('存储根目录已被替换，请重新盘点')
    return no_links(root / rel)


def key(ref):
    return (ref['root'], relative(ref['path']).as_posix())


def scan(config):
    scope = scope_load(config)
    files, issues = [], []
    for root_id, base in scope['roots'].items():
        def walk_error(e):
            issues.append(dict(root=root_id, path=str(e.filename), reason=str(e)))
        for folder, dirs, names in os.walk(base, followlinks=False, onerror=walk_error):
            for name in list(dirs):
                p = Path(folder) / name
                ref = dict(root=root_id, path=p.relative_to(base).as_posix())
                try:
                    scoped(scope, ref)
                    if p.suffix.lower() in ('.app', '.photoslibrary', '.bundle'):
                        raise ValueError('应用或资料库包：交给所属应用处理')
                except ValueError as e:
                    dirs.remove(name)
                    issues.append(dict(**ref, reason=str(e)))
            for name in sorted(names):
                p = Path(folder) / name
                ref = dict(root=root_id, path=p.relative_to(base).as_posix())
                try:
                    files.append(dict(**ref, **fingerprint(scoped(scope, ref))))
                except (OSError, ValueError) as e:
                    issues.append(dict(**ref, reason=str(e)))
    groups = {}
    for f in files:
        groups.setdefault((f['size'], f['md5']), []).append(dict(root=f['root'], path=f['path']))
    return dict(version=VERSION, created=now(), scope=scope, files=files, issues=issues,
                duplicates=[g for g in groups.values() if len(g) > 1],
                note='完整MD5仅证明内容候选；用途由用户意图和目录角色判断。隔离前另核SHA256。')


def make_plan(inventory, decisions):
    scope = scope_load(inventory['scope'])
    records = {key(f): f for f in inventory['files']}
    moves = []
    sources, targets, keepers = set(), set(), set()
    protected, protected_identities = set(), set()
    for label in ('retained', 'pending'):
        for item in decisions.get(label, []):
            ref = item.get('file', item)
            path = scoped(scope, ref)
            protected.add(key(ref))
            try:
                info = path.stat()
            except FileNotFoundError:
                continue
            protected_identities.add((info.st_dev, info.st_ino))
    for d in decisions.get('moves', []):
        src, dst = d['source'], d['target']
        source, target = scoped(scope, src), scoped(scope, dst)
        if key(src) not in records:
            raise ValueError('移动源不在盘点证据中')
        if not d.get('reason', '').strip() or d.get('kind') not in ('file', 'quarantine', 'review'):
            raise ValueError('每项须有用途理由及kind: file/quarantine/review')
        if source == target or key(src) in sources or key(dst) in targets or target.exists():
            raise ValueError('重复移动源、目标冲突或目标已存在')
        record = records[key(src)]
        current = fingerprint(source)
        if (current['device'], current['inode']) in protected_identities:
            raise ValueError('移动源与保留或待判断项指向同一文件')
        if current != {k: record[k] for k in current}:
            raise ValueError('盘点后文件变化，请重新盘点')
        move = dict(source=src, target=dst, kind=d['kind'], reason=d['reason'], expected=current)
        if d['kind'] == 'quarantine':
            keeper = d['keeper']
            if key(keeper) == key(src) or key(keeper) not in records:
                raise ValueError('隔离必须指定盘点中的另一份保留件')
            kept = fingerprint(scoped(scope, keeper))
            if not same_content(current, kept):
                raise ValueError('保留件与隔离件完整内容不一致')
            if '待删除' not in relative(dst['path']).parts:
                raise ValueError('隔离目标必须位于待删除目录下')
            move.update(keeper=keeper, keeper_expected=kept)
            keepers.add(key(keeper))
        sources.add(key(src))
        targets.add(key(dst))
        moves.append(move)
    if sources & targets or sources & keepers:
        raise ValueError('本批不能移动保留件或串联移动')
    if sources & protected or targets & protected:
        raise ValueError('保留或待判断项与移动清单冲突')
    plan = dict(version=VERSION, created=now(), scope=scope, moves=moves,
                retained=decisions.get('retained', []), pending=decisions.get('pending', []))
    plan['approval_sha256'] = digest(plan)
    return plan


def check_digest(plan):
    body = {k: v for k, v in plan.items() if k != 'approval_sha256'}
    if digest(body) != plan['approval_sha256']:
        raise ValueError('计划已改变，重新生成并审阅')


def check_plan(plan):
    check_digest(plan)
    scope_load(plan['scope'])
    for move in plan['moves']:
        source = scoped(plan['scope'], move['source'])
        target = scoped(plan['scope'], move['target'])
        if target.exists():
            raise ValueError(f'目标已存在：{target}')
        if fingerprint(source) != move['expected']:
            raise ValueError(f'源文件已变化：{source}')
        if 'keeper' in move:
            kept = fingerprint(scoped(plan['scope'], move['keeper']))
            if kept != move['keeper_expected'] or not same_content(kept, move['expected']):
                raise ValueError('保留件已变化')


def move_file(source, target, expected):
    """普通文件复制到排他创建的新文件，完整回读后才移除源；不覆盖目标。"""
    no_links(source)
    no_links(target)
    if fingerprint(source) != expected:
        raise ValueError('执行前源文件变化')
    target.parent.mkdir(parents=True, exist_ok=True)
    no_links(target)
    # 优先硬链接保留全部元数据；不支持硬链接或跨设备时使用普通文件复制。
    try:
        os.link(source, target)
    except FileExistsError:
        raise ValueError('目标已存在，未覆盖')
    except OSError:
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst, 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, target, follow_symlinks=False)
    if not same_content(fingerprint(target), expected) or not same_content(fingerprint(source), expected):
        raise ValueError('复制后内容变化，保留两端供核对')
    source.unlink()
    if source.exists() or not same_content(fingerprint(target), expected):
        raise ValueError('移动后回读不符')


def apply(plan, approved, receipt_path):
    if approved != plan['approval_sha256']:
        raise ValueError('执行需要已审阅计划的完整指纹')
    check_plan(plan)
    receipt = dict(version=VERSION, created=now(), plan=plan, status='running', operations=[])
    save(receipt_path, receipt, new=True)
    try:
        for move in plan['moves']:
            op = dict(move=move, status='intent')
            receipt['operations'].append(op)
            save(receipt_path, receipt)
            if 'keeper' in move and fingerprint(scoped(plan['scope'], move['keeper'])) != move['keeper_expected']:
                raise ValueError('保留件变化，停止执行')
            move_file(scoped(plan['scope'], move['source']), scoped(plan['scope'], move['target']), move['expected'])
            op['status'] = 'moved'
            save(receipt_path, receipt)
        receipt['status'] = 'complete'
    except (OSError, ValueError) as e:
        receipt['status'] = 'interrupted'
        receipt['error'] = str(e)
        raise
    finally:
        save(receipt_path, receipt)
    return receipt


def check_receipt(receipt):
    check_digest(receipt['plan'])
    operations = receipt['operations']
    planned = receipt['plan']['moves']
    if len(operations) > len(planned) or any(op['move'] != planned[i] for i, op in enumerate(operations)):
        raise ValueError('回执操作不匹配原批准计划，停止执行')


def verify(receipt):
    check_receipt(receipt)
    scope = scope_load(receipt['plan']['scope'])
    results = []
    for op in receipt['operations']:
        m = op['move']
        found = {}
        for label in ('source', 'target', *(['keeper'] if 'keeper' in m else [])):
            try:
                p = scoped(scope, m[label])
                found[label] = 'matching' if same_content(fingerprint(p), m['expected']) else 'changed'
            except FileNotFoundError:
                found[label] = 'absent'
            except (OSError, ValueError):
                found[label] = 'unreadable'
        results.append(dict(source=m['source'], target=m['target'], recorded=op['status'], **{f'{k}_state':v for k,v in found.items()}))
    good = len(results) == len(receipt['plan']['moves']) and all(r['source_state'] == 'absent' and r['target_state'] == 'matching' and r.get('keeper_state', 'matching') == 'matching' for r in results)
    return dict(verified=good, items=results, note='源缺席＋目标完整哈希一致才表示移动到位；intent项请先人工核对，不重跑原计划。')


def restore(receipt, approved, output):
    check_receipt(receipt)
    plan = receipt['plan']
    if approved != plan['approval_sha256']:
        raise ValueError('恢复需指定原计划指纹，并获用户恢复授权')
    if receipt.get('status') not in ('complete', 'interrupted') or any(o['status'] != 'moved' for o in receipt['operations']):
        raise ValueError('存在未完成intent；先verify逐项核对，不自动删除任一端')
    reverse = []
    for op in reversed(receipt['operations']):
        m = op['move']
        if scoped(plan['scope'], m['source']).exists():
            raise ValueError('原位置已有文件，恢复不会覆盖')
        f = fingerprint(scoped(plan['scope'], m['target']))
        if not same_content(f, m['expected']):
            raise ValueError('隔离/归位后内容已变化，停止恢复')
        reverse.append(dict(source=m['target'], target=m['source'], kind='file', reason='按原回执恢复', expected=f))
    reverse_plan = dict(version=VERSION, created=now(), scope=plan['scope'], moves=reverse, retained=[], pending=[])
    reverse_plan['approval_sha256'] = digest(reverse_plan)
    return apply(reverse_plan, reverse_plan['approval_sha256'], output)


def search(inventory, query):
    words = query.casefold().split()
    return [f for f in inventory['files'] if all(w in f['path'].casefold() for w in words)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('scan'); p.add_argument('--scope', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('plan'); p.add_argument('--inventory', required=True); p.add_argument('--decisions', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('apply'); p.add_argument('--plan', required=True); p.add_argument('--approved', required=True); p.add_argument('--receipt', required=True)
    p = sub.add_parser('verify'); p.add_argument('--receipt', required=True)
    p = sub.add_parser('restore'); p.add_argument('--receipt', required=True); p.add_argument('--approved', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('search'); p.add_argument('--inventory', required=True); p.add_argument('query')
    args = parser.parse_args()
    try:
        if args.command == 'scan':
            result = scan(read(args.scope)); save(args.out, result, new=True)
            result = dict(files=len(result['files']), duplicates=len(result['duplicates']), issues=len(result['issues']), output=args.out)
        elif args.command == 'plan':
            result = make_plan(read(args.inventory), read(args.decisions)); save(args.out, result, new=True)
        elif args.command == 'apply':
            result = apply(read(args.plan), args.approved, args.receipt)
        elif args.command == 'verify':
            result = verify(read(args.receipt))
        elif args.command == 'restore':
            result = restore(read(args.receipt), args.approved, args.out)
        else:
            result = search(read(args.inventory), args.query)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.command != 'verify' or result['verified'] else 1
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f'停止：{e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
