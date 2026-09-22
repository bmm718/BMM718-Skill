#!/usr/bin/env python3
"""离线核验网盘候选完整下载副本。仅标准库，不连接网盘，不移动文件。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys


class VerificationError(ValueError):
    """输入或副本不足以构成完整字节核验证据。"""


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(f"{label} 必须是非空字符串")
    return value


def checked_path(root, relative):
    nonempty(relative, "cache_path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise VerificationError("cache_path 必须是缓存根目录内的相对路径，不能包含 ..")
    candidate = root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise VerificationError("缓存路径不允许软链接")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise VerificationError("缓存路径越出缓存根目录")
    if not stat.S_ISREG(candidate.stat().st_mode):
        raise VerificationError("缓存条目必须是普通文件")
    return candidate


def snapshot(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def hash_complete(root, relative, expected_size):
    path = checked_path(root, relative)
    before = path.stat()
    if before.st_size != expected_size:
        raise VerificationError("缓存大小与清单中的远端大小不符，可能截断或已变化")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or snapshot(before) != snapshot(opened):
            raise VerificationError("缓存文件在打开时发生变化")
        digest = hashlib.sha256()
        byte_count = 0
        while block := stream.read(1024 * 1024):
            digest.update(block)
            byte_count += len(block)
        after = os.fstat(stream.fileno())
    checked_path(root, relative)
    if byte_count != expected_size or snapshot(opened) != snapshot(after) or snapshot(after) != snapshot(path.stat()):
        raise VerificationError("缓存文件在读取期间发生变化")
    return digest.hexdigest(), byte_count


def verify(manifest, cache_root):
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise VerificationError("清单必须使用 schema_version: 1")
    task_id = nonempty(manifest.get("task_id"), "task_id")
    provider = nonempty(manifest.get("provider"), "provider")
    scope = nonempty(manifest.get("scope"), "scope")
    if not isinstance(manifest.get("entries"), list) or not manifest["entries"]:
        raise VerificationError("entries 必须是非空列表")
    supplied_root = Path(cache_root).expanduser()
    if supplied_root.is_symlink():
        raise VerificationError("缓存根目录不能是软链接")
    root = supplied_root.resolve(strict=True)
    if not root.is_dir():
        raise VerificationError("缓存根路径必须是目录")
    ids, cache_paths, groups, records = set(), set(), {}, []
    for index, entry in enumerate(manifest["entries"]):
        if not isinstance(entry, dict):
            raise VerificationError(f"条目 {index} 必须是对象")
        remote_id = nonempty(entry.get("remote_id"), "remote_id")
        remote_path = nonempty(entry.get("remote_path"), "remote_path")
        group_id = nonempty(entry.get("candidate_group"), "candidate_group")
        if remote_id in ids:
            raise VerificationError("同一清单不允许重复 remote_id")
        ids.add(remote_id)
        size = entry.get("size")
        if type(size) is not int or size < 0:
            raise VerificationError("size 必须是非负整数字节数")
        if "revision" not in entry:
            raise VerificationError("必须提供 revision；接口没有版本号时填 null 并说明原因")
        revision = entry["revision"]
        if revision is None:
            nonempty(entry.get("revision_note"), "revision_note")
        else:
            nonempty(revision, "revision")
        fingerprint = entry.get("fingerprint")
        if not isinstance(fingerprint, dict) or fingerprint.get("semantics") != "opaque" or "value" not in fingerprint:
            raise VerificationError("fingerprint 必须含 semantics: opaque 和 value，不用接口指纹判定相同内容")
        if fingerprint["value"] is not None and not isinstance(fingerprint["value"], str):
            raise VerificationError("fingerprint.value 必须是字符串或 null")
        cache_path = nonempty(entry.get("cache_path"), "cache_path")
        canonical = checked_path(root, cache_path).resolve(strict=True)
        if canonical in cache_paths:
            raise VerificationError("不同远端条目必须使用独立缓存路径")
        cache_paths.add(canonical)
        records.append((entry, remote_id, remote_path, group_id, size, revision, cache_path))
        groups.setdefault(group_id, []).append(remote_id)
    if any(len(ids_in_group) < 2 for ids_in_group in groups.values()):
        raise VerificationError("每个候选组至少需要两个远端条目")
    evidence = []
    for entry, remote_id, remote_path, group_id, size, revision, cache_path in records:
        digest, byte_count = hash_complete(root, cache_path, size)
        evidence.append({
            "remote_id": remote_id, "remote_path": remote_path,
            "candidate_group": group_id, "size": size, "revision": revision,
            "revision_note": entry.get("revision_note"), "cache_path": cache_path,
            "sha256": digest, "bytes_read": byte_count,
            "upstream_fingerprint_used_for_equality": False,
        })
    comparisons = []
    for group_id, remote_ids in groups.items():
        hashes = {item["sha256"] for item in evidence if item["candidate_group"] == group_id}
        comparisons.append({"candidate_group": group_id, "remote_ids": remote_ids,
                            "cached_content_equal": len(hashes) == 1,
                            "purpose_review_required": True, "move_authorized": False})
    return {
        "schema_version": 1, "task_id": task_id, "provider": provider, "scope": scope,
        "status": "verified_cached_bytes", "algorithm": "SHA-256",
        "verification_level": "offline_download_copy_only",
        "live_remote_identity_verified": False, "live_download_verified": False,
        "live_move_verified": False, "permanent_delete_performed": False,
        "limitations": ["大小来自输入清单；本脚本不证明清单真实、下载链路完整或副本属于对应远端文件。",
                        "相同内容只证明本地副本逐字节哈希一致，用途确认及真实网盘移动需要独立授权与回读。"],
        "entries": evidence, "groups": comparisons,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="候选清单 JSON 文件")
    parser.add_argument("--cache-root", required=True, help="完整下载副本的根目录")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        result = verify(manifest, args.cache_root)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc), "verification_level": "none"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
