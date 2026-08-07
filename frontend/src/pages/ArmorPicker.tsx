import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  ArmorSolveResult,
  ArmorSolveSet,
  ArmorStatCaps,
  ArmorStatKey,
  Character,
  ExoticArmorOption,
  SubclassPlug,
} from "../api";

const CLASSES = ["warlock", "hunter", "titan"] as const; // D2ArmorPicker order
const STATS: ArmorStatKey[] = ["Weapons", "Health", "Class", "Grenade", "Super", "Melee"];
const ELEMENTS = ["arc", "solar", "void", "stasis", "strand", "prism"] as const;
const STAT_MAX = 200;

const CLASS_ICON_PATHS: Record<string, string> = {
  titan:
    "m14.839 15.979-13.178-7.609v15.218zm2.322 0 13.178 7.609v-15.218zm5.485-12.175-6.589-3.804-13.178 7.609 13.178 7.609 13.179-7.609zm0 16.784-6.589-3.805-13.178 7.609 13.178 7.608 13.179-7.608-6.59-3.805z",
  hunter:
    "m9.055 10.446 6.945-.023-6.948 10.451 6.948-.024-7.412 11.15h-7.045l7.036-10.428h-7.036l7.032-10.422h-7.032l7.507-11.126 6.95-.024zm13.89 0-6.945-10.446 6.95.024 7.507 11.126h-7.032l7.032 10.422h-7.036l7.036 10.428h-7.045l-7.412-11.15 6.948.024-6.948-10.451z",
  warlock:
    "m5.442 23.986 7.255-11.65-2.71-4.322-9.987 15.972zm5.986 0 4.28-6.849-2.717-4.333-6.992 11.182zm7.83-11.611 7.316 11.611h5.426l-10.015-15.972zm-7.26 11.611h8.004l-4.008-6.392zm6.991-11.182-2.703 4.324 4.302 6.858h5.413zm-5.707-.459 2.71-4.331 2.71 4.331-2.703 4.326z",
};

const ELEMENT_COLOR: Record<string, string> = {
  arc: "text-cyan-300 border-cyan-400/50 bg-cyan-500/10",
  solar: "text-orange-300 border-orange-400/50 bg-orange-500/10",
  void: "text-purple-300 border-purple-400/50 bg-purple-500/10",
  stasis: "text-blue-300 border-blue-400/50 bg-blue-500/10",
  strand: "text-lime-300 border-lime-400/50 bg-lime-500/10",
  prism: "text-pink-300 border-pink-400/50 bg-pink-500/10",
};

function ClassIcon({ classType, className }: { classType: string; className?: string }) {
  const d = CLASS_ICON_PATHS[classType];
  if (!d) return null;
  return (
    <svg viewBox="0 0 32 32" fill="currentColor" className={`block shrink-0 ${className || ""}`} aria-hidden>
      <path d={d} />
    </svg>
  );
}

function formatBonus(bonus: Record<string, number> | undefined): string {
  if (!bonus) return "";
  return STATS.map((s) => {
    const v = bonus[s] ?? bonus[s.toLowerCase()] ?? 0;
    return v ? `${v > 0 ? "+" : ""}${v} ${s.slice(0, 3)}` : null;
  })
    .filter(Boolean)
    .join(" ");
}

function zeroTargets(): Record<ArmorStatKey, number> {
  return { Weapons: 0, Health: 0, Class: 0, Grenade: 0, Super: 0, Melee: 0 };
}

function ResultsTable({
  results,
  targets,
  characterId,
  onStatus,
}: {
  results: ArmorSolveSet[];
  targets: Record<string, number>;
  characterId: string;
  onStatus: (msg: string, isError?: boolean) => void;
}) {
  const [busyIdx, setBusyIdx] = useState<number | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  if (!results.length) return null;

  async function copyDim(set: ArmorSolveSet, index: number) {
    if (!set.dim?.search) return;
    try {
      await navigator.clipboard.writeText(set.dim.search);
      setCopiedIdx(index);
      onStatus("DIM search copied.");
      window.setTimeout(() => setCopiedIdx((i) => (i === index ? null : i)), 1500);
    } catch {
      onStatus("Could not copy to clipboard.", true);
    }
  }

  async function equipSet(set: ArmorSolveSet, index: number) {
    if (!characterId) {
      onStatus("Pick a character first to equip this set.", true);
      return;
    }
    const ids = ["helmet", "gauntlets", "chest", "legs", "class"]
      .map((slot) => set.armor[slot]?.itemInstanceId)
      .filter((id): id is string => !!id);
    if (!ids.length) {
      onStatus("This set has no equippable instance ids.", true);
      return;
    }
    setBusyIdx(index);
    try {
      const res = await api.equipLoadout({ characterId, itemInstanceIds: ids });
      onStatus(res.message, !!res.errors?.length);
    } catch (e) {
      onStatus((e as Error).message, true);
    } finally {
      setBusyIdx(null);
    }
  }

  return (
    <div className="overflow-x-auto rounded border border-white/10">
      <table className="w-full text-xs text-left">
        <thead className="bg-white/[0.04] text-white/45 uppercase tracking-wide">
          <tr>
            <th className="px-2 py-2 font-medium">Set</th>
            {STATS.map((s) => (
              <th key={s} className="px-2 py-2 font-medium text-center">
                {s.slice(0, 3)}
              </th>
            ))}
            <th className="px-2 py-2 font-medium text-center">Tiers</th>
            <th className="px-2 py-2 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {results.map((set, i) => {
            const exotic = Object.values(set.armor).find((p) => p.isExotic);
            return (
              <tr key={i} className="border-t border-white/5 hover:bg-white/[0.03]">
                <td className="px-2 py-2">
                  <div className="flex items-center gap-1">
                    {["helmet", "gauntlets", "chest", "legs", "class"].map((slot) => {
                      const p = set.armor[slot];
                      if (!p) return null;
                      return (
                        <div
                          key={slot}
                          title={p.name}
                          className={`w-8 h-8 overflow-hidden border shrink-0 ${
                            p.isExotic ? "border-exotic" : "border-white/15"
                          }`}
                        >
                          {p.icon && (
                            <img src={p.icon} alt="" className="w-full h-full object-cover" />
                          )}
                        </div>
                      );
                    })}
                    {exotic && (
                      <span className="ml-1 text-exotic truncate max-w-[6rem]" title={exotic.name}>
                        {exotic.name}
                      </span>
                    )}
                  </div>
                </td>
                {STATS.map((s) => {
                  const v = set.totals[s] ?? 0;
                  const goal = targets[s] ?? 0;
                  const met = goal === 0 || v >= goal;
                  return (
                    <td
                      key={s}
                      className={`px-2 py-2 text-center tabular-nums ${
                        met ? "text-emerald-300" : "text-amber-200"
                      }`}
                    >
                      {v}
                    </td>
                  );
                })}
                <td className="px-2 py-2 text-center tabular-nums text-white/70">
                  {set.tiersMet}/6
                </td>
                <td className="px-2 py-2">
                  <div className="flex flex-wrap items-center justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => copyDim(set, i)}
                      className="px-1.5 py-1 rounded bg-white/10 hover:bg-white/15"
                      title={set.dim?.search || "DIM search"}
                    >
                      {copiedIdx === i ? "Copied" : "Copy DIM"}
                    </button>
                    {set.dim?.url && (
                      <a
                        href={set.dim.url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-1.5 py-1 rounded bg-sky-500/20 hover:bg-sky-500/30 text-sky-200"
                      >
                        Open DIM
                      </a>
                    )}
                    <button
                      type="button"
                      disabled={busyIdx === i || !characterId}
                      onClick={() => equipSet(set, i)}
                      className="px-1.5 py-1 rounded bg-exotic/90 text-black font-medium disabled:opacity-40"
                      title={
                        characterId
                          ? "Transfer + equip these pieces on the selected character"
                          : "Select a character to equip"
                      }
                    >
                      {busyIdx === i ? "Equipping…" : "Equip"}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function ArmorPicker({
  authed,
  characters,
}: {
  authed: boolean;
  characters: Character[];
}) {
  const [characterId, setCharacterId] = useState("");
  const [classType, setClassType] = useState<string>("warlock");
  const [includeVault, setIncludeVault] = useState(true);
  const [ownedOnly, setOwnedOnly] = useState(false); // D2AP shows the full exotic list
  const [targets, setTargets] = useState<Record<ArmorStatKey, number>>(zeroTargets);
  const [exotics, setExotics] = useState<ExoticArmorOption[]>([]);
  const [exoticHash, setExoticHash] = useState<number | null>(null);
  const [element, setElement] = useState<string>("void");
  const [aspects, setAspects] = useState<SubclassPlug[]>([]);
  const [fragments, setFragments] = useState<SubclassPlug[]>([]);
  const [aspectHashes, setAspectHashes] = useState<number[]>([]);
  const [fragmentHashes, setFragmentHashes] = useState<number[]>([]);
  const [loadingExotics, setLoadingExotics] = useState(false);
  const [loadingSubclass, setLoadingSubclass] = useState(false);
  const [solving, setSolving] = useState(false);
  const [capsLoading, setCapsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<{ msg: string; isError: boolean } | null>(
    null
  );
  const [result, setResult] = useState<ArmorSolveResult | null>(null);
  const [caps, setCaps] = useState<ArmorStatCaps | null>(null);
  const capsReq = useRef(0);

  function onActionStatus(msg: string, isError = false) {
    setActionStatus({ msg, isError });
  }

  const selectedChar = useMemo(
    () => characters.find((c) => c.characterId === characterId) || null,
    [characters, characterId]
  );

  // Prefer first character's class when characters arrive (still overridable).
  useEffect(() => {
    if (selectedChar?.classType && selectedChar.classType !== "unknown") {
      setClassType(selectedChar.classType);
    } else if (!selectedChar && characters[0]?.classType) {
      // only seed once if still on default and we have chars — don't fight user
    }
  }, [selectedChar]);

  useEffect(() => {
    if (characters.length && !characterId) {
      // Auto-select first character like D2AP (optional UX)
      const first = characters[0];
      setCharacterId(first.characterId);
      if (first.classType && first.classType !== "unknown") setClassType(first.classType);
    }
  }, [characters]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!authed || !classType) {
      setExotics([]);
      return;
    }
    let alive = true;
    setLoadingExotics(true);
    setError(null);
    api
      .listExotics(classType, characterId || null, includeVault)
      .then((res) => {
        if (!alive) return;
        setExotics(res.exotics);
        if (exoticHash && !res.exotics.some((e) => e.hash === exoticHash)) {
          setExoticHash(null);
        }
      })
      .catch((e) => alive && setError((e as Error).message))
      .finally(() => alive && setLoadingExotics(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authed, classType, characterId, includeVault]);

  useEffect(() => {
    if (!authed || !classType || !element) {
      setAspects([]);
      setFragments([]);
      return;
    }
    let alive = true;
    setLoadingSubclass(true);
    api
      .subclassOptions(classType, element)
      .then((res) => {
        if (!alive) return;
        setAspects(res.aspects);
        setFragments(res.fragments);
        const aSet = new Set(res.aspects.map((a) => a.hash));
        const fSet = new Set(res.fragments.map((f) => f.hash));
        setAspectHashes((prev) => prev.filter((h) => aSet.has(h)));
        setFragmentHashes((prev) => prev.filter((h) => fSet.has(h)));
      })
      .catch((e) => alive && setError((e as Error).message))
      .finally(() => alive && setLoadingSubclass(false));
    return () => {
      alive = false;
    };
  }, [authed, classType, element]);

  // D2ArmorPicker-style caps: when you push Health to 200, other maxes shrink to what's still possible.
  useEffect(() => {
    if (!authed || !classType) {
      setCaps(null);
      return;
    }
    const reqId = ++capsReq.current;
    setCapsLoading(true);
    const t = window.setTimeout(() => {
      api
        .armorStatCaps({
          classType,
          characterId: characterId || null,
          includeVault,
          exoticHash,
          targets,
          fragmentHashes,
        })
        .then((res) => {
          if (capsReq.current !== reqId) return;
          setCaps(res);
          if (res.ok && res.max) {
            // Clamp any target that now exceeds the reachable max for that stat.
            setTargets((prev) => {
              let changed = false;
              const next = { ...prev };
              for (const s of STATS) {
                const cap = Math.max(0, Math.min(STAT_MAX, res.max[s] ?? STAT_MAX));
                if (next[s] > cap) {
                  next[s] = cap;
                  changed = true;
                }
              }
              return changed ? next : prev;
            });
          }
        })
        .catch((e) => {
          if (capsReq.current === reqId) setError((e as Error).message);
        })
        .finally(() => {
          if (capsReq.current === reqId) setCapsLoading(false);
        });
    }, 350);
    return () => window.clearTimeout(t);
  }, [authed, classType, characterId, includeVault, exoticHash, targets, fragmentHashes]);

  const fragmentBonusPreview = useMemo(() => {
    const total: Record<string, number> = Object.fromEntries(STATS.map((s) => [s, 0]));
    for (const h of fragmentHashes) {
      const f = fragments.find((x) => x.hash === h);
      if (!f) continue;
      for (const s of STATS) {
        total[s] += f.bonus[s.toLowerCase()] ?? f.bonus[s] ?? 0;
      }
    }
    return total;
  }, [fragmentHashes, fragments]);

  const visibleExotics = ownedOnly ? exotics.filter((e) => e.owned) : exotics;
  const classLocked = !!selectedChar;

  function setTarget(stat: ArmorStatKey, value: number) {
    const cap = Math.max(0, Math.min(STAT_MAX, caps?.max?.[stat] ?? STAT_MAX));
    const v = Math.max(0, Math.min(cap, Math.round(Number.isFinite(value) ? value : 0)));
    setTargets((prev) => (prev[stat] === v ? prev : { ...prev, [stat]: v }));
  }

  function toggleAspect(hash: number) {
    setAspectHashes((prev) => {
      if (prev.includes(hash)) return prev.filter((h) => h !== hash);
      if (prev.length >= 2) return [...prev.slice(1), hash];
      return [...prev, hash];
    });
  }

  function toggleFragment(hash: number) {
    setFragmentHashes((prev) => {
      if (prev.includes(hash)) return prev.filter((h) => h !== hash);
      if (prev.length >= 5) return [...prev.slice(1), hash];
      return [...prev, hash];
    });
  }

  async function solve() {
    if (!classType) {
      setError("Pick a class first.");
      return;
    }
    setSolving(true);
    setError(null);
    try {
      const res = await api.solveArmor({
        classType,
        characterId: characterId || null,
        includeVault,
        exoticHash,
        targets,
        fragmentHashes,
        aspectHashes,
        maxResults: 20,
      });
      setResult(res);
      if (!res.ok) setError(res.error || "No sets found.");
    } catch (e) {
      setError((e as Error).message);
      setResult(null);
    } finally {
      setSolving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Armor optimizer</h2>
        <p className="text-sm text-white/50">
          Set targets (0–{STAT_MAX}), pick an exotic and fragments — find vault/inventory sets that
          hit the combo.
        </p>
      </div>

      {/* Class tabs — D2ArmorPicker style */}
      <div className="flex rounded border border-white/10 overflow-hidden">
        {CLASSES.map((cl) => {
          const active = classType === cl;
          const char = characters.find((c) => c.classType === cl);
          return (
            <button
              key={cl}
              type="button"
              disabled={classLocked && classType !== cl}
              onClick={() => {
                setClassType(cl);
                if (char) setCharacterId(char.characterId);
              }}
              className={`flex-1 flex items-center justify-center gap-2 px-3 py-2.5 text-sm capitalize border-r border-white/10 last:border-r-0 transition-colors ${
                active
                  ? "bg-sky-500/20 text-sky-100"
                  : "bg-white/[0.02] text-white/60 hover:bg-white/5"
              } disabled:opacity-40`}
            >
              <ClassIcon classType={cl} className="w-4 h-4" />
              {cl}
              {char?.light != null && (
                <span className="text-[11px] text-white/35 tabular-nums">{char.light}</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs text-white/50">
        <label className="flex items-center gap-1.5">
          Character
          <select
            value={characterId}
            onChange={(e) => setCharacterId(e.target.value)}
            disabled={!authed}
            className="px-2 py-1 rounded bg-white/5 border border-white/10 text-sm text-white disabled:opacity-50"
          >
            <option value="">All + vault</option>
            {characters.map((c) => (
              <option key={c.characterId} value={c.characterId}>
                {c.classType} {c.light != null ? `· ${c.light}` : ""}
              </option>
            ))}
          </select>
        </label>
        {characterId && (
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={includeVault}
              onChange={(e) => setIncludeVault(e.target.checked)}
            />
            Include vault
          </label>
        )}
      </div>

      <div className="grid lg:grid-cols-[minmax(280px,340px)_1fr] gap-4 items-start">
        {/* LEFT — controls */}
        <div className="space-y-3">
          {/* Stat sliders */}
          <div className="p-3 rounded border border-white/10 bg-[#12151c]">
            <div className="flex items-center mb-3">
              <h3 className="text-sm font-medium">Desired Stat Tiers</h3>
              {capsLoading && (
                <span className="ml-2 text-[10px] text-white/35">Updating max…</span>
              )}
              <button
                type="button"
                className="ml-auto text-[11px] text-white/40 hover:text-white/70"
                onClick={() => setTargets(zeroTargets())}
              >
                Reset to 0
              </button>
            </div>
            <p className="text-[11px] text-white/35 mb-3">
              Values show <span className="text-white/55">target / max</span> from your armor
              (other targets cap what’s left).
            </p>
            <div className="space-y-3">
              {STATS.map((stat) => {
                const v = targets[stat];
                const cap = Math.max(0, Math.min(STAT_MAX, caps?.max?.[stat] ?? STAT_MAX));
                const abs = Math.max(0, Math.min(STAT_MAX, caps?.absoluteMax?.[stat] ?? STAT_MAX));
                const frag = fragmentBonusPreview[stat] || 0;
                const sliderMax = Math.max(cap, 0);
                // Keep range usable even at 0 cap (disabled look via opacity).
                const rangeMax = Math.max(sliderMax, 1);
                return (
                  <div key={stat} className={cap === 0 && v === 0 ? "opacity-60" : ""}>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="w-[4.5rem] text-xs text-white/70">{stat}</span>
                      <input
                        type="range"
                        min={0}
                        max={rangeMax}
                        step={10}
                        value={Math.min(v, sliderMax)}
                        disabled={sliderMax === 0}
                        onChange={(e) => setTarget(stat, Number(e.target.value))}
                        className="flex-1 accent-sky-400 h-1.5 cursor-pointer disabled:cursor-not-allowed"
                      />
                      <input
                        type="number"
                        min={0}
                        max={sliderMax || STAT_MAX}
                        value={v}
                        onChange={(e) => setTarget(stat, Number(e.target.value))}
                        className="w-12 px-1 py-1 rounded bg-black/40 border border-white/15 text-xs tabular-nums text-center"
                      />
                      <span
                        className="w-[3.25rem] text-[11px] tabular-nums text-right"
                        title={
                          abs !== cap
                            ? `Max with current targets: ${cap} (inventory alone: ${abs})`
                            : `Max from your armor: ${cap}`
                        }
                      >
                        <span className="text-sky-200/90">{v}</span>
                        <span className="text-white/30"> / </span>
                        <span className={cap < abs ? "text-amber-200/90" : "text-white/45"}>
                          {cap}
                        </span>
                      </span>
                    </div>
                    {frag !== 0 && (
                      <p className="text-[10px] text-sky-300/70 pl-[4.5rem]">
                        Fragments {frag > 0 ? "+" : ""}
                        {frag} → armor needs {Math.max(0, v - frag)}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Exotic grid */}
          <div className="p-3 rounded border border-white/10 bg-[#12151c]">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-sm font-medium">Exotic</h3>
              <label className="flex items-center gap-1.5 text-[11px] text-white/45 ml-auto">
                <input
                  type="checkbox"
                  checked={ownedOnly}
                  onChange={(e) => setOwnedOnly(e.target.checked)}
                />
                Owned only
              </label>
              {exoticHash != null && (
                <button
                  type="button"
                  onClick={() => setExoticHash(null)}
                  className="text-[11px] text-white/40 hover:text-white/70"
                >
                  Any
                </button>
              )}
            </div>
            {loadingExotics ? (
              <p className="text-sm text-white/40">Loading exotics…</p>
            ) : (
              <div className="grid grid-cols-6 sm:grid-cols-7 gap-1 max-h-56 overflow-y-auto content-start pr-0.5">
                {visibleExotics.map((ex) => {
                  const active = exoticHash === ex.hash;
                  return (
                    <button
                      key={ex.hash}
                      type="button"
                      title={ex.name + (ex.owned ? "" : " (not owned)")}
                      onClick={() => setExoticHash(active ? null : ex.hash)}
                      className={`relative aspect-square overflow-hidden border transition-all ${
                        active
                          ? "border-exotic ring-2 ring-exotic/50 scale-[1.03]"
                          : ex.owned
                            ? "border-white/20 hover:border-sky-400/50"
                            : "border-white/10 opacity-40 hover:opacity-70"
                      }`}
                    >
                      {ex.icon ? (
                        <img src={ex.icon} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <span className="text-[8px] p-0.5 text-white/50">{ex.name.slice(0, 4)}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
            {!loadingExotics && !visibleExotics.length && (
              <p className="text-sm text-white/40 mt-1">
                {ownedOnly
                  ? "No owned exotics — uncheck Owned only to browse all."
                  : "No exotic armor found."}
              </p>
            )}
            {exoticHash != null && (
              <p className="text-xs text-exotic mt-2 truncate">
                {exotics.find((e) => e.hash === exoticHash)?.name}
              </p>
            )}
          </div>

          {/* Subclass */}
          <div className="p-3 rounded border border-white/10 bg-[#12151c] space-y-2.5">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-medium">Subclass</h3>
              {loadingSubclass && <span className="text-[11px] text-white/35">Loading…</span>}
            </div>
            <div className="flex flex-wrap gap-1">
              {ELEMENTS.map((el) => (
                <button
                  key={el}
                  type="button"
                  onClick={() => setElement(el)}
                  className={`px-2 py-1 rounded border text-[11px] capitalize ${
                    element === el
                      ? ELEMENT_COLOR[el]
                      : "border-white/10 text-white/50 hover:bg-white/5"
                  }`}
                >
                  {el}
                </button>
              ))}
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wide text-white/40 mb-1">
                Aspects ({aspectHashes.length}/2)
              </div>
              <div className="flex flex-wrap gap-1 max-h-28 overflow-y-auto">
                {aspects.map((a) => {
                  const active = aspectHashes.includes(a.hash);
                  return (
                    <button
                      key={a.hash}
                      type="button"
                      title={a.name}
                      onClick={() => toggleAspect(a.hash)}
                      className={`flex items-center gap-1 px-1 py-0.5 rounded border text-[11px] ${
                        active
                          ? "border-sky-400/50 bg-sky-500/15"
                          : "border-white/10 text-white/65 hover:bg-white/5"
                      }`}
                    >
                      {a.icon && <img src={a.icon} alt="" className="w-5 h-5" />}
                      <span className="truncate max-w-[7rem]">{a.name}</span>
                    </button>
                  );
                })}
                {!aspects.length && (
                  <span className="text-[11px] text-white/35">None for this class/element.</span>
                )}
              </div>
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wide text-white/40 mb-1">
                Fragments ({fragmentHashes.length}/5)
              </div>
              <div className="flex flex-wrap gap-1 max-h-40 overflow-y-auto">
                {fragments.map((f) => {
                  const active = fragmentHashes.includes(f.hash);
                  const bonusTxt = formatBonus(f.bonus);
                  return (
                    <button
                      key={f.hash}
                      type="button"
                      title={bonusTxt ? `${f.name} · ${bonusTxt}` : f.name}
                      onClick={() => toggleFragment(f.hash)}
                      className={`flex items-center gap-1 px-1 py-0.5 rounded border text-[11px] ${
                        active
                          ? "border-sky-400/50 bg-sky-500/15"
                          : f.hasStatBonus
                            ? "border-white/15 text-white/75 hover:bg-white/5"
                            : "border-white/10 text-white/40 hover:bg-white/5"
                      }`}
                    >
                      {f.icon && <img src={f.icon} alt="" className="w-5 h-5" />}
                      <span className="truncate max-w-[6.5rem]">{f.name}</span>
                      {bonusTxt && (
                        <span className="text-[9px] text-sky-300/80 whitespace-nowrap">{bonusTxt}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={solve}
            disabled={!authed || solving || !classType}
            className="w-full px-4 py-2.5 rounded bg-exotic text-black font-semibold disabled:opacity-50"
          >
            {solving ? "Searching…" : "Find armor sets"}
          </button>
        </div>

        {/* RIGHT — results */}
        <div className="min-w-0 space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium">Results</h3>
            {result?.searchedCombos != null && (
              <span className="text-[11px] text-white/35">
                {result.searchedCombos.toLocaleString()} combos · {result.results.length} shown
              </span>
            )}
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}
          {actionStatus && (
            <p className={`text-sm ${actionStatus.isError ? "text-amber-300" : "text-emerald-300"}`}>
              {actionStatus.msg}
            </p>
          )}

          {!result && !error && (
            <div className="rounded border border-dashed border-white/10 p-8 text-center text-sm text-white/35">
              Drag the stat sliders, pick an exotic, then Find armor sets.
              <br />
              Results show here like D2ArmorPicker.
            </div>
          )}

          {result?.ok && result.results.length > 0 && (
            <ResultsTable
              results={result.results}
              targets={result.targets || targets}
              characterId={characterId}
              onStatus={onActionStatus}
            />
          )}

          {result?.ok && result.results.length === 0 && (
            <p className="text-sm text-white/50">No combinations found. Lower targets or pick a different exotic.</p>
          )}
        </div>
      </div>
    </div>
  );
}
