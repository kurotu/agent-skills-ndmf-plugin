# NDMF API Reference

Verified against `nadena.dev.ndmf` 1.14.0. Method names and behavior are
generally stable across versions, but if something here doesn't match what you
see in `Packages/nadena.dev.ndmf` (or wherever the package is vendored in the
project), trust the installed source over this file and re-derive from there.

## Plugin & Pass registration

`Plugin<T> where T : Plugin<T>, new()`:

- Override `QualifiedName` (a unique dotted id -- reverse-DNS of your package
  is a safe default, e.g. `"com.example.my-plugin"`) and `DisplayName`.
- Override `protected override void Configure()` -- the only required method.
- Put `[assembly: ExportsPlugin(typeof(YourPlugin))]` at the top of one file in
  the assembly. NDMF discovers plugins this way; there is no separate manual
  registration step.

Inside `Configure()`:

- `InPhase(BuildPhase phase)` returns a `Sequence` and starts one. Phase order
  is `Resolving` -> `Generating` -> `Transforming` -> `Optimizing`; pick the
  phase using the semantics described on the best-practices page (fetched in
  Step 1), not by guessing from the name alone.
- `sequence.Run(YourPass.Instance)` registers a pass (or use
  `sequence.Run("display name", ctx => { ... })` for a short inline pass that
  doesn't need its own class).
- Ordering relative to other plugins:
  - `.AfterPlugin("nadena.dev.modular-avatar")` takes the *qualified name as a
    string*, so it works even when the other plugin's assembly isn't
    referenced or installed at all -- this is a soft dependency and is safe to
    declare unconditionally, even in a project where that other plugin is
    absent.
  - A generic `.AfterPlugin<T>()` overload also exists but requires a hard
    compile-time reference to the other plugin's type. Prefer the string
    overload unless your plugin already depends on that other plugin's types
    for some other reason.
  - Mirror APIs: `.BeforePlugin(...)`, `.AfterPass(...)`, `.WaitFor(...)`.

`Pass<T> where T : Pass<T>, new()`:

- Singleton instance via `Pass<T>.Instance`.
- Override `protected abstract void Execute(BuildContext context)`.
- `QualifiedName` defaults to the C# type's full name, which is fine for most
  passes.
- Add `[DependsOnContext(typeof(SomeExtensionContext))]` on the class to have
  NDMF activate that extension context before your pass runs and deactivate it
  afterward automatically. This is the normal way to use the animator-services
  layer below -- see that section for the one place this attribute isn't
  enough on its own (unit tests).

## BuildContext -- what you get inside Execute()

- `GameObject AvatarRootObject` / `Transform AvatarRootTransform`.
- `T Extension<T>()` -- fetch an active extension context. Throws if the
  context isn't active, so pair it with `[DependsOnContext]` on your pass (or
  explicit activation -- see below).
- `IAssetSaver AssetSaver` -- call `AssetSaver.SaveAsset(newObject)` for every
  new `UnityEngine.Object` you create (materials, clips, textures, ...).
  Prefer this over writing into `AssetContainer` directly; it's the
  documented, idiomatic entry point for "this new object should persist in the
  build output."
- `ObjectRegistry` -- call the static
  `ObjectRegistry.RegisterReplacedObject(oldObj, newObj)` whenever you swap one
  asset for another, so NDMF, other plugins, and the error-reporting UI can
  trace the replacement back to the object the user actually authored.
- `ErrorReport` -- report user-facing, recoverable problems via
  `ErrorReport.ReportError(localizer, severity, key, ...args)` instead of
  throwing. The build continues and the user sees a localized message in their
  build report rather than the whole build aborting.
- `context.VRChatAvatarDescriptor()` (extension method from the
  `nadena.dev.ndmf.vrchat` assembly) is the current way to get the avatar's
  `VRCAvatarDescriptor` -- the older `context.AvatarDescriptor` property is
  obsolete.

## Animation-safe editing -- `nadena.dev.ndmf.animator`

Any pass that changes materials, transforms, or other values that *could* also
be driven by an animation must go through this layer, or it will only fix the
static/default state and silently leave broken references inside animation
clips -- see the "Why this shape of problem bites people" note in SKILL.md.

- `AnimatorServicesContext` is the extension context. Get it via
  `context.Extension<AnimatorServicesContext>()` after it's active -- either
  via `[DependsOnContext(typeof(AnimatorServicesContext))]` on your `Pass<T>`,
  or `sequence.WithRequiredExtension(typeof(AnimatorServicesContext), ...)` in
  `Configure()`.
- `.AnimationIndex.RewriteObjectCurves(Func<Object, Object> mapping)` walks
  every object-reference curve (materials, textures, or other object
  references assigned via animation) across every animator controller NDMF has
  virtualized, and replaces each keyframe's value through your mapping
  function.
  - The mapping must never return `null` for a non-null input -- it throws
    `InvalidOperationException` if it does. Curve values that are already
    `null` are skipped automatically before your mapping is even called, so
    you don't need to guard for that case yourself.
  - This rewrites *every layer of every controller* NDMF knows about, not just
    one layer. That's usually what you want -- a renderer's live value and its
    animated overrides need to stay consistent with each other -- but if you
    need a narrower scope, `VirtualControllerContext.Controllers` is a
    dictionary keyed by layer type (e.g. `VRCAvatarDescriptor.AnimLayerType`
    for VRChat avatars), and `AnimationIndex` has a constructor that accepts
    just the subset of virtual nodes you want indexed.
- **Object-reference curves are only half the picture.** Numeric properties
  driven by animation -- blend shape weights, a `float`/`bool`/enum shader or
  component field, a collider radius -- are *float curves*, not object
  curves, and `RewriteObjectCurves` does not touch them. `VirtualClip` (also
  under `nadena.dev.ndmf.animator`) exposes the float-curve equivalents:
  `GetFloatCurveBindings()` to enumerate, `GetFloatCurve`/`SetFloatCurve` to
  read/replace a specific binding. If your pass fixes a value that could be
  animated by a float curve (e.g. forcing a blend shape weight), you generally
  need to neutralize or remove the competing float curve too -- otherwise the
  animator will keep driving the old value at runtime and silently override
  whatever your pass set. Enumerate clips via `AnimatorServicesContext`'s
  indexed data (or walk `VirtualControllerContext`'s controllers directly) to
  find the bindings whose path/property match what you changed.
- **Moving, renaming, reparenting, or removing a GameObject** while
  `AnimatorServicesContext` is active is a separate concern from the curve
  values above -- it's about whether an animation path (e.g.
  `Body/Hips/Chest`) still resolves to the right object at all, not what
  value a curve carries. `AnimatorServicesContext.ObjectPathRemapper` tracks
  this automatically, but only if you follow its rules:
  - **Moving or renaming an object is free** -- paths are tracked by
    `Transform` reference internally, not by string, so no extra call is
    needed for this case alone.
  - **Removing an object outright with a replacement taking its place**
    requires calling `ObjectPathRemapper.ReplaceObject(old, new)` before the
    removal, so existing animation paths get redirected to the replacement
    instead of going dangling.
  - **Adding a new object** you want existing or new animations to target:
    call `GetVirtualPathForObject(transform)` (or `RecordObjectTree(subtree)`
    for a whole hierarchy, e.g. an instantiated prefab) to register its path
    before authoring curves against it.
  - Access it via
    `context.Extension<AnimatorServicesContext>().ObjectPathRemapper` (same
    activation requirement as `AnimationIndex`).
- **Removing an object with no replacement** leaves its paths resolving to
  `null` in `ObjectPathRemapper.GetVirtualToRealPathMap()` -- i.e. any
  animation curve still targeting it is now a dangling reference. Don't
  assume this is automatically harmless -- verify in the actual Editor (see
  `testing.md`) whether a dangling curve binding is silently ignored or
  produces a console warning, and prune the binding explicitly
  (`GetObjectCurveBindings()`/`GetFloatCurveBindings()` plus removing the
  matching entries) if it isn't clean.
- **In unit tests**, activating this context requires
  `context.ActivateExtensionContextRecursive<AnimatorServicesContext>()`, not
  the plain `ActivateExtensionContext<T>()` -- the non-recursive version does
  not also activate `AnimatorServicesContext`'s own declared dependency
  (`VirtualControllerContext`) and throws "Extension ... not active" instead.
  Deactivate with `context.DeactivateAllExtensionContexts()`, which commits the
  virtualized controllers back onto the avatar in dependency order -- only
  read the results back after this call returns. (In a real build driven by
  `[DependsOnContext]` or `AvatarProcessor`, NDMF handles this activation
  order correctly on its own; this distinction only matters when you're
  constructing a `BuildContext` by hand in a test. See `testing.md`.)

## VRChat build pipeline integration & VRCFury ordering

This section applies only when building for VRChat (VRCSDK installed). It is
essential for diagnosing **ordering bugs** or behavior that differs between a
plain NDMF build and a VRChat SDK upload or Play mode entry.

### The "VRCFury sandwich" -- split callback order

NDMF registers **two** `IVRCSDKPreprocessAvatarCallback` hooks, not one:

| Hook class | `callbackOrder` | Phases covered |
|---|---|---|
| `BuildFrameworkPreprocessHook` | `-11000` | `First` → `Transforming` |
| `BuildFrameworkOptimizeHook` | `-1025` | `Optimizing` → `Last` |

If VRCFury is installed, NDMF source documents its callback at approximately
`-10000` (`// Must run before -10000 (VRCFury)`), which falls between these
two NDMF hooks. In that setup, the practical execution order for VRChat build
and Play mode entry is:

> **NDMF** (Resolving / Generating / Transforming) → **VRCFury** → **NDMF** (Optimizing / Last)

Consequences:
- Passes in `Transforming` or earlier run *before* VRCFury. They cannot see
  VRCFury's output.
- Passes in `Optimizing` or `Last` run *after* VRCFury. This is intentional for
  optimizer passes that should see the fully merged avatar.

Source: `Editor/VRChat/BuildFrameworkPreprocessHook.cs`.

### ApplyOnPlay goes through the full VRCSDK preprocessor chain

When Play mode is entered for a VRChat avatar, NDMF's `ApplyOnPlay` path calls
`VRCBuildPipelineCallbacks.OnPreprocessAvatar(avatarGameObject)` -- **not**
`AvatarProcessor.ProcessAvatar` directly. This triggers the full VRCSDK
`IVRCSDKPreprocessAvatarCallback` chain, so all the phase ordering above applies
in Play mode too (VRCFury and other VRCSDK preprocessors participate).

NDMF also replicates the VRCSDK clone/original naming convention at this point:
it temporarily renames the avatar to `"(Clone)"` and creates a short-lived fake
original `GameObject` because some non-NDMF hooks (e.g. VRCFury) depend on that
name pattern to distinguish the build copy from the source avatar.

For non-VRChat avatars, or when VRCSDK is absent, `ApplyOnPlay` bypasses all of
this and calls NDMF directly.

Source: `Editor/ApplyOnPlay.cs`, around the `VRCAvatarDescriptor` branch.

### VRCFury hack detection in `AvatarProcessor.ProcessAvatar`

VRCFury occasionally calls `AvatarProcessor.ProcessAvatar` directly during its
own processing. NDMF detects this via a stack-trace pattern check and adjusts:

- **Inside VRCSDK build hooks** (normal build or Play via VRC pipeline): the
  duplicate call is silently ignored -- NDMF will run via its own registered
  hooks in the correct order anyway.
- **In Play mode outside the VRCSDK hook chain** (legacy/manual path): `lastPhase`
  is clamped to `BuildPhase.Transforming`, skipping `Optimizing` and `Last` to
  avoid running optimizer passes before VRCFury has finished.

**Practical implication for custom build scripts and tests:** calling
`AvatarProcessor.ProcessAvatar` directly may produce different phase behavior
depending on what else is on the call stack. When debugging order-sensitive
behavior, verify against the installed source in
`Packages/nadena.dev.ndmf/Editor/AvatarProcessor.cs` and
`Editor/VRChat/BuildFrameworkPreprocessHook.cs` -- the installed code is
authoritative over any summary in this reference file.

Source: `Editor/AvatarProcessor.cs`, `IsVRCFuryHack`/`InHookExecution` block.

## Package & component conventions

- Give a runtime settings component `INDMFEditorOnly` (from the
  `nadena.dev.ndmf` namespace) instead of hand-rolling `#if` guards around
  VRChat's `IEditorOnly`. It derives from `IEditorOnly` only when
  `NDMF_VRCSDK3_AVATARS` is defined, and is a harmless no-op interface
  otherwise -- so the same component source compiles and behaves correctly
  whether or not VRCSDK is installed in the project.
- A typical three-assembly layout:
  - `Runtime` -- component definitions only, references `nadena.dev.ndmf.runtime`.
  - `Editor` -- the plugin and passes, references `Runtime` plus
    `nadena.dev.ndmf` and `nadena.dev.ndmf.runtime`, `includePlatforms: ["Editor"]`.
  - `Tests/Editor` -- see `testing.md`.
- If a pass reads settings from a component and the effect should be "baked
  in" to the build output, destroy the component at the end of the pass
  (`Object.DestroyImmediate(component)`) rather than leaving it behind. The
  whole point of NDMF is that the *avatar project* stays untouched while the
  *build output* reflects the transform -- a leftover marker component in the
  built avatar usually isn't what the user wants, unless it has a genuine
  runtime purpose.
