---
name: ndmf-plugin-builder
description: "Implement NDMF (Non-Destructive Modular Framework, nadena.dev.ndmf) plugins and passes for VRChat/Unity avatars -- build-time transforms that duplicate materials, rewrite AnimatorController/animation clip references, add or remove components, or otherwise modify an avatar without touching the source scene, prefabs, or assets. Also covers adding NDMF Preview support for such a transform (IRenderFilter, IRenderFilterNode, RenderGroup, ComputeContext, nadena.dev.ndmf.preview) so the effect is visible live in the Scene view without running a full build. Use this skill whenever the user asks to write, build, design, port, or debug an NDMF plugin or pass; wants a Unity/VRChat avatar modification to become 'non-destructive' or 'apply only at build time'; asks for 'NDMF Preview', 'live preview', 'preview support', or to 'see the result without building' for an existing or new NDMF transform; mentions nadena.dev.ndmf, Plugin<T>, Pass<T>, BuildContext, AnimatorServicesContext, or ordering relative to Modular Avatar; or describes an existing workflow that mutates source materials/prefabs/animations directly and should instead run automatically during the avatar build -- even if they never say the word 'NDMF'."
---

# NDMF Plugin Builder

Guides implementing an NDMF (`nadena.dev.ndmf`) plugin: a Unity Editor pass that
transforms a VRChat/Unity avatar non-destructively at build time, leaving the
source scene, prefabs, and assets untouched.

## Why this shape of problem bites people

An NDMF pass runs against a *build-time copy* of the avatar. Anything you want
to end up in the built avatar -- a swapped material, a rewritten animation, a
removed helper component -- has to be produced by your code, not by hand-editing
the source project. This has one recurring practical consequence worth
internalizing before writing anything: **every live reference to the thing
you're changing usually has an animated counterpart you need to change too**
(a renderer's current material *and* any animation clip that swaps it; a
component's current field value *and* any animation curve driving that field).
Forgetting the animated side is the single most common way an NDMF pass looks
correct in the Editor and breaks the moment an animation plays. Keep this in
mind through every step below.

## Step 1 -- Read the official best practices first

Before designing anything, fetch and read `https://ndmf.nadena.dev/best-practices.html`
with WebFetch. It's short, it's authoritative, and it can change independently
of this skill -- don't rely on a summary baked into this file going stale.
Re-fetch it if it's been a while since you last read it in this session.

## Step 2 -- Confirm the shape of the plugin

Before writing code, make sure you know:

- **What triggers the transform** -- a settings `MonoBehaviour` the user adds
  to the avatar, or an unconditional pass that runs on every avatar? Most
  non-trivial plugins want a settings component (see
  `references/common-patterns.md`) so users can opt in/out and configure it
  per-avatar.
- **Which build phase** the transform belongs in (Resolving / Generating /
  Transforming / Optimizing), and **whether it needs to run before or after
  another known plugin** -- most commonly Modular Avatar, qualified name
  `"nadena.dev.modular-avatar"`. Get the phase semantics from the best-practices
  page you just fetched, and the exact ordering API from
  `references/api-reference.md` -- don't guess; ordering bugs are subtle and
  only surface when the *other* plugin happens to be installed.
- **What exactly gets duplicated or rewritten, and whether an animation clip
  could reference it.** If in doubt, assume yes and read the animation section
  of `references/api-reference.md`.

Load `references/api-reference.md` now for the confirmed API surface
(`Plugin<T>`/`Pass<T>`, `BuildContext` members, the animator-services layer,
package/component conventions). Treat it as the primary source for exact
method names rather than re-deriving them from memory -- NDMF's extension-context
activation in particular has more than one method with subtly different
behavior, and guessing wrong compiles fine but breaks quietly.

## Step 3 -- Implement

1. Package layout and component conventions: see the "Package & component
   conventions" section of `references/api-reference.md`.
2. Plugin + Pass skeleton: see the "Plugin & Pass registration" section of
   `references/api-reference.md`.
3. For the specific transform you're building, check
   `references/common-patterns.md` -- it covers the two patterns that come up
   in almost every plugin (non-destructively duplicating a shared asset like a
   material, and rewriting animation references to match), including two
   concrete Unity API gotchas discovered the hard way: they compile fine and
   produce silently wrong output.
4. Report problems through `ErrorReport`, not exceptions -- a thrown exception
   aborts the *entire* avatar build for a problem the user could otherwise be
   warned about and continue past.

## Step 4 -- Add NDMF Preview support (only if asked)

If the user also wants to *see* the transform's effect in the Scene view
without running a full build -- they say "NDMF Preview," "preview," "live
preview," "see it without building," or mention
`IRenderFilter`/`RenderGroup`/`ComputeContext` -- that's NDMF Preview
(`nadena.dev.ndmf.preview`), a separate API layered on top of the pass you
just built, not a variant of it. Load `references/preview-api.md` before
designing it: it covers the registration API, and in particular a
quiet-by-design behavior (materials must be re-applied every frame in
`IRenderFilterNode.OnFrame`, not just set once) that compiles fine, passes
naive unit tests, and produces no error -- the only symptom is preview
silently doing nothing. It's the single most expensive mistake to make in this
part of NDMF, so read that section before writing the filter, not after
debugging why nothing shows up.

Skip this step entirely if the user only asked for the build-time transform.

## Step 5 -- Test

Load `references/testing.md` for how to write EditMode tests against a
hand-built minimal avatar (NDMF's distributed package ships no test helpers of
its own), plus two non-obvious blockers that otherwise waste time: unsaved
scene changes blocking a test run before it even starts, and a domain reload
needing a moment to settle before tests will run right after a compile. Separately,
driving a pass inside a test needs `ActivateExtensionContextRecursive<T>`,
not the non-recursive `ActivateExtensionContext<T>` -- that one is covered in
the "In unit tests" bullet of `references/api-reference.md`'s animation
section, not in `testing.md`'s blockers. If you added NDMF Preview support in
Step 4, `references/preview-api.md` has its own testing section -- notably a
`ComputeContext` caching gotcha that produces mysterious "object not found"
failures unrelated to your filter's actual logic.

Compile and run tests through whatever this project's Unity tooling is (check
for project-specific skills or a CLAUDE.md pointer first; don't assume a
generic `dotnet test` or CLI path works for a Unity package).

## Step 6 -- Verify for real, then review

The last section of `testing.md` explains why a real Editor smoke test and a
code-review pass both matter specifically for this kind of code -- do both
before calling the plugin done, not only when something feels off. Bugs that
compile fine and pass a naive test are the norm for Unity API work like this,
not the exception: this skill's own reference material documents two bugs
that were caught only by hands-on inspection and review, not by the initial
implementation or first test pass.
