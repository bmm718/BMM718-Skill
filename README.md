# BMMSkill

**让人类少操点心的开源 Agent Skills。**

把生活里反复操心的小事，做成能交给 Agent 的技能。这里是白毛毛的公开技能集合。

Practical agent skills for everyday life.

## 从文件整理开始

文件越存越多，不记得放哪，又怕删错？第一枚 Skill「文件管家」帮你按用途分类、核对重复，再继续帮你归位和查找。

| 你遇到的事 | 文件管家会怎样处理 |
|---|---|
| 文件夹越来越乱 | 先核实整理范围，结合实际用途梳理分类 |
| 不同目录里可能存了重复文件 | 完整读取核对；同内容但用途不同的副本继续保留 |
| 有些文件不知道是什么 | 先读取能确认的内容，拿不准的集中列给你看 |
| 确定有些副本多余 | 先移入待删除，记录去向，完成回读并支持恢复 |
| 新文件又进来了，或想找旧资料 | 沿用分类规则归位，查找后核对当前文件位置 |

安装不会自动开始扫盘。先选一个你明确要整理的文件夹，把范围和需要保留的用途告诉 Agent 即可。

## 安装

需要能使用本地 Skill 和文件工具的 Agent。执行文件工具需要 Python 3.9+，无需第三方 Python 包。下面的安装方式需要 Node.js/npm 和网络：

macOS / Linux（Bash）：

```sh
npx -y skills add bmm718/bmmskill --skill bmms-file-steward -g
```

Windows PowerShell：

```powershell
npx -y skills add bmm718/bmmskill --skill bmms-file-steward -g
```

按安装器提示选择你使用的 Agent，然后刷新或重开会话。

Skills CLI 默认向 skills.sh 发送安装统计，包含仓库、Skill、Agent 等安装信息，用于目录与榜单。安装统计不代表实际持续使用。若想退出，可在 macOS/Linux 命令前加 `DISABLE_TELEMETRY=1`；PowerShell 先执行 `$env:DISABLE_TELEMETRY = "1"`。已有的 `DO_NOT_TRACK` 设置也会被安装器尊重。[安装器官方说明](https://skills.sh/docs/cli)

文件管家当前公开版不采集使用数据，也不会向作者发送回访记录。本地文件整理无需联网。

也可以从 [Releases](https://github.com/bmm718/bmmskill/releases) 下载发布包，按[文件管家说明](bmms-file-steward/README.md)手动安装完整目录。

## 第一次可以这样说

> 用文件管家整理我指定的资料文件夹，排除备份目录。照片全集和精选都保留。先核对重复，拿不准的集中给我看，确定多余的先放待删除。

之后可以直接说：

> 把刚放进收件文件夹的资料按之前的规则归位。

> 帮我找以前存的调色课程，只查找，别移动。

## 当前技能

| Skill | 用途 | 说明 |
|---|---|---|
| `bmms-file-steward` 文件管家 | 文件整理、完整去重核验、隔离与恢复、日常归位和查找 | [使用说明](bmms-file-steward/README.md) · [本地样例](bmms-file-steward/references/local.md) · [网盘接入](bmms-file-steward/references/cloud.md) |

## 先了解边界

- 默认不永久删除，不按时间自动清空待删除；隔离文件本身不会释放空间。
- 支持 Python 能正常访问的普通文件。软链接、应用资料库和复杂跨盘元数据有明确限制，详见本地样例。
- 网盘需要你自己的账号及当前 Agent 可用的接口。名为 MD5 的字段不能直接当标准 MD5；离线副本核验通过也不代表真实网盘已接入或移动成功。
- 本地合成样本、离线网盘证据和安装验证已有覆盖；实体移动硬盘/U盘、Windows、各家真实网盘操作尚未全部实测。
- 内容相同仍需判断用途，重要取舍由你决定。没有授权，不上传文件、发送资料或扩展整理范围。

## 更新与反馈

更新前保留自己的分类规则和操作回执；运行记录存放在用户目录，不在 Skill 安装目录。更新安装后重新核对文件现状，不执行过期计划。

遇到问题可以[提交 Issue](https://github.com/bmm718/bmmskill/issues)。请说明操作系统、使用的 Agent、Python 版本、执行到哪一步及去掉隐私的错误信息；使用合成样例复现，不要上传文件原件、凭据或完整磁盘清单。

版本和变化说明见 [Releases](https://github.com/bmm718/bmmskill/releases)。

## 教程与许可

- [B站：白毛毛莫慢待](https://space.bilibili.com/602247575)
- [小红书：白思路白毛毛](https://xhslink.com/m/7EIvfBx9bhJ)

本仓库代码与文档采用 [MIT 许可](LICENSE)。第三方 Agent、网盘服务及安装工具各自遵循其许可、账号与配额要求。
