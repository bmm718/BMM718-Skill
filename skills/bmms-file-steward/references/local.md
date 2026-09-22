# 本地命令与样例

需要 Python 3.9+，仅标准库。以下命令中的脚本路径相对于 Skill 目录。实际操作请使用脚本的真实安装路径，并在 Skill 之外的运行目录创建 demo。用户通常只需向 Agent 说任务，Agent 生成这些运行文件。

不要直接在 Skill 目录执行会生成 demo 的示例。将运行目录设为用户自己的 `~/.bmms/bmms-file-steward/` 或明确指定的位置。下例全部为虚构沙盒，用 `demo` 目录展示完整流程。真实运行时先确定根目录，不照抄示例范围。

## 可直接运行的沙盒

```sh
skill_dir="$HOME/.agents/skills/bmms-file-steward"
mkdir -p "$HOME/.bmms/bmms-file-steward/example"
cd "$HOME/.bmms/bmms-file-steward/example"
mkdir -p demo/disk/资料 demo/disk/收件 demo/disk/精选 demo/state
printf 'synthetic sample\n' > demo/disk/资料/样本.txt
cp demo/disk/资料/样本.txt demo/disk/收件/样本副本.txt
cp demo/disk/资料/样本.txt demo/disk/精选/样本.txt
python3 -c 'import json,pathlib; p=pathlib.Path("demo/disk").resolve(); pathlib.Path("demo/state/scope.json").write_text(json.dumps({"version":1,"roots":{"disk":str(p)},"exclude":{"disk":["保护区"]}},ensure_ascii=False),encoding="utf-8")'
python3 "$skill_dir/scripts/local_files.py" scan --scope demo/state/scope.json --out demo/state/inventory.json
```

在 `demo/state/decisions.json` 写入：

```json
{
  "moves": [{
    "source": {"root": "disk", "path": "收件/样本副本.txt"},
    "target": {"root": "disk", "path": "待删除/本批/样本副本.txt"},
    "kind": "quarantine",
    "keeper": {"root": "disk", "path": "资料/样本.txt"},
    "reason": "用户确认收件中的同用途副本多余，资料主档保留"
  }],
  "retained": [{"root": "disk", "path": "精选/样本.txt", "reason": "精选入口用途不同"}],
  "pending": []
}
```

```sh
python3 "$skill_dir/scripts/local_files.py" plan --inventory demo/state/inventory.json --decisions demo/state/decisions.json --out demo/state/plan.json
python3 -c 'import json; print(json.load(open("demo/state/plan.json"))["approval_sha256"])'
```

审阅清单中的每个源、目标、理由和保留件。`apply --approved` 后接上一步输出的完整指纹，`--plan demo/state/plan.json --receipt demo/state/receipt.json`。Agent 必须先取得覆盖具体动作的授权，不把输出指纹当作批准。

```sh
python3 "$skill_dir/scripts/local_files.py" verify --receipt demo/state/receipt.json
python3 "$skill_dir/scripts/local_files.py" search --inventory demo/state/inventory.json '样本'
```

搜索展示盘点时的路径，移动后重新扫描生成新的盘点文件；不得拿旧路径当现状。示例结束可删除自己生成的整个 `demo` 沙盒；不要把该清理动作套到真实数据。

## 范围和决定格式

- `roots` 是本轮实际读写根目录，可以有多个不同磁盘的非重叠目录。键是用户任务内别名，值是当前机器真实路径。磁盘挂载点/盘符每次核实，范围不延伸到父目录。
- `exclude` 是各根目录下相对路径，排除该文件或整个子树。隐藏文件并非自动安全；扫描系统盘前由 Agent 列明排除。运行记录和下载缓存应位于扫描范围之外。
- `kind: file` 普通归位/重命名，`review` 是已授权物理集中到待确认，`quarantine` 是确认多余且有保留件的隔离。
- `retained`、`pending` 是可阅读的决定记录，不产生移动；每项写具体路径与理由/问题。
- 目标必须不存在，不使用自动覆盖；同名冲突由 Agent 根据用途选新名称并重新生成计划。
- 脚本完整读取所有普通文件；大盘耗时与数据总量相关，不承诺固定速度或一定节省空间。读取失败和排除项记在 `issues`，不能静默忽略。
- 扫描跳过目录软链接和应用/照片资料库包；嵌套挂载与特殊存储先明确边界。扫描普通文件不分析语义，不会独立理解图片、课序或用户用途。
- 支持可被 Python 访问的本地盘、移动盘和U盘。网盘虚拟挂载只有证明完整读取稳定、写入语义和同步状态可验收后才按本地流程处理；默认走网盘分支。

## 中断和恢复

回执先记 `intent`，文件移动回读后记 `moved`；全批结束为 `complete`。对无覆盖复制失败的残留，保留两端，避免误删。

1. 先 `verify --receipt`，检查每项源与目标是否存在、完整内容是否匹配，同时核对保留件。
2. `source=absent,target=matching` 表示该项已到位，即使此前命令丢失响应也不要重做。`intent` 状态不能直接重试整批，须结合完整哈希和原计划逐项确认并保存恢复判断；先保留现场。
3. 两边都存在时不代表可随便删一边；确认复制是否完成、其他程序是否修改后，在具体授权下处理残留。内容不符、挂载变化、缺失或不可读时停止相关项。
4. 全部记录为 `moved` 且当前目标仍匹配，用户要求撤回时，可运行 `restore --receipt 原回执 --approved 原计划指纹 --out 新恢复回执`。这也会逐项回读，原位置已存在则拒绝覆盖。对恢复回执再 `verify`。
5. 半批完成但没有未决 intent 的回执可恢复已完成项；存在 intent 时先人工核对，脚本不猜测该项结果。不要编辑掉意图记录绕过检查。

完整内容与普通文件时间/权限可回读。支持硬链接时保留原文件元数据；跨设备或不支持硬链接时复制再核验。ACL、资源叉和第三方扩展属性不保证跨文件系统保真，依赖这些元数据的文件应留在原位或使用对应原生工具；文件夹、特殊文件和应用数据库不纳入批量移动。操作时关闭会写入这些文件的程序，避免与同步软件同时改动；这不是文件系统事务或备份替代品。
