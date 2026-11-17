# Adding or changing VRChat Expression Parameters

Load this when a pass adds, removes, renames, reorders, or retypes entries in
the avatar's `VRCExpressionParameters` -- directly, or by generating a
menu/animator whose parameters end up there -- or when anything about the
parameters a pass emits could depend on the build target. It also covers
declaring a component's parameters to NDMF with `IParameterProvider`, and
generating Modular Avatar's MA Parameters instead of editing the asset.

Contents:

- **Why: platform builds are matched by position, not by name**
- **The rule for a pass**, and the usual ways a pass breaks it
- **Declaring the parameters with `IParameterProvider`**
- **Writing the asset yourself**
- **Alternative: generate MA Parameters instead**
- **Checking it**

## Why: platform builds are matched by position, not by name

A cross-platform avatar is several separate uploads under one avatar ID: a PC
build, an Android build, and optionally an iOS build, built from one avatar
(with or without per-platform overrides). Viewers receive the wearer's synced
parameter values from whichever build the wearer is running, and apply them to
the build *they* loaded.

VRChat's creator docs (Animator Parameters, "Cross-Platform Parameter Sync",
last updated 2026-10-28) state that these values are matched **by position in
the parameter list and by parameter type, not by the names of the
parameters**: "For a given parameter to sync between PC and Quest, it has to be
in the same position in the parameter list, and have the same parameter type."
They recommend using the same Expression Parameters asset for every platform
"even if one version doesn't make use of all the parameters."

Nothing errors when the lists differ: the build and the upload both succeed.
The symptom only shows up across platforms at runtime. A PC wearer flips a
toggle, and Android viewers see whatever parameter sits at that slot in the
Android build change instead, or nothing at all. A plugin author testing on
one platform never sees it.

Keep the **names** identical too, for two reasons:

- **Today:** users who fix cross-platform order with Modular Avatar's Sync
  Parameter Sequence depend on names. It records the primary platform's
  parameters, and its docs say "Your primary platform avatar must contain all
  of the parameters that are synced on any variant of your avatar. If any are
  missing, the build will fail." A name that differs per build never matches
  that record.
- **Possibly tomorrow:** VRChat 2026.4.1 (build 1936, 2026-10-28) shipped
  name-based mapping of synced parameters between platform builds ("going off
  of names instead" of "positions in the synced parameter buffer"), and then
  reverted it ("reverted for now"). If it comes back, a parameter whose name
  differs between builds stops syncing even if its position matches.

A pass that emits the same names, in the same order, with the same types,
works under either rule.

These are VRChat client behaviors, not NDMF ones, and they can change. Before
relying on the details for a design decision, re-check
`https://creators.vrchat.com/avatars/animator-parameters/` and the latest
release notes under `https://docs.vrchat.com/docs/`. The docs only talk about
"PC and Quest"; treat iOS builds the same way.

## The rule for a pass

Given the same avatar, the pass must produce the same Expression Parameters on
every platform build: the same entries, in the same order, with the same
`name`, `valueType`, and `networkSynced`. If the installed VRChat SDK exposes
per-parameter bit width or signedness (the docs describe them under "Show
Advanced Options"), keep those identical too. The docs don't say whether
unsynced entries count toward a synced parameter's position (the reverted
release note's "synced parameter buffer" hints they don't, but that's not a
guarantee), so don't reason about which entries are "safe" to vary. Keep the
whole list identical; that is correct under any reading.

Your pass can only control its own output. Other tools, or a per-platform
override with a different hierarchy, can still make the lists diverge. The
goal is that your plugin is never the cause. Don't try to repair other tools'
lists from your pass; end users have dedicated tools for that (Modular Avatar's
Sync Parameter Sequence component, for example).

### Ways a pass breaks it

1. **Deciding the parameter set from the build target.** Watch for
   `EditorUserBuildSettings.activeBuildTarget`, `#if UNITY_ANDROID`,
   `#if UNITY_IOS`, `#if UNITY_STANDALONE`, or any "is this mobile?" helper
   that decides *whether a parameter exists*, where it goes, or its type. If a
   feature can't work on mobile (its shader or component is stripped there,
   say), skip the renderer/animation work on that platform but still emit the
   parameter, in the same slot, with the same type. Likewise, don't shrink a
   parameter on mobile (Int to Bool, or a narrower bit width) to save synced
   bits: the type is half of what VRChat matches on. The same applies to a
   settings flag like "enable on Android": it may gate the effect, not the
   parameter.

2. **Order that depends on object identity or discovery.** A list sorted by
   `GetInstanceID()`, `Object.FindObjectsOfType` results, or anything keyed by
   a Unity object's hash can come out in a different order in another Editor
   session or after a build-target switch. Iterating a `HashSet<T>` or
   `Dictionary<TKey, TValue>` is stable in practice when you only insert, but
   it isn't guaranteed, so don't let it decide the order either. Iterate in
   hierarchy order (`GetComponentsInChildren<T>(true)` on the avatar root) or
   sort by a stable key with `StringComparer.Ordinal` (culture-sensitive
   comparison can order differently on a machine with another locale). If the
   hierarchy itself can differ between platform variants, sort by name rather
   than hierarchy position.

3. **Names that aren't deterministic.** `Guid.NewGuid()`, `GetInstanceID()`,
   `GetHashCode()` of a Unity object, a counter shared across avatars, or a
   timestamp in a generated parameter name produces a different name on every
   build. Derive names from what the user configured (a name field on the
   component) or the object's path relative to the avatar root, under a fixed
   plugin-specific prefix. If you need a short unique suffix, hash that stable
   string with a fixed algorithm (e.g. SHA-1 of the path), not with object
   identity.

4. **Removing "unused" parameters per platform.** A pass that drops parameters
   the current build's animators don't read shifts every later parameter on
   that platform only. If the decision depends on platform-specific content,
   keep the entry instead. An unused parameter costs synced bits, but keeps
   the slots aligned.

## Declaring the parameters with `IParameterProvider`

Declare the parameters your component generates with NDMF's parameter
introspection API (NDMF 1.4.0+). Do this by default, not only when asked:
without it, parameter-usage displays (Modular Avatar's parameter usage window,
for example) show the user a synced-bit total that leaves your parameters out
until after the build, and tools that remap parameter names can't see them.

Declaring a parameter does **not** add it to the Expression Parameters asset.
Your pass still has to do that. Give both one shared, pure method that
describes the parameters for a component, and call it from the provider and
from the pass. That keeps the usage estimate equal to what the build emits, and
because the method doesn't read the build target, every platform gets the same
list.

```csharp
using System.Collections.Generic;
using nadena.dev.ndmf;
using UnityEngine;

internal static class GlowToggleParameters
{
    // Pure and deterministic: no build target, no instance IDs.
    // The pass calls this too, so the build matches what usage UIs show.
    public static string NameFor(GlowToggle c) => "GlowToggle/" + c.parameterName;
}

[ParameterProviderFor(typeof(GlowToggle))]
internal class GlowToggleParameterProvider : IParameterProvider
{
    private readonly GlowToggle _component;

    // Required: a public constructor taking the ForType component.
    public GlowToggleParameterProvider(GlowToggle component) => _component = component;

    public IEnumerable<ProvidedParameter> GetSuppliedParameters(BuildContext context = null)
    {
        // Return NEW objects on every call; NDMF mutates them (e.g. EffectiveName on remap).
        yield return new ProvidedParameter(
            GlowToggleParameters.NameFor(_component),
            ParameterNamespace.Animator,
            _component,
            GlowTogglePlugin.Instance,         // Plugin<T>.Instance
            AnimatorControllerParameterType.Bool)
        {
            WantSynced = true,
            DefaultValue = 0,                  // NDMF 1.5.0+
        };
    }

    // RemapParameters has a default no-op body on Unity 2021+; override it only
    // if your component renames parameters for its children.
}
```

Points that are easy to get wrong:

- The types live in the `nadena.dev.ndmf` namespace but in the
  **`nadena.dev.ndmf.vrchat`** assembly. Add it to the Editor asmdef's
  `references`, or the attribute and interface won't resolve.
- NDMF finds providers by scanning for `[ParameterProviderFor]` and calling a
  public constructor that takes the component. If there isn't one, NDMF logs
  an error once when it builds its provider table after a domain reload (easy
  to miss) and treats the component as providing nothing. The attribute also
  matches subclasses and implemented interfaces, so one provider can cover a
  base type.
- `GetSuppliedParameters` is called **outside** builds too (`context` is
  `null` then, e.g. for usage UIs). NDMF's interface documentation asks you
  not to change the number or type of synced parameters depending on the
  context, so that usage estimates stay correct. Treat it as the same rule as
  above: no build-target branches, no per-build names.
- Set `IsAnimatorOnly = true` for animator-internal parameters that must not
  go into the Expression Parameters asset, `WantSynced = false` for local-only
  ones, and `IsHidden = true` for internal parameters that usage UIs should
  not list.
- Providers are queried for components that exist at the time of the query.
  If your pass destroys its settings component (as SKILL.md Step 3 asks),
  compute everything it needs before destroying it.

### Reading parameters back with `ParameterInfo`

`ParameterInfo.ForContext(context).GetParametersForObject(avatarRoot)` returns
the parameters declared on the avatar by every provider (yours, other tools',
and NDMF's built-in ones for the avatar descriptor's existing asset entries,
PhysBones, and contacts), in declaration order: each object's components, then
its children in hierarchy order, skipping `EditorOnly`-tagged objects. Use
`ParameterInfo.ForUI` from editor UI and `ParameterInfo.ForPreview(computeContext)`
from NDMF Preview code.

It **merges** declarations by name. Only the first declarer's
`ProvidedParameter` survives, and later ones are folded into it (types
reconciled, sync flags combined). Two consequences:

- Don't use it to enumerate *your own* parameters by filtering on
  `p.Plugin == YourPlugin.Instance` or `p.Source`. A name that already exists
  in the user's asset is declared first by the avatar descriptor at the root,
  and two of your components that share a name come back as one entry with
  the first one's `Source`. Either way, a pass that builds one layer per
  returned entry silently skips some. Enumerate your own components and call
  your shared method instead.
- Do use it to look up the **effective** name of a parameter you declared:
  find the entry whose `OriginalName` is your name and read `EffectiveName`.
  It differs from the original only when a remapping tool (an MA Parameters
  rename on an ancestor, for example) applies. Those remaps are only visible
  while that tool's components still exist, so a pass that wants to honor
  them must run before that tool processes them (for Modular Avatar,
  `.BeforePlugin("nadena.dev.modular-avatar")`). Whatever name you settle on,
  use the same string for the asset entry, the animator parameter, and the
  menu control, or they silently stop matching.

## Writing the asset yourself

- If `VRCAvatarDescriptor.customExpressions` is `false`, VRChat ignores the
  descriptor's assets and uses its default menu and parameters. Set it to
  `true` when you add parameters.
- If `expressionParameters` (or `expressionsMenu`) is `null`, don't start from
  an empty asset: that drops VRChat's default parameters (`VRCEmote`,
  `VRCFaceBlendH`, `VRCFaceBlendV`) that the default menu and playable layers
  use. Start from a copy of the VRChat SDK's `DefaultExpressionParameters`
  asset (shipped under `Packages/com.vrchat.avatars/Samples/AV3 Demo Assets/
  Expressions Menu/`), or create one with those entries.
- Otherwise the descriptor still points at the user's source asset. Clone it
  (`Object.Instantiate`), assign the clone to the descriptor, and call
  `ObjectRegistry.RegisterReplacedObject(original, clone)`, as in the
  duplication pattern in `common-patterns.md`. Do this unconditionally
  rather than trying to detect whether an earlier pass already cloned it.
- `parameters` is an array: build a new array and assign it rather than trying
  to grow it in place.
- If an entry with your name already exists, reuse it instead of appending a
  duplicate. If its type differs from yours, report it through `ErrorReport`
  rather than silently retyping it.

## Alternative: generate MA Parameters instead

If the plugin already depends on Modular Avatar, or can reasonably require it,
consider having the pass generate an MA Parameters component
(`nadena.dev.modular_avatar.core.ModularAvatarParameters`) on the build copy
and leaving the Expression Parameters asset to MA. NDMF's own
`IParameterProvider` documentation points to this route for plugins that need
name remapping ("converting to e.g. Modular Avatar Parameters objects at build
time").

What MA then handles for you:

- Writing the entries into the Expression Parameters asset. You don't clone
  or edit the asset yourself.
- Merging and reporting duplicate or conflicting declarations from several
  sources.
- Remapping: a user's MA Parameters on an ancestor object can rename your
  parameter, and "Auto rename" (`internalParameter = true`) gives it a unique
  name, so you don't have to invent a collision suffix.

```csharp
using nadena.dev.modular_avatar.core;

// One generated object holds everything that must see MA's renames.
var holder = new GameObject("GlowToggle");
holder.transform.SetParent(toggle.transform, false);

var maParams = holder.AddComponent<ModularAvatarParameters>();
maParams.parameters.Add(new ParameterConfig
{
    nameOrPrefix = GlowToggleParameters.NameFor(toggle),  // still deterministic
    syncType = ParameterSyncType.Bool,     // the type; NotSynced means animator-only
    localOnly = false,                     // true = in the asset but not network-synced
    saved = true,
    defaultValue = 0,
    hasExplicitDefaultValue = true,
});

// The animator and the menu go on the same holder (or below it), so a rename
// reaches them too.
var merge = holder.AddComponent<ModularAvatarMergeAnimator>();
merge.animator = generatedFxController;    // uses the same parameter name
holder.AddComponent<ModularAvatarMenuItem>(); // configure its Control likewise
```

What to watch for:

- **It's a hard dependency.** The Editor asmdef needs a reference to
  `nadena.dev.modular-avatar.core`, and the package should declare MA in
  `vpmDependencies`. Without MA installed, nothing reads the component and the
  parameters never reach the asset. If MA should stay optional, keep the
  direct-asset path as the fallback; don't half-depend on it.
- **Run before MA.** Generate the components in the Generating phase (NDMF's
  phase for generating components that Modular Avatar will consume). A
  component added after MA has run is ignored.
- **`[DisallowMultipleComponent]`.** The target object may already carry the
  user's own MA Parameters, and Unity then refuses a second one (`AddComponent`
  doesn't give you a usable component). Put yours on a generated GameObject,
  as above.
- **Renames only reach what MA processes, and only below the MA Parameters
  object.** An MA rename (Auto rename, or a user's MA Parameters on an
  ancestor) applies to MA Merge Animator controllers, MA Menu Items and Menu
  Installers, and PhysBone/Contact parameters on that object and its
  children. It isn't applied to a layer your pass writes straight into the
  avatar's FX controller, to a menu you edit directly, or to components on the
  *parent* of the generated object. Those keep the original name and silently
  stop matching. If you go through MA Parameters, put the Merge Animator and
  Menu Item on the same generated object or below it, or don't rely on
  renaming.
- **The cross-platform rule still applies.** MA appends the parameters in
  hierarchy order, so a pass that generates MA Parameters only on some
  platforms, or with per-build names, breaks sync the same way. MA doesn't
  document how Auto rename picks names, so if a name must be stable across
  platform builds, set an explicit deterministic name instead of Auto rename.
- **Keep your own `IParameterProvider`.** A component your pass creates only
  exists during the build. Usage UIs query the edit-time scene, so they only
  see these parameters if your source component declares them.

## Checking it

- Grep the pass for `activeBuildTarget`, `UNITY_ANDROID`, `UNITY_IOS`,
  `UNITY_STANDALONE`, `NewGuid`, `GetInstanceID`, and `FindObjectsOfType`
  near the code that builds the parameter list.
- In an EditMode test (see `testing.md`), build two identical avatars, run
  the pass on each, and assert that the resulting
  `(name, valueType, networkSynced)` lists are equal index by index. Fresh
  objects get fresh instance IDs, so this catches identity-based names. It
  doesn't reliably catch identity-based *ordering*: identically built avatars
  tend to get instance IDs in the same relative order. To catch that too,
  create the second avatar's objects in a different order, then set the same
  sibling order.
- For a real check, build the same avatar for Windows and Android and diff the
  two built parameter lists the same way.
