# agent-skills-ndmf-plugin

NDMF (Non-Destructive Modular Framework) プラグイン開発向けの AI エージェントスキル集です。[skills.sh](https://skills.sh) 経由で配布します。

## インストール

```sh
npx skills add kurotu/agent-skills-ndmf-plugin
```

## スキルの追加方法

`skills/<スキル名>/SKILL.md` を作成してください。`SKILL.md` には最低限 `name` と `description` を含む YAML frontmatter が必要です。

```markdown
---
name: my-skill
description: このスキルが何をするか、いつ使うべきかを記述する
---

# My Skill

エージェントが従うべき手順をここに記述する。
```
