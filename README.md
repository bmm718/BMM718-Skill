# BMM718-Skill

**简称 BMMS。让人类少操点心的开源 Agent Skills 集合。**

把生活里反复操心的小事，做成能交给 Agent 的独立技能。你可以安装整个集合，也可以只选需要的一项。

Practical agent skills for everyday life.

[能力一览](#能力一览) · [安装](#安装) · [第一次使用](#第一次使用) · [更新与反馈](#更新与反馈)

## 能力一览

目前公开 **1 个技能**。每个技能都有独立的使用说明、工具和安装入口。

| 你想完成的事 | Skill | 使用说明 |
|---|---|---|
| 按用途整理文件、核对重复、隔离多余副本，继续归位和查找 | `bmms-file-steward` · [文件管家](skills/bmms-file-steward/README.md) | [打开文件管家](skills/bmms-file-steward/README.md) |

本页是整个集合的入口。各项技能的具体用法、依赖和限制在各自页面中说明。

## 安装

需要支持本地 Skills 的 Agent。以下命令适用于 macOS、Linux 终端及 Windows PowerShell，需要 Node.js/npm 和网络。当前已完成 Codex 安装验证；其他宿主按安装器提示选择，具体能力取决于宿主提供的工具与权限。

### 安装整个集合

```sh
npx -y skills add bmm718/BMM718-Skill --skill '*' -g
```

会安装仓库中当前公开的全部技能。目前只有文件管家；以后新增技能，可重新执行安装并按提示更新。

### 只安装文件管家

```sh
npx -y skills add bmm718/BMM718-Skill --skill bmms-file-steward -g
```

按安装器提示选择 Agent，安装后刷新或重开会话。执行文件管家的本地工具需要 Python 3.9+，无第三方 Python 包依赖。

### 手动下载

从 [Releases](https://github.com/bmm718/BMM718-Skill/releases) 下载发布包。解压后，技能在 `skills/` 下；将需要的完整技能目录按其[安装说明](skills/bmms-file-steward/README.md#安装和使用)导入 Agent。

Skills CLI 默认向 skills.sh 发送包含仓库、Skill、Agent 等信息的安装统计，用于目录与榜单；安装次数不代表持续使用。退出方式：macOS/Linux 在安装命令前加 `DISABLE_TELEMETRY=1`，PowerShell 先执行 `$env:DISABLE_TELEMETRY = "1"`。已有 `DO_NOT_TRACK` 设置也会被尊重，详见[安装器说明](https://skills.sh/docs/cli)。当前公开技能不向作者发送使用或回访记录。

## 第一次使用

安装文件管家后，对 Agent 说：

> 用文件管家整理我指定的资料文件夹，排除备份目录。先核对重复，照片全集和精选都保留，确定多余的先放待删除。

安装不会自动开始扫盘或移动文件。具体流程、可恢复操作和网盘边界见[文件管家使用说明](skills/bmms-file-steward/README.md)。

## 集合与单个技能

```text
BMM718-Skill（BMMS）
├── README.md                   集合介绍与安装入口
├── LICENSE                     开源许可
└── skills/
    └── bmms-file-steward/       文件管家
        ├── README.md           单项使用说明
        ├── SKILL.md            Agent 执行指令
        ├── scripts/            文件工具
        ├── references/         用法与边界
        └── tests/              合成样本验证
```

## 更新与反馈

版本说明与下载见 [Releases](https://github.com/bmm718/BMM718-Skill/releases)。更新前保留自己的分类规则和操作回执；这些运行资料保存在用户目录，不在 Skill 安装目录。更新后重新核对文件现状，不执行过期计划。

遇到问题可以[提交 Issue](https://github.com/bmm718/BMM718-Skill/issues)。请注明技能名称、操作系统、Agent、Python 版本及去掉隐私的错误信息。使用合成样例复现，不上传文件原件、凭据或完整磁盘清单。

## 作者与教程

- [B站：白毛毛莫慢待](https://space.bilibili.com/602247575)
- [小红书：白思路白毛毛](https://xhslink.com/m/7EIvfBx9bhJ)

## 许可证

本仓库代码与文档采用 [MIT 许可](LICENSE)。第三方 Agent、网盘服务和安装工具各自遵循其许可、账号与配额要求。
