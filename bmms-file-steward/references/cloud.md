# 网盘：先核实接口，再处理文件

本 Skill 不绑定网盘服务，不内置账号，也不自动替用户安装、登录或申请付费套餐。网盘路径必须先有当前 Agent 能真实调用的连接器、官方 API 或已配置的开源客户端。没有这些能力时，可以处理用户提供的清单和下载副本，但交付应写“离线副本核验”，不能称该网盘已接入或实测完成。脚本只依赖 Python 3.9+ 标准库，无后台、遥测或外发。

## 每次接入先确定什么

沿用用户已明确的存储位置、整理范围、排除项和授权。尚未明确范围时，在递归盘点或下载前确认是全盘还是指定目录；照片备份、应用数据、共享空间等没有进入本次授权的内容保持原样。

读取当前环境可用的连接器说明或 CLI 帮助，逐项确定：列目录是否有分页、如何判断末页、文件的稳定 ID、完整路径、字节大小、版本号、下载能力、服务端移动语义和冲突策略。记录该次使用的工具、版本、账号所属空间的非敏感标识和查询时间；凭据只留在用户自己的连接器或客户端中。不要在计划、日志或清单里放 token、Cookie、签名下载链接。

字段名不能代替字段语义。名为 `md5` 的字段可能经过服务端变换，也可能仅代表分块信息。先查该接口文档和实际响应；无法核实的指纹统一标为 `opaque`。大小加不透明指纹只用于缩小候选，不能写成“已确认重复”。即使文档说明是标准哈希，本流程最终仍读取每个候选的完整内容，用同一个 SHA-256 算法逐组比较。

递归盘点需要走完分页，留存目录、文件计数及失败项。中途失败、权限不可见、配额限制或部分列表均须报告，不能写成全盘已盘清。只在授权范围内下载候选；文件太大、流量或计费超过既定范围时，暂停受影响的下载，继续已能核验的组。

## 可选：用户已有 rclone 时只读接入

[rclone](https://rclone.org/) 是 MIT 许可的独立可选客户端，不包含在本 Skill 中。安装和配置按[官方安装文档](https://rclone.org/install/)及对应[服务商文档](https://rclone.org/overview/)执行。服务商支持、OAuth、第三方限制和目录语义不同；不能因为装了 rclone 就声称任意网盘可用。也不要用别人的远端配置或凭据。

以下 Bash 示例要求用户已经配置一个真实受支持的 remote；将 `myremote` 和路径换成当次已授权范围。命令会联系该网盘，但不修改远端。`lsjson` 清单中的个人路径保存在用户自己的运行目录，不进入 Skill 安装目录。

```bash
rclone version
rclone listremotes
mkdir -p "$HOME/.bmms/bmms-file-steward/cloud-run/cache"
rclone lsjson 'myremote:Documents' --recursive --files-only > "$HOME/.bmms/bmms-file-steward/cloud-run/listing.json"
```

只有进程成功结束，且当前后端枚举完整性得到核对时，才能把清单视为此次可见范围的完整盘点。`lsjson` 的 `ID`、`Size`、`Path` 等字段依后端而异；`ModTime` 不能自行当作不可变版本号。详情见 [lsjson](https://rclone.org/commands/rclone_lsjson/)。不支持稳定 ID 的后端仍可只读盘点；在无法可靠识别移动后对象前，不执行自动云端移动。

单个候选完整下载的可执行例子（目标文件已存在就停止，避免覆盖本地缓存）：

```bash
cache_file="$HOME/.bmms/bmms-file-steward/cloud-run/cache/item-a.bin"
if [ -e "$cache_file" ] || [ -L "$cache_file" ]; then
  printf '%s\n' '缓存目标已存在，请换一个未使用的名称。' >&2
else
  rclone copyto 'myremote:Documents/item-a.bin' "$cache_file" --immutable
fi
```

这只是 [copyto](https://rclone.org/commands/rclone_copyto/) 的只读远端下载示例，须逐项替换来源与缓存名称；重复使用同一路径不能证明两个远端条目都下载过。下载前后再次查询远端 ID、大小、版本，确保没有变化；支持按版本下载时固定版本。没有版本号的接口记录原因、前后元数据与下载时间，保留“并发修改无法完全排除”的限制。不要用此示例上传、`sync` 或执行删除。

## 离线完整字节校验

为每个候选组准备独立下载副本及下列 JSON 清单。`remote_id` 应来自真实接口；`revision` 缺失时显式用 `null`，并提供 `revision_note`。`fingerprint.value` 没有就填 `null`。`cache_path` 相对于本次缓存根目录，不能含 `..` 或软链接。一个清单属于同一任务和服务空间，每个组至少两个条目，ID 与缓存路径都不能重复。

以下是虚构格式样本，示例字节大小必须替换成实际查询值：

```json
{
  "schema_version": 1,
  "task_id": "sample-review",
  "provider": "example-provider:user-space",
  "scope": "Documents；排除 Shared 和 Backups",
  "entries": [
    {
      "candidate_group": "group-001",
      "remote_id": "id-a",
      "remote_path": "/Documents/item-a.bin",
      "size": 12,
      "revision": "version-a",
      "fingerprint": {"semantics": "opaque", "value": "provider-value"},
      "cache_path": "item-a.bin"
    },
    {
      "candidate_group": "group-001",
      "remote_id": "id-b",
      "remote_path": "/Documents/project/item-b.bin",
      "size": 12,
      "revision": null,
      "revision_note": "该接口未提供版本号，已保存下载前后元数据，无法完全排除并发修改。",
      "fingerprint": {"semantics": "opaque", "value": "provider-value"},
      "cache_path": "item-b.bin"
    }
  ]
}
```

在 Skill 安装目录运行；所有运行资料和结果在安装目录之外：

```bash
python3 scripts/cloud_verify.py "$HOME/.bmms/bmms-file-steward/cloud-run/manifest.json" \
  --cache-root "$HOME/.bmms/bmms-file-steward/cloud-run/cache" \
  > "$HOME/.bmms/bmms-file-steward/cloud-run/evidence.json"
```

退出码 0 表示校验过程完成；仍须看每组的 `cached_content_equal`，不同内容属于正常核验结果。退出码 2 表示输入或文件被拒绝，结果为 `status: rejected`。脚本流式读取完整字节、核对大小，并检查读取期间文件是否变化。它不会使用上游指纹判等，不执行云端写入，也不修改副本。不要在其他程序会同步改动缓存目录时运行。

`verified_cached_bytes` 只证明清单所指本地副本的完整读取及哈希比较。清单大小是否真实、下载来源是否正确、真实 API 下载成功、真实云端移动均需另有证据。用户把两个远端 ID 错配到相同内容的副本，脚本无法识别；必须保留实际下载回执及远端元数据关联。

## 从候选到待删除及恢复

1. 哈希相同也先审用途。项目交付副本与日常工作副本可能都要保留；无法判断的统一列入存疑清单，不拆散项目、不自动去重。
2. 把需保留项、拟隔离项、原路径、目标路径、稳定 ID、版本和哈希放在同一份可审阅计划里。用户确认用途与具体动作后才移动，已有明确授权继续沿用。默认目标是同一存储空间内的“待删除”目录；不永久删除，不自动过期清空。
3. 重新查询来源，核对 ID、大小、版本；无版本号时按当前风险重新下载比对。发现变动则停止该条。目标存在同名项时保持两边原样，不覆盖、不自动合并。只有工具能明确保证目标冲突失败，才可执行移动；否则保持计划并说明能力缺口。
4. 先记录恢复所需的原路径与目标位置，再逐项调用已核实的移动接口。接口返回成功仍须用稳定 ID 回读目标位置和来源状态，核对内容元数据；API 不支持服务端移动、ID 会改变或下载代替移动时，应先说明并重新确定可验证方法，不能静默改为上传加删除。
5. 超时或失败先回读源与目标，确认该 ID 当前的位置，禁止盲目重复。能确认已移动的补回执；能确认未移动的才重试；无法确认的保留为待查。
6. 恢复时以记录的 ID 及原路径生成反向移动计划，先检查当前版本和原位置是否已被占用；冲突不覆盖。按照同样的授权、失败回读和逐项验收流程恢复。第三方回收站的保留期不属于本 Skill 的保证。

交付分开列明：离线合成样本验证、真实接口盘点、候选完整下载核验、用途确认、真实移动回读。只列本次实际完成的层级。这里的 Python 工具不构成任何服务商的真实接入认证。
