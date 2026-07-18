# agent-skills-ndmf-plugin

A collection of AI agent skills for NDMF (Non-Destructive Modular Framework) plugin development. Distributed via [skills.sh](https://skills.sh).

## Installation

```sh
npx skills add kurotu/agent-skills-ndmf-plugin
```

## Included Skills

### ndmf-plugin-builder

Helps implement, port, and debug NDMF (`nadena.dev.ndmf`) plugins and passes.
Covers writing Unity Editor passes that non-destructively transform a VRChat
avatar at build time (duplicating materials, rewriting
AnimatorController/animation-clip references, adding or removing components),
pass phase ordering, NDMF Preview (`IRenderFilter`) for a build-free live
preview, and how to test passes.

Details: [skills/ndmf-plugin-builder/SKILL.md](skills/ndmf-plugin-builder/SKILL.md)

## Repository Layout

- `skills/<skill-name>/` — the distributed content. skills.sh recognizes only
  folders that contain a `SKILL.md` as skills.
- `skills/ndmf-plugin-builder-workspace/` — skill development tooling
  (**not distributed**). An evaluation harness for measuring and optimizing
  how reliably `ndmf-plugin-builder`'s description triggers. See
  [skills/ndmf-plugin-builder-workspace/README.md](skills/ndmf-plugin-builder-workspace/README.md)
  for details.
- This repository is also a Unity project with NDMF / Modular Avatar
  installed (see `Packages/vpm-manifest.json`), used to verify the skill
  against a real project.

## Developing the Skill

After updating a skill's `description`, re-evaluate trigger accuracy following
the steps in
[skills/ndmf-plugin-builder-workspace/README.md](skills/ndmf-plugin-builder-workspace/README.md)
(the same instruction is also recorded in `CLAUDE.md`).

## License

MIT. See [LICENSE](LICENSE).
