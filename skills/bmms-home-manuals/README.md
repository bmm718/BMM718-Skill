# 全屋说明书（bmms-home-manuals）

把你家每台电器的官方说明书按型号收进一个目录，之后问 AI "这台怎么用""它为什么坏"，它先查说明书、告诉你第几页；说明书没写的，它会明说是推测，再陪你一步一步排。

## 装

把本目录整个放进你的 Agent 的 skills 目录：

- Codex：`~/.codex/skills/bmms-home-manuals/`
- Claude Code：`~/.claude/skills/bmms-home-manuals/`
- WorkBuddy：`~/.workbuddy/skills/bmms-home-manuals/`（所有项目可用）或 `<项目>/.workbuddy/skills/bmms-home-manuals/`（只这个项目）

## 用

在你想放说明书的项目目录里装。装完它会直接问你家有什么家电；要是它没开口，对它说一句：

> 开始记录家电

它会问你家有什么，你答一台它找一台。之后直接问：

> 洗衣机儿童锁怎么开
> 书桌那盏灯为什么一直闪

## 它不做什么

不推荐买什么、不比价、不给链接；不碰电器、不读设备数据；拆机、电路、燃气的事它会让你找售后。

## 要什么样的 Agent

能联网下载文件、能读 PDF、能在你电脑上存文件的。只能聊天的网页版用不了，它记不住你家有什么。
