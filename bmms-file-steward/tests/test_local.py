"""纯合成文件的行为回归；不读取用户文件，不依赖账号或外部包。"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'local_files.py'
SPEC = importlib.util.spec_from_file_location('local_files', SCRIPT)
local = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(local)


class LocalFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='local-', dir=os.environ.get('FILE_STEWARD_TEST_TMP'))
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'disk'
        self.root.mkdir()
        self.config = {'version': 1, 'roots': {'disk': str(self.root)}, 'exclude': {'disk': ['排除']}}

    def write(self, rel, content=b'example'):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def ref(self, rel):
        return {'root': 'disk', 'path': rel}

    def move(self, source, target, kind='file', keeper=None):
        d = {'source': self.ref(source), 'target': self.ref(target), 'kind': kind, 'reason': '合成样本已确认用途'}
        if keeper:
            d['keeper'] = self.ref(keeper)
        return d

    def plan(self, moves, **kwargs):
        return local.make_plan(local.scan(self.config), {'moves': moves, **kwargs})

    def apply(self, plan):
        return local.apply(plan, plan['approval_sha256'], self.base / 'receipt.json')

    def test_complete_md5_large_file(self):
        content = b'a' * (1024 * 1024) + b'final-tail'
        self.write('完整读取.bin', content)
        record = local.scan(self.config)['files'][0]
        self.assertEqual(record['size'], len(content))
        self.assertEqual(record['md5'], hashlib.md5(content).hexdigest())
        self.assertEqual(record['sha256'], hashlib.sha256(content).hexdigest())

    def test_same_content_different_purpose_retained_and_pending_stay(self):
        first = self.write('工作/模板.txt')
        second = self.write('学习/模板.txt')
        uncertain = self.write('存疑/不知道用途.bin', b'unknown')
        inventory = local.scan(self.config)
        self.assertEqual(len(inventory['duplicates']), 1)
        retained = [{'file': self.ref('学习/模板.txt'), 'reason': '另一独立用途'}]
        pending = [{'file': self.ref('存疑/不知道用途.bin'), 'question': '用途待确认'}]
        plan = local.make_plan(inventory, {'moves': [], 'retained': retained, 'pending': pending})
        receipt = self.apply(plan)
        self.assertEqual(receipt['plan']['retained'], retained)
        self.assertEqual(receipt['plan']['pending'], pending)
        self.assertEqual([p.read_bytes() for p in (first, second, uncertain)], [b'example', b'example', b'unknown'])
        self.assertTrue(local.verify(receipt)['verified'])

    def test_cross_directory_quarantine_verify_restore_no_permanent_delete(self):
        original = self.write('正式/原件.txt')
        duplicate = self.write('下载/副本.txt')
        plan = self.plan([self.move('下载/副本.txt', '待删除/下载/副本.txt', 'quarantine', '正式/原件.txt')])
        receipt = self.apply(plan)
        isolated = self.root / '待删除/下载/副本.txt'
        self.assertFalse(duplicate.exists())
        self.assertEqual(original.read_bytes(), isolated.read_bytes())
        self.assertTrue(local.verify(receipt)['verified'])
        restore_receipt = local.restore(receipt, plan['approval_sha256'], self.base / 'restore.json')
        self.assertTrue(local.verify(restore_receipt)['verified'])
        self.assertEqual(duplicate.read_bytes(), b'example')
        self.assertEqual(original.read_bytes(), b'example')
        self.assertFalse(isolated.exists())

    def test_scope_and_exclusions_untouched(self):
        outside = self.base / 'outside.txt'
        outside.write_bytes(b'outside')
        excluded = self.write('排除/private.txt', b'excluded')
        normal = self.write('收件/a.txt')
        inventory = local.scan(self.config)
        self.assertEqual([f['path'] for f in inventory['files']], ['收件/a.txt'])
        for target in ('../outside.txt', '排除/private.txt', str(outside)):
            with self.subTest(target=target), self.assertRaises(ValueError):
                local.make_plan(inventory, {'moves': [self.move('收件/a.txt', target)]})
        receipt = self.apply(local.make_plan(inventory, {'moves': [self.move('收件/a.txt', '资料/a.txt')]}))
        self.assertTrue(local.verify(receipt)['verified'])
        self.assertEqual(excluded.read_bytes(), b'excluded')
        self.assertEqual(outside.read_bytes(), b'outside')
        self.assertFalse(normal.exists())

    def test_symlink_source_and_target_parent_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'source.txt').write_bytes(b'outside')
        (self.root / '链接').symlink_to(outside, target_is_directory=True)
        (self.root / '链接文件').symlink_to(outside / 'source.txt')
        self.write('a.txt')
        inventory = local.scan(self.config)
        self.assertEqual([f['path'] for f in inventory['files']], ['a.txt'])
        self.assertEqual(len(inventory['issues']), 2)
        with self.assertRaises(ValueError):
            local.make_plan(inventory, {'moves': [self.move('a.txt', '链接/a.txt')]})
        self.assertFalse((outside / 'a.txt').exists())
        self.assertEqual((outside / 'source.txt').read_bytes(), b'outside')

    def test_stale_inventory_and_stale_plan_rejected(self):
        source = self.write('a.txt')
        inventory = local.scan(self.config)
        source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            local.make_plan(inventory, {'moves': [self.move('a.txt', '资料/a.txt')]})
        plan = self.plan([self.move('a.txt', '资料/a.txt')])
        source.write_bytes(b'changed-again')
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertEqual(source.read_bytes(), b'changed-again')
        self.assertFalse((self.root / '资料/a.txt').exists())

    def test_target_conflict_does_not_overwrite(self):
        self.write('a.txt')
        plan = self.plan([self.move('a.txt', '资料/a.txt')])
        target = self.write('资料/a.txt', b'new arrival')
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertEqual(target.read_bytes(), b'new arrival')
        self.assertEqual((self.root / 'a.txt').read_bytes(), b'example')

    def test_keeper_changed_blocks_quarantine(self):
        keeper = self.write('keep.txt')
        duplicate = self.write('duplicate.txt')
        plan = self.plan([self.move('duplicate.txt', '待删除/duplicate.txt', 'quarantine', 'keep.txt')])
        keeper.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertEqual(duplicate.read_bytes(), b'example')
        self.assertFalse((self.root / '待删除/duplicate.txt').exists())

    def test_keeper_cannot_itself_be_moved_in_batch(self):
        self.write('keep.txt')
        self.write('duplicate.txt')
        with self.assertRaises(ValueError):
            self.plan([self.move('duplicate.txt', '待删除/duplicate.txt', 'quarantine', 'keep.txt'), self.move('keep.txt', 'moved.txt')])

    def test_wrong_approval_and_modified_plan_rejected(self):
        source = self.write('a.txt')
        plan = self.plan([self.move('a.txt', '资料/a.txt')])
        with self.assertRaises(ValueError):
            local.apply(plan, 'wrong', self.base / 'receipt.json')
        plan['moves'][0]['reason'] = 'changed after review'
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertTrue(source.exists())

    def test_failure_intent_receipt_preserves_source_and_refuses_restore(self):
        source = self.write('a.txt')
        self.write('parent-is-file', b'obstacle')
        plan = self.plan([self.move('a.txt', 'parent-is-file/target.txt')])
        with self.assertRaises(OSError):
            self.apply(plan)
        receipt = local.read(self.base / 'receipt.json')
        self.assertEqual(receipt['status'], 'interrupted')
        self.assertEqual(receipt['operations'][0]['status'], 'intent')
        self.assertEqual(source.read_bytes(), b'example')
        self.assertFalse(local.verify(receipt)['verified'])
        with self.assertRaises(ValueError):
            local.restore(receipt, plan['approval_sha256'], self.base / 'restore.json')

    def test_copy_fallback_and_restore_conflict(self):
        source = self.write('a.txt', b'cross-device-content')
        plan = self.plan([self.move('a.txt', '资料/a.txt')])
        with mock.patch.object(local.os, 'link', side_effect=OSError('synthetic EXDEV')):
            receipt = self.apply(plan)
        self.assertTrue(local.verify(receipt)['verified'])
        source.write_bytes(b'new arrival')
        with self.assertRaises(ValueError):
            local.restore(receipt, plan['approval_sha256'], self.base / 'restore.json')
        self.assertEqual(source.read_bytes(), b'new arrival')
        self.assertEqual((self.root / '资料/a.txt').read_bytes(), b'cross-device-content')

    def test_copy_fallback_target_race_never_overwrites(self):
        source = self.write('a.txt', b'original')
        plan = self.plan([self.move('a.txt', '资料/a.txt')])
        def concurrent_target(src, dst):
            Path(dst).write_bytes(b'concurrent arrival')
            raise OSError('synthetic EXDEV after concurrent arrival')
        with mock.patch.object(local.os, 'link', side_effect=concurrent_target):
            with self.assertRaises(OSError):
                self.apply(plan)
        self.assertEqual(source.read_bytes(), b'original')
        self.assertEqual((self.root / '资料/a.txt').read_bytes(), b'concurrent arrival')
        receipt = local.read(self.base / 'receipt.json')
        self.assertEqual(receipt['status'], 'interrupted')
        self.assertEqual(receipt['operations'][0]['status'], 'intent')
        self.assertFalse(local.verify(receipt)['verified'])

    def test_new_file_placement_and_search(self):
        self.write('收件/项目 清单.txt')
        first = self.plan([self.move('收件/项目 清单.txt', '工作/项目 清单.txt')])
        self.apply(first)
        self.write('收件/项目 笔记.txt', b'new')
        second = self.plan([self.move('收件/项目 笔记.txt', '工作/项目 笔记.txt')])
        local.apply(second, second['approval_sha256'], self.base / 'receipt2.json')
        inventory = local.scan(self.config)
        self.assertEqual([f['path'] for f in local.search(inventory, '工作 笔记')], ['工作/项目 笔记.txt'])
        self.assertEqual(local.search(inventory, '不存在'), [])

    def test_empty_home_cli_full_lifecycle(self):
        self.write('收件/sample.txt')
        state = self.base / 'state'
        state.mkdir()
        empty_home = self.base / 'empty-home'
        empty_home.mkdir()
        env = os.environ.copy()
        env['HOME'] = str(empty_home)
        env.pop('PYTHONPATH', None)
        scope = state / 'scope.json'
        decisions = state / 'decisions.json'
        scope.write_text(json.dumps(self.config))
        decisions.write_text(json.dumps({'moves': [self.move('收件/sample.txt', '资料/sample.txt')]}))
        def cli(*args):
            result = subprocess.run([sys.executable, '-I', str(SCRIPT), *map(str, args)], env=env, cwd=empty_home, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        inventory = state / 'inventory.json'
        plan_path = state / 'plan.json'
        receipt_path = state / 'receipt.json'
        cli('scan', '--scope', scope, '--out', inventory)
        plan = cli('plan', '--inventory', inventory, '--decisions', decisions, '--out', plan_path)
        cli('apply', '--plan', plan_path, '--approved', plan['approval_sha256'], '--receipt', receipt_path)
        self.assertTrue(cli('verify', '--receipt', receipt_path)['verified'])
        cli('restore', '--receipt', receipt_path, '--approved', plan['approval_sha256'], '--out', state / 'restored.json')
        self.assertEqual((self.root / '收件/sample.txt').read_bytes(), b'example')
        self.assertEqual(list(empty_home.iterdir()), [])

    def test_restore_refuses_forged_operation_outside_approved_moves(self):
        self.write('a.txt')
        innocent = self.write('unrelated.txt', b'unrelated')
        plan = self.plan([self.move('a.txt', '资料/a.txt')])
        receipt = self.apply(plan)
        # 模拟回执文件被改动：原计划与批准摘要不变，操作行指向另一文件。
        receipt = json.loads(json.dumps(receipt))
        forged = receipt['operations'][0]['move']
        forged['source'] = self.ref('unrelated-moved.txt')
        forged['target'] = self.ref('unrelated.txt')
        forged['expected'] = local.fingerprint(innocent)
        with self.assertRaises(ValueError):
            local.restore(receipt, plan['approval_sha256'], self.base / 'restore.json')
        self.assertEqual(innocent.read_bytes(), b'unrelated')
        self.assertFalse((self.root / 'unrelated-moved.txt').exists())

    def test_target_storage_root_replacement_stops_apply(self):
        self.write('a.txt')
        target_root = self.base / 'other-drive'
        target_root.mkdir()
        self.config['roots']['external'] = str(target_root)
        move = self.move('a.txt', 'a.txt')
        move['target']['root'] = 'external'
        plan = self.plan([move])
        target_root.rename(self.base / 'old-drive')
        target_root.mkdir()
        with self.assertRaises(ValueError):
            self.apply(plan)
        self.assertEqual((self.root / 'a.txt').read_bytes(), b'example')
        self.assertFalse((target_root / 'a.txt').exists())

    def test_verify_detects_missing_keeper_after_quarantine(self):
        keeper = self.write('keep.txt')
        self.write('duplicate.txt')
        plan = self.plan([self.move('duplicate.txt', '待删除/duplicate.txt', 'quarantine', 'keep.txt')])
        receipt = self.apply(plan)
        keeper.unlink()
        self.assertFalse(local.verify(receipt)['verified'])
        self.assertEqual((self.root / '待删除/duplicate.txt').read_bytes(), b'example')

    def test_retained_and_pending_cannot_also_be_moved(self):
        self.write('a.txt')
        for decision_key in ('retained', 'pending'):
            with self.subTest(decision_key=decision_key), self.assertRaises(ValueError):
                self.plan([self.move('a.txt', '资料/a.txt')], **{decision_key: [{'file': self.ref('a.txt'), 'reason': '保留原位或等待确认'}]})

    def test_retained_and_pending_path_aliases_cannot_be_moved(self):
        source = self.write('资料/a.txt')
        for decision_key in ('retained', 'pending'):
            for alias in ('./资料/a.txt', '资料/./a.txt', '资料//a.txt'):
                with self.subTest(decision_key=decision_key, alias=alias), self.assertRaises(ValueError):
                    self.plan([self.move('资料/a.txt', '目标/a.txt')],
                              **{decision_key: [{'file': self.ref(alias), 'reason': '保留原位或等待确认'}]})
        self.assertEqual(source.read_bytes(), b'example')
        self.assertFalse((self.root / '目标').exists())

    def test_package_and_nested_package_roots_are_rejected(self):
        for index, suffix in enumerate(('.app', '.photoslibrary', '.bundle', '.APP')):
            package = self.root / ('example-' + str(index) + suffix)
            nested = package / '内部' / '子目录'
            nested.mkdir(parents=True)
            source = nested / '原始资料.txt'
            source.write_bytes(b'package data')
            for selected_root in (package, nested):
                with self.subTest(suffix=suffix, root=selected_root), self.assertRaises(ValueError):
                    local.scan({'version': 1, 'roots': {'disk': str(selected_root)}})
            self.assertEqual(source.read_bytes(), b'package data')

    def test_retained_and_pending_case_aliases_cannot_be_moved(self):
        source = self.write('a.txt')
        alias = self.root / 'A.txt'
        if not alias.exists() or not alias.samefile(source):
            self.skipTest('当前测试文件系统区分大小写，无大小写别名')
        for decision_key in ('retained', 'pending'):
            with self.subTest(decision_key=decision_key), self.assertRaises(ValueError):
                self.plan([self.move('a.txt', '目标/a.txt')],
                          **{decision_key: [{'file': self.ref('A.txt'), 'reason': '保留原位或等待确认'}]})
        self.assertEqual(source.read_bytes(), b'example')
        self.assertFalse((self.root / '目标').exists())

    def test_retained_and_pending_hardlinks_conservatively_block_moves(self):
        source = self.write('a.txt')
        alias = self.root / 'protected-link.txt'
        os.link(source, alias)
        for decision_key in ('retained', 'pending'):
            with self.subTest(decision_key=decision_key), self.assertRaises(ValueError):
                self.plan([self.move('a.txt', '目标/a.txt')],
                          **{decision_key: [{'file': self.ref('protected-link.txt'), 'reason': '保守保护同一文件的硬链接'}]})
        self.assertEqual(source.read_bytes(), b'example')
        self.assertEqual(alias.read_bytes(), b'example')
        self.assertTrue(source.samefile(alias))
        self.assertFalse((self.root / '目标').exists())

    def test_package_subdirectories_remain_skipped(self):
        self.write('资料/a.txt')
        for suffix in ('.app', '.photoslibrary', '.bundle'):
            self.write('example' + suffix + '/内部/原始资料.txt', b'package data')
        inventory = local.scan(self.config)
        self.assertEqual([entry['path'] for entry in inventory['files']], ['资料/a.txt'])
        self.assertEqual(len(inventory['issues']), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
