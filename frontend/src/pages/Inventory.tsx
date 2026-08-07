import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  pointerWithin,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  api,
  ArmorDupeGroup,
  ArmorDupePiece,
  Character,
  Item,
  ItemDetail,
  Profile,
  VaultCleanScan,
  WeaponDupeGroup,
  WeaponDupePiece,
} from "../api";

// DIM-style rarity border colors.
const RARITY_COLOR: Record<string, string> = {
  exotic: "#ceae33",
  legendary: "#522f65",
  rare: "#5076a2",
  uncommon: "#4d7d55",
  common: "#b8b0a6",
  basic: "#b8b0a6",
  unknown: "#4b5563",
};

// Slightly lifted rarity fills shown behind the icon (like DIM tiles).
const RARITY_BG: Record<string, string> = {
  exotic: "#ceae33",
  legendary: "#522f65",
  rare: "#5076a2",
  uncommon: "#366f42",
  common: "#c3bcb4",
  basic: "#c3bcb4",
  unknown: "#3a3f4a",
};

const MW_GOLD = "#eade8b";
const EQUIPPED_WHITE = "#f5f5f5";
const CRAFTED_RED = "#d0553d";

const WEAPON_GROUPS: { key: string; label: string }[] = [
  { key: "kinetic", label: "Kinetic" },
  { key: "energy", label: "Energy" },
  { key: "power", label: "Power" },
];

const ARMOR_GROUPS: { key: string; label: string }[] = [
  { key: "helmet", label: "Helmet" },
  { key: "gauntlets", label: "Arms" },
  { key: "chest", label: "Chest" },
  { key: "legs", label: "Legs" },
  { key: "class", label: "Class" },
];

// DIM puts these above weapons, per character.
const TOP_GROUPS: { key: string; label: string }[] = [
  { key: "postmaster", label: "Postmaster" },
  { key: "engrams", label: "Engrams" },
];

const CLASS_LABELS: Record<string, string> = {
  titan: "Titan",
  hunter: "Hunter",
  warlock: "Warlock",
  unknown: "Any",
};

// Official class glyphs (destiny-icons — same set DIM uses).
const CLASS_ICON_PATHS: Record<string, string> = {
  titan:
    "m14.839 15.979-13.178-7.609v15.218zm2.322 0 13.178 7.609v-15.218zm5.485-12.175-6.589-3.804-13.178 7.609 13.178 7.609 13.179-7.609zm0 16.784-6.589-3.805-13.178 7.609 13.178 7.608 13.179-7.608-6.59-3.805z",
  hunter:
    "m9.055 10.446 6.945-.023-6.948 10.451 6.948-.024-7.412 11.15h-7.045l7.036-10.428h-7.036l7.032-10.422h-7.032l7.507-11.126 6.95-.024zm13.89 0-6.945-10.446 6.95.024 7.507 11.126h-7.032l7.032 10.422h-7.036l7.036 10.428h-7.045l-7.412-11.15 6.948.024-6.948-10.451z",
  warlock:
    "m5.442 23.986 7.255-11.65-2.71-4.322-9.987 15.972zm5.986 0 4.28-6.849-2.717-4.333-6.992 11.182zm7.83-11.611 7.316 11.611h5.426l-10.015-15.972zm-7.26 11.611h8.004l-4.008-6.392zm6.991-11.182-2.703 4.324 4.302 6.858h5.413zm-5.707-.459 2.71-4.331 2.71 4.331-2.703 4.326z",
};

function ClassIcon({ classType, className }: { classType: string; className?: string }) {
  const d = CLASS_ICON_PATHS[classType];
  if (!d) return null;
  return (
    <svg
      viewBox="0 0 32 32"
      fill="currentColor"
      className={`block shrink-0 ${className || ""}`}
      aria-hidden
    >
      <path d={d} />
    </svg>
  );
}

// Armor bucket glyphs (destiny-icons), viewBox 0 0 51 51.
const ARMOR_BUCKET_PATHS: Record<string, string[]> = {
  helmet: [
    "M24.77,7.03c-8.15,0.38-14.42,7.41-14.42,15.57v16.06c0,0.23,0.13,0.44,0.34,0.53l10.33,4.68c0.78,0.35,1.66-0.22,1.66-1.07v-5.75V31.9c0-0.39-0.19-0.75-0.52-0.97l-5.39-3.64c-0.87-0.52-1.43-1.5-1.34-2.61c0.13-1.46,1.46-2.52,2.93-2.52h4.36c0.65,0,1.17,0.53,1.17,1.17v6.71c0,0,0,0.61,1.61,0.61c1.61,0,1.61-0.61,1.61-0.61v-6.71c0-0.65,0.52-1.17,1.17-1.17h4.36c1.47,0,2.8,1.06,2.93,2.52c0.1,1.11-0.47,2.09-1.34,2.61l-5.39,3.64c-0.32,0.22-0.52,0.58-0.52,0.97v5.16v5.75c0,0.85,0.88,1.42,1.66,1.07l10.33-4.68c0.21-0.1,0.34-0.3,0.34-0.53V22.17C40.66,13.56,33.47,6.62,24.77,7.03z",
  ],
  gauntlets: [
    "M40.1,30.03c0.39-0.47,0.59-1.11,0.42-1.8c-0.18-0.76-0.81-1.39-1.58-1.55c-0.81-0.17-1.54,0.14-2.01,0.68c-0.04,0.05-0.08,0.1-0.12,0.15c-0.47,0.61-1.95,2.37-3.29,2.45c-1.62,0.1,2.51-16.14,2.51-16.14c0.04-0.15,0.07-0.31,0.07-0.48c0-0.98-0.79-1.77-1.77-1.77c-0.81,0-1.49,0.55-1.69,1.29c-0.01,0.05-0.02,0.1-0.03,0.15c-0.24,1.21-1.68,8.2-2.81,8.89C28.48,22.77,28.5,8.79,28.5,8.79c0-0.98-0.79-1.77-1.77-1.77c-0.98,0-1.77,0.79-1.77,1.77c0,0-0.35,12.85-1.73,12.73c-1.37-0.12-2.47-10.67-2.47-10.67c0-0.98-0.79-1.77-1.77-1.77c-0.98,0-1.77,0.79-1.77,1.77c0,0.15,0.02,0.28,0.06,0.42c0.27,2.06,1.36,11.12-0.06,11.12c-1.6,0-3.68-6.35-3.68-6.35c-0.23-0.62-0.82-1.06-1.52-1.06c-0.9,0-1.62,0.73-1.62,1.62c0,0.09,0.01,0.17,0.03,0.25c0.02,0.09,0.05,0.17,0.09,0.25c0.99,2.71,6.28,17.46,7.26,26.23c0.03,0.25,0.24,0.44,0.49,0.44h12.19c0.26,0,0.47-0.19,0.5-0.45c0.1-1.04,0.52-3.68,2.09-5.54c1.8-2.14,6.06-6.89,6.86-7.79c0.02-0.02,0.03-0.04,0.05-0.06C40.07,30.07,40.11,30.03,40.1,30.03z",
  ],
  chest: [
    "M42.49,13.55c-1.06-1.51-4.05-5.05-9.52-6.49c-0.35-0.09-0.72,0.14-0.78,0.5c-0.35,2.04-1.78,8.08-6.69,8.08s-6.34-6.04-6.69-8.08c-0.06-0.36-0.43-0.59-0.78-0.5c-5.47,1.44-8.46,4.98-9.52,6.49c-0.24,0.34-0.09,0.8,0.3,0.94c2.01,0.7,7.34,2.94,7.34,7.01c0,4.24-4.47,6.89-5.87,7.61c-0.25,0.13-0.38,0.4-0.33,0.67c1.44,7.62,7.55,13.09,8.67,14.04c0.11,0.1,0.25,0.15,0.4,0.15h6.47h6.47c0.15,0,0.29-0.05,0.4-0.15c1.12-0.95,7.23-6.42,8.67-14.04c0.05-0.27-0.08-0.54-0.33-0.67c-1.4-0.72-5.87-3.37-5.87-7.61c0-4.08,5.33-6.32,7.34-7.01C42.58,14.35,42.73,13.88,42.49,13.55z",
  ],
  legs: [
    "M13,7.6c3.63,0,10.02,0,13.96,0c1.73,0,2.99,1.64,2.54,3.32l-5.44,20.46c-0.07,0.28,0.03,0.57,0.28,0.72c0.99,0.62,4.64,2.57,8.15,5.78c0.12,0.11,2.92-0.03,3.09-0.01c2.31,0.2,3.97-0.08,5.05,4.7c0.09,0.42-0.21,0.82-0.64,0.82c-4.21,0-24.43,0-28.17,0c-0.34,0-0.63-0.26-0.66-0.61c-0.15-1.82-0.4-7.23,1.74-9.32c0.17-0.16,0.25-0.37,0.2-0.6c-0.39-1.74-2.09-9.83-2.74-22.48C10.29,8.88,11.48,7.6,13,7.6z",
  ],
  class: [
    "M43.12,7.12C38.99,9.45,25.5,9.02,25.5,9.02S12.01,9.45,7.88,7.12C7.51,6.91,7.03,7.09,6.94,7.51C6.58,9,6.07,11.93,7.03,13.37c0.09,0.13,0.22,0.21,0.38,0.25c1.23,0.3,7.36,1.65,18.09,1.65c10.73,0,16.86-1.35,18.09-1.65c0.15-0.04,0.29-0.12,0.38-0.25c0.96-1.44,0.45-4.37,0.1-5.86C43.97,7.09,43.49,6.91,43.12,7.12z",
    "M9.27,28.34c0,0,0,2.34,2.27,2.34s2.27-2.34,2.27-2.34V15.73c-1.93-0.22-3.45-0.45-4.55-0.65V28.34z",
    "M16.3,34.8c0,0,0,2.34,2.27,2.34s2.27-2.34,2.27-2.34V16.24c-1.66-0.06-3.18-0.16-4.55-0.27V34.8z",
    "M37.18,28.34c0,0,0,2.34,2.27,2.34s2.27-2.34,2.27-2.34V15.08c-1.09,0.2-2.61,0.44-4.55,0.65V28.34z",
    "M30.15,34.8c0,0,0,2.34,2.27,2.34s2.27-2.34,2.27-2.34V15.97c-1.36,0.11-2.88,0.21-4.55,0.27V34.8z",
    "M23.23,16.31v25.31c0,0,0,2.34,2.27,2.34s2.27-2.34,2.27-2.34V16.31c-0.74,0.01-1.49,0.02-2.27,0.02C24.72,16.34,23.96,16.33,23.23,16.31z",
  ],
};

function BucketIcon({ slot, className }: { slot: string; className?: string }) {
  const paths = ARMOR_BUCKET_PATHS[slot];
  if (!paths) return null;
  return (
    <svg
      viewBox="0 0 51 51"
      fill="currentColor"
      className={`block shrink-0 ${className || ""}`}
      aria-hidden
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

// Armor stat display order (Mobility, Resilience, Recovery, Discipline, Intellect, Strength).
const ARMOR_STAT_ORDER = [2996146975, 392767087, 1943323491, 1735777505, 144602215, 4244567218];

function bucketKey(i: Item): string | null {
  // Match in-game / DIM: weapons by equipment slot (kinetic/energy/power), not ammo type.
  if (i.kind === "weapon") return i.slot;
  if (i.kind === "armor") return i.slot;
  if (i.kind === "postmaster") return "postmaster";
  if (i.kind === "engram") return "engrams";
  return null;
}

// --- DIM-like search -------------------------------------------------------
function tokenMatch(i: Item, t: string): boolean {
  if (t.startsWith("is:")) {
    const v = t.slice(3);
    switch (v) {
      case "exotic":
      case "legendary":
      case "rare":
      case "uncommon":
      case "common":
        return i.tier === v;
      case "masterwork":
      case "masterworked":
        return !!i.isMasterwork;
      case "crafted":
        return !!i.isCrafted;
      case "equipped":
        return i.location === "equipped";
      case "postmaster":
        return i.kind === "postmaster";
      case "engram":
      case "engrams":
        return i.kind === "engram";
      case "weapon":
        return i.kind === "weapon";
      case "armor":
        return i.kind === "armor";
      case "titan":
      case "hunter":
      case "warlock":
        return i.classType === v;
      case "arc":
      case "solar":
      case "void":
      case "stasis":
      case "strand":
        return (i.damageName || "").toLowerCase() === v;
      case "primary":
      case "special":
      case "heavy":
        return i.ammoType === v;
      case "kinetic":
      case "energy":
      case "power":
        return i.slot === v;
      case "helmet":
        return i.slot === "helmet";
      case "arms":
      case "gauntlets":
        return i.slot === "gauntlets";
      case "chest":
        return i.slot === "chest";
      case "legs":
        return i.slot === "legs";
      case "classitem":
      case "class":
        return i.slot === "class";
      default:
        return i.name.toLowerCase().includes(v);
    }
  }
  return i.name.toLowerCase().includes(t);
}

function matchesQuery(i: Item, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return q.split(/\s+/).every((t) => tokenMatch(i, t));
}

// --- Tile ------------------------------------------------------------------
const TILE_SIZE = "w-14 h-14"; // 56px — slightly larger, DIM-like

function TileFace({
  item,
  dimmed = false,
  ghost = false,
}: {
  item: Item;
  dimmed?: boolean;
  ghost?: boolean;
}) {
  const rarity = RARITY_COLOR[item.tier] || RARITY_COLOR.unknown;
  const bg = RARITY_BG[item.tier] || RARITY_BG.unknown;
  const equipped = item.location === "equipped";
  const borderColor = item.isMasterwork
    ? MW_GOLD
    : equipped
      ? EQUIPPED_WHITE
      : item.isCrafted
        ? CRAFTED_RED
        : "rgba(255,255,255,0.28)";
  const borderWidth = item.isMasterwork || equipped || item.isCrafted ? 2 : 1;
  const wlTier = item.wishlist?.tier || (item.wishlist?.is_wishlisted ? "god" : "none");
  const isGod = wlTier === "god" || !!item.wishlist?.is_wishlisted;
  const isNear = wlTier === "near";

  return (
    <div
      className={`relative box-border ${TILE_SIZE} shrink-0 overflow-hidden ${
        dimmed ? "opacity-40" : ""
      } ${ghost ? "shadow-xl shadow-black/50 scale-105" : ""} ${
        isGod && !dimmed ? "ring-2 ring-[#f5dc56] ring-offset-1 ring-offset-black" : ""
      }`}
      style={{
        backgroundColor: bg,
        border: `${borderWidth}px solid ${isGod ? MW_GOLD : borderColor}`,
        boxShadow: item.isMasterwork && !dimmed ? `inset 0 -6px 8px -3px ${MW_GOLD}` : undefined,
      }}
    >
      {item.icon ? (
        <img
          key={item.icon}
          src={item.icon}
          alt=""
          className="absolute inset-0 w-full h-full object-cover pointer-events-none"
          draggable={false}
        />
      ) : null}
      <span
        className="absolute bottom-0 left-0 right-0 h-[4px] pointer-events-none"
        style={{ background: item.isMasterwork || isGod ? MW_GOLD : rarity }}
      />
      <span
        className="absolute inset-x-0 bottom-0 h-1/3 pointer-events-none"
        style={{ background: `linear-gradient(to top, ${rarity}55, transparent)` }}
      />
      {item.damageIcon ? (
        <img
          src={item.damageIcon}
          alt=""
          className={`absolute left-0 w-4 h-4 bg-black/70 p-px pointer-events-none ${
            isGod ? "top-[14px]" : "top-0"
          }`}
          draggable={false}
        />
      ) : null}
      {item.hasOrnament ? (
        <span
          className="absolute top-0 right-0 w-2 h-2 rounded-bl pointer-events-none"
          style={{ background: "#7ec8ff" }}
        />
      ) : null}
      {isGod && (
        <span
          className="absolute top-0 left-0 right-0 text-[9px] font-black tracking-wide text-center leading-none py-0.5 pointer-events-none"
          style={{
            background: "linear-gradient(to bottom, #f5dc56, #c9a227)",
            color: "#1a1200",
            textShadow: "0 0 1px rgba(255,255,255,0.4)",
          }}
          title={item.wishlist?.notes || "Wishlist god roll"}
        >
          GOD
        </span>
      )}
      {!isGod && isNear && (
        <span
          className="absolute top-0 left-0 px-0.5 text-[8px] font-bold leading-none py-0.5 pointer-events-none bg-amber-500/90 text-black"
          title={
            item.wishlist?.notes ||
            `${item.wishlist?.matched_perks || 0}/${item.wishlist?.needed_perks || "?"} wishlist perks`
          }
        >
          NEAR
        </span>
      )}
      {item.power != null ? (
        <span className="absolute bottom-[4px] right-0 text-[10px] leading-none px-0.5 bg-black/75 text-[#c3f0ff] tabular-nums pointer-events-none font-medium">
          {item.power}
        </span>
      ) : null}
    </div>
  );
}

function sortInventoryItems(items: Item[]): Item[] {
  return [...items].sort((a, b) => {
    const sa = a.wishlistScore ?? (a.wishlist?.is_wishlisted ? 1000 : (a.wishlist?.matched_perks || 0) * 10);
    const sb = b.wishlistScore ?? (b.wishlist?.is_wishlisted ? 1000 : (b.wishlist?.matched_perks || 0) * 10);
    if (sa !== sb) return sb - sa;
    return (b.power || 0) - (a.power || 0);
  });
}

function Tile({
  item,
  onSelect,
  dimmed = false,
}: {
  item: Item;
  onSelect?: (i: Item) => void;
  dimmed?: boolean;
}) {
  const id = item.itemInstanceId || `hash-${item.itemHash}`;
  const canDrag = !!item.itemInstanceId && !dimmed;
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id,
    data: { item },
    disabled: !canDrag,
  });

  return (
    <div
      ref={setNodeRef}
      {...(canDrag ? listeners : {})}
      {...(canDrag ? attributes : {})}
      onClick={() => !dimmed && item.itemInstanceId && onSelect?.(item)}
      className={`touch-none ${
        dimmed
          ? "opacity-40 cursor-default"
          : canDrag
            ? "cursor-grab active:cursor-grabbing"
            : item.itemInstanceId
              ? "cursor-pointer"
              : ""
      } ${isDragging ? "opacity-30" : ""}`}
      title={`${item.name}${item.power ? ` · ${item.power}` : ""}${
        item.damageName ? ` · ${item.damageName}` : ""
      } · ${item.tier}${item.isMasterwork ? " · Masterwork" : ""}${
        item.location === "equipped" ? " · Equipped" : ""
      }${item.isCrafted ? " · Crafted" : ""}${item.hasOrnament ? " · Ornament" : ""}${
        dimmed ? " · (filtered out)" : ""
      }`}
    >
      <TileFace item={item} dimmed={dimmed} />
    </div>
  );
}

function DropZone({
  id,
  data,
  className = "",
  overClassName = "",
  title,
  children,
}: {
  id: string;
  data: { kind: "move" | "equip"; toStore?: string; characterId?: string };
  className?: string;
  overClassName?: string;
  title?: string;
  children: ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id, data });
  return (
    <div
      ref={setNodeRef}
      title={title}
      className={`${className} ${isOver ? overClassName : ""}`}
    >
      {children}
    </div>
  );
}

function CharacterHeader({ character }: { character: Character }) {
  return (
    <div
      className="relative h-14 rounded overflow-hidden border border-white/10"
      style={
        character.emblemPath
          ? { backgroundImage: `url(${character.emblemPath})`, backgroundSize: "cover" }
          : undefined
      }
    >
      <div className="absolute inset-0 bg-gradient-to-r from-black/70 to-black/20" />
      <div className="relative h-full flex flex-col justify-center px-3">
        <span className="capitalize font-semibold text-white text-sm drop-shadow">
          {character.classType}
        </span>
        <span className="text-lg font-bold text-[#f5dc56] drop-shadow leading-none">
          {character.light}
        </span>
      </div>
    </div>
  );
}

// --- Item detail modal -----------------------------------------------------
function ItemDetailModal({ item, onClose }: { item: Item; onClose: () => void }) {
  const [detail, setDetail] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setDetail(null);
    setError(null);
    if (!item.itemInstanceId) {
      setError("This item has no instance id.");
      return;
    }
    api
      .itemDetail(item.itemInstanceId, item.itemHash)
      .then((d) => {
        if (active) setDetail(d);
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [item.itemInstanceId, item.itemHash]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const rarity = RARITY_COLOR[item.tier] || RARITY_COLOR.unknown;
  const stats = useMemo(() => {
    if (!detail) return [];
    const order = (h: number) => {
      const idx = ARMOR_STAT_ORDER.indexOf(h);
      return idx === -1 ? 999 : idx;
    };
    return [...detail.stats].sort((a, b) => order(a.hash) - order(b.hash));
  }, [detail]);

  const totalArmor =
    item.kind === "armor" ? stats.reduce((sum, s) => sum + (s.value || 0), 0) : null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start sm:items-center justify-center bg-black/70 p-3 sm:p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md max-h-[90vh] overflow-y-auto rounded border border-white/15 bg-[#0f1218] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{
          boxShadow: item.isMasterwork
            ? `0 0 0 1px ${MW_GOLD}, 0 20px 50px rgba(0,0,0,0.6)`
            : "0 20px 50px rgba(0,0,0,0.6)",
        }}
      >
        {/* header — rarity band like DIM */}
        <div className="relative" style={{ background: rarity }}>
          <div className="absolute inset-0 bg-gradient-to-b from-black/10 to-black/55" />
          <div className="relative flex items-start gap-3 p-4">
            {(detail?.icon || item.icon) && (
              <div
                className="w-16 h-16 shrink-0 overflow-hidden"
                style={{
                  background: RARITY_BG[item.tier] || RARITY_BG.unknown,
                  boxShadow: `inset 0 0 0 2px ${
                    item.isMasterwork
                      ? MW_GOLD
                      : item.location === "equipped"
                        ? EQUIPPED_WHITE
                        : "rgba(0,0,0,0.4)"
                  }`,
                }}
              >
                <img
                  key={detail?.icon || item.icon || ""}
                  src={(detail?.icon || item.icon)!}
                  alt=""
                  className="w-full h-full object-cover"
                />
              </div>
            )}
            <div className="min-w-0 flex-1 pr-2">
              <div className="flex items-center gap-2">
                {detail?.damageIcon && (
                  <img src={detail.damageIcon} alt="" className="w-4 h-4" />
                )}
                <h2 className="text-lg font-bold leading-tight text-white drop-shadow truncate">
                  {item.name}
                </h2>
              </div>
              <p className="text-xs text-white/85 mt-0.5">
                {detail?.typeName || item.itemTypeName || item.kind}
                {item.classType && item.classType !== "unknown"
                  ? ` · ${item.classType.charAt(0).toUpperCase()}${item.classType.slice(1)}`
                  : ""}
              </p>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-black/35 text-white/90">
                  {item.tier}
                </span>
                {(detail?.hasOrnament || item.hasOrnament) && (
                  <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-sky-500/30 text-sky-100">
                    Ornament
                  </span>
                )}
                {item.isMasterwork && (
                  <span
                    className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded"
                    style={{ background: MW_GOLD, color: "#1a1500" }}
                  >
                    Masterwork
                  </span>
                )}
                {item.location === "equipped" && (
                  <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-white text-black">
                    Equipped
                  </span>
                )}
                {item.isCrafted && (
                  <span
                    className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded text-white"
                    style={{ background: CRAFTED_RED }}
                  >
                    Crafted
                  </span>
                )}
              </div>
            </div>
            <div className="shrink-0 flex flex-col items-end gap-1">
              <button
                onClick={onClose}
                className="w-7 h-7 rounded bg-black/40 hover:bg-black/60 text-white/80 leading-none"
                aria-label="Close"
              >
                ×
              </button>
              {(detail?.power ?? item.power) != null && (
                <div className="text-right">
                  <div className="text-2xl font-bold text-white leading-none drop-shadow">
                    {detail?.power ?? item.power}
                  </div>
                  <div className="text-[10px] text-white/70 uppercase tracking-wide">Power</div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="p-4">
          {error && <p className="text-red-400 text-sm">{error}</p>}
          {!detail && !error && <p className="text-white/50 text-sm">Loading details…</p>}

          {stats.length > 0 && (
            <div className="mb-4">
              <div className="flex items-baseline justify-between mb-2">
                <h3 className="text-xs font-semibold text-white/70 uppercase tracking-wide">Stats</h3>
                {totalArmor != null && (
                  <span className="text-xs text-white/50">
                    Total <span className="text-white font-semibold tabular-nums">{totalArmor}</span>
                  </span>
                )}
              </div>
              <div className="space-y-1.5">
                {stats.map((s) => (
                  <div key={s.hash} className="flex items-center gap-2 text-xs">
                    <span className="w-24 shrink-0 text-white/70 truncate">{s.name}</span>
                    <div className="flex-1 h-2.5 rounded-sm bg-white/10 overflow-hidden">
                      <div
                        className="h-full"
                        style={{
                          width: `${Math.min(100, (s.value / (item.kind === "armor" ? 42 : 100)) * 100)}%`,
                          background: item.kind === "armor" ? "#5ea9ff" : MW_GOLD,
                        }}
                      />
                    </div>
                    <span className="w-8 text-right tabular-nums font-medium">{s.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {detail?.socketGroups.map((g) => (
            <div key={g.name} className="mb-4">
              <h3 className="text-xs font-semibold text-white/70 uppercase tracking-wide mb-2">
                {g.name}
              </h3>
              <div className="grid grid-cols-1 gap-1">
                {g.plugs.map((p, idx) => (
                  <div
                    key={g.name + idx}
                    className={`flex items-center gap-2 px-2 py-1.5 rounded bg-white/[0.04] border ${
                      p.enabled ? "border-white/15" : "border-white/5 opacity-40"
                    }`}
                    title={p.name}
                  >
                    {p.icon ? (
                      <img src={p.icon} alt="" className="w-7 h-7 rounded-sm bg-black/40" />
                    ) : (
                      <div className="w-7 h-7 rounded-sm bg-white/10" />
                    )}
                    <span className="text-sm leading-tight">{p.name}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {detail?.flavor && (
            <p className="mt-1 text-xs italic text-white/40 border-t border-white/10 pt-3">
              {detail.flavor}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Armor dupe finder -----------------------------------------------------
const SLOT_LABELS: Record<string, string> = {
  helmet: "Helmet",
  gauntlets: "Arms",
  chest: "Chest",
  legs: "Legs",
  class: "Class",
};

function locLabelItem(p: { location: string }): string {
  if (p.location === "vault") return "Vault";
  if (p.location === "equipped") return "Equipped";
  return "Inventory";
}

function wlBadge(tier: string | undefined) {
  if (tier === "god") {
    return (
      <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-[#f5dc56] text-black tracking-wide">
        GOD ROLL
      </span>
    );
  }
  if (tier === "near") {
    return (
      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/90 text-black">
        NEAR
      </span>
    );
  }
  return null;
}

function VaultCleanPanel({
  open,
  onClose,
  onVaulted,
}: {
  open: boolean;
  onClose: () => void;
  onVaulted: () => void;
}) {
  const [tab, setTab] = useState<"weapons" | "armor">("weapons");
  const [scan, setScan] = useState<VaultCleanScan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keepByGroup, setKeepByGroup] = useState<Record<string, string>>({});
  const [vaulting, setVaulting] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  function seedKeeps(res: VaultCleanScan) {
    const initial: Record<string, string> = {};
    res.weapons.groups.forEach((g, i) => {
      const god = g.pieces.find((p) => p.wishlist?.tier === "god" || p.wishlist?.is_wishlisted);
      initial[`w-${i}`] = (god || g.pieces[0]).itemInstanceId;
    });
    res.armor.groups.forEach((g, i) => {
      const tuned = g.pieces.find((p) => p.tuning && !p.tuning.isEmpty);
      initial[`a-${i}`] = (tuned || g.pieces[0]).itemInstanceId;
    });
    setKeepByGroup(initial);
  }

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setLoading(true);
    setError(null);
    setStatus(null);
    setScan(null);
    setKeepByGroup({});
    api
      .vaultClean()
      .then((res) => {
        if (!alive) return;
        setScan(res);
        seedKeeps(res);
      })
      .catch((e) => alive && setError((e as Error).message))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [open]);

  if (!open) return null;

  async function vaultOthers(
    key: string,
    pieces: { itemInstanceId: string; name: string; location: string }[]
  ) {
    const keepId = keepByGroup[key];
    if (!keepId) return;
    const toVault = pieces.filter((p) => p.itemInstanceId !== keepId && p.location !== "vault");
    const alreadyVaulted = pieces.filter(
      (p) => p.itemInstanceId !== keepId && p.location === "vault"
    );
    if (!toVault.length && alreadyVaulted.length) {
      setStatus(
        "The other copies are already in the Vault. Dismantle them in-game if you want them gone."
      );
      return;
    }
    if (!toVault.length) {
      setStatus("Nothing to vault for this group.");
      return;
    }
    setVaulting(key);
    setStatus(null);
    const errors: string[] = [];
    let moved = 0;
    for (const p of toVault) {
      try {
        await api.moveItem({ itemInstanceId: p.itemInstanceId, toStore: "vault" });
        moved += 1;
      } catch (e) {
        errors.push(`${p.name}: ${(e as Error).message}`);
      }
    }
    setVaulting(null);
    if (errors.length) setStatus(`Vaulted ${moved}. Issues: ${errors.slice(0, 2).join("; ")}`);
    else setStatus(`Vaulted ${moved} duplicate(s). Kept the selected piece.`);
    onVaulted();
    try {
      const res = await api.vaultClean();
      setScan(res);
      seedKeeps(res);
    } catch {
      /* ignore */
    }
  }

  const weaponGroups = scan?.weapons.groups || [];
  const armorGroups = scan?.armor.groups || [];

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-16 bg-black/70 overflow-y-auto">
      <div className="w-full max-w-3xl rounded-lg border border-white/15 bg-[#12151c] shadow-xl">
        <div className="flex items-start gap-3 px-4 py-3 border-b border-white/10">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold text-white">Vault cleaner</h2>
            <p className="text-xs text-white/50 mt-0.5">
              Find weapon + armor duplicates. Keep the best roll (god rolls / tuning), vault the rest.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-2 py-1 rounded text-white/50 hover:text-white hover:bg-white/10"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="px-4 pt-3 flex gap-1">
          {(
            [
              ["weapons", `Weapons (${weaponGroups.length})`],
              ["armor", `Armor (${armorGroups.length})`],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`px-3 py-1.5 rounded text-sm ${
                tab === id ? "bg-white/15 text-white" : "text-white/50 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="p-4 space-y-4 max-h-[70vh] overflow-y-auto">
          {loading && <p className="text-sm text-white/50">Scanning vault…</p>}
          {error && <p className="text-sm text-red-400">{error}</p>}
          {status && <p className="text-sm text-emerald-300">{status}</p>}

          {scan && !loading && tab === "weapons" && (
            <>
              <p className="text-xs text-white/40">
                Scanned {scan.weapons.scanned} weapons · {scan.weapons.groupCount} duplicate group
                {scan.weapons.groupCount === 1 ? "" : "s"}
              </p>
              {weaponGroups.length === 0 && (
                <p className="text-sm text-white/50 py-6 text-center">No duplicate weapons found.</p>
              )}
              {weaponGroups.map((group: WeaponDupeGroup, gi: number) => {
                const key = `w-${gi}`;
                return (
                  <div
                    key={group.itemHash + "-" + gi}
                    className="rounded border border-white/10 bg-white/[0.03] overflow-hidden"
                  >
                    <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-white/[0.04] border-b border-white/10">
                      {group.icon && (
                        <img src={group.icon} alt="" className="w-7 h-7 rounded border border-white/15" />
                      )}
                      <span className="text-sm text-white/80">{group.name}</span>
                      <span className="text-xs text-white/35 capitalize">{group.slot}</span>
                      <span className="text-xs text-white/35">{group.count} copies</span>
                      {group.hasGodRoll && (
                        <span className="text-[10px] font-black px-1.5 py-0.5 rounded bg-[#f5dc56] text-black">
                          HAS GOD ROLL
                        </span>
                      )}
                      {group.wishlistDiffers && (
                        <span className="text-[10px] uppercase tracking-wide text-amber-300/90 bg-amber-400/10 px-1.5 py-0.5 rounded">
                          Rolls differ
                        </span>
                      )}
                    </div>
                    <div className="divide-y divide-white/5">
                      {group.pieces.map((p: WeaponDupePiece) => {
                        const selected = keepByGroup[key] === p.itemInstanceId;
                        return (
                          <label
                            key={p.itemInstanceId}
                            className={`flex items-center gap-3 px-3 py-2 cursor-pointer ${
                              selected ? "bg-exotic/10" : "hover:bg-white/[0.04]"
                            }`}
                          >
                            <input
                              type="radio"
                              name={`dupe-${key}`}
                              checked={selected}
                              onChange={() =>
                                setKeepByGroup((prev) => ({ ...prev, [key]: p.itemInstanceId }))
                              }
                              className="accent-[#ceae33]"
                            />
                            {p.icon && (
                              <img
                                src={p.icon}
                                alt=""
                                className="w-10 h-10 rounded border border-white/15 object-cover shrink-0"
                              />
                            )}
                            <div className="min-w-0 flex-1">
                              <div className="text-sm truncate flex items-center gap-2 flex-wrap">
                                <span className={p.isExotic ? "text-exotic" : ""}>{p.name}</span>
                                {p.power != null && (
                                  <span className="text-white/40 tabular-nums">{p.power}</span>
                                )}
                                {wlBadge(p.wishlist?.tier)}
                                {selected && (
                                  <span className="text-[10px] uppercase text-exotic">Keep</span>
                                )}
                              </div>
                              <div className="text-[11px] text-white/45 truncate">
                                {locLabelItem(p)}
                                {p.isMasterwork ? " · Masterwork" : ""}
                                {p.wishlist?.matched_perks
                                  ? ` · ${p.wishlist.matched_perks}/${p.wishlist.needed_perks || "?"} wishlist perks`
                                  : ""}
                                {p.wishlist?.notes ? ` · ${p.wishlist.notes}` : ""}
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                    <div className="px-3 py-2 border-t border-white/10 flex justify-end">
                      <button
                        type="button"
                        disabled={vaulting === key || !keepByGroup[key]}
                        onClick={() => vaultOthers(key, group.pieces)}
                        className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/15 text-sm disabled:opacity-40"
                      >
                        {vaulting === key ? "Vaulting…" : "Vault the others"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {scan && !loading && tab === "armor" && (
            <>
              <p className="text-xs text-white/40">
                Scanned {scan.armor.scanned} Armor 3.0 pieces · {scan.armor.groupCount} duplicate
                group{scan.armor.groupCount === 1 ? "" : "s"}
              </p>
              {armorGroups.length === 0 && (
                <p className="text-sm text-white/50 py-6 text-center">
                  No duplicate armor base rolls found.
                </p>
              )}
              {armorGroups.map((group: ArmorDupeGroup, gi: number) => {
                const key = `a-${gi}`;
                return (
                  <div
                    key={`${group.classType}-${group.slot}-${gi}`}
                    className="rounded border border-white/10 bg-white/[0.03] overflow-hidden"
                  >
                    <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-white/[0.04] border-b border-white/10">
                      <ClassIcon classType={group.classType} className="w-3.5 h-3.5 text-white/60" />
                      <span className="text-sm capitalize text-white/80">
                        {group.classType} · {SLOT_LABELS[group.slot] || group.slot}
                      </span>
                      {group.archetype?.name && (
                        <span className="text-xs text-exotic/90">{group.archetype.name}</span>
                      )}
                      <span className="text-xs text-white/35">{group.count} copies</span>
                      {group.tuningDiffers && (
                        <span className="text-[10px] uppercase tracking-wide text-amber-300/90 bg-amber-400/10 px-1.5 py-0.5 rounded">
                          Tuning differs
                        </span>
                      )}
                      <div className="ml-auto flex flex-wrap gap-1 text-[11px] tabular-nums text-white/55">
                        {(scan.armor.statOrder || Object.keys(group.rollStats)).map((s) => (
                          <span key={s} title={s}>
                            {s.slice(0, 1)}
                            <span className="text-white/80">{group.rollStats[s] ?? 0}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="divide-y divide-white/5">
                      {group.pieces.map((p: ArmorDupePiece) => {
                        const selected = keepByGroup[key] === p.itemInstanceId;
                        return (
                          <label
                            key={p.itemInstanceId}
                            className={`flex items-center gap-3 px-3 py-2 cursor-pointer ${
                              selected ? "bg-exotic/10" : "hover:bg-white/[0.04]"
                            }`}
                          >
                            <input
                              type="radio"
                              name={`dupe-${key}`}
                              checked={selected}
                              onChange={() =>
                                setKeepByGroup((prev) => ({ ...prev, [key]: p.itemInstanceId }))
                              }
                              className="accent-[#ceae33]"
                            />
                            {p.icon && (
                              <img
                                src={p.icon}
                                alt=""
                                className="w-10 h-10 rounded border border-white/15 object-cover shrink-0"
                              />
                            )}
                            <div className="min-w-0 flex-1">
                              <div className="text-sm truncate">
                                <span className={p.isExotic ? "text-exotic" : ""}>{p.name}</span>
                                {p.power != null && (
                                  <span className="text-white/40 ml-1.5 tabular-nums">{p.power}</span>
                                )}
                                {selected && (
                                  <span className="ml-2 text-[10px] uppercase text-exotic">Keep</span>
                                )}
                              </div>
                              <div className="text-[11px] text-white/45 truncate">
                                {locLabelItem(p)}
                                {p.isMasterwork ? " · Masterwork" : ""}
                              </div>
                            </div>
                            <div
                              className="shrink-0 flex items-center gap-1.5 max-w-[11rem]"
                              title={p.tuning?.name || "No tuning socket"}
                            >
                              {p.tuning?.icon && (
                                <img
                                  src={p.tuning.icon}
                                  alt=""
                                  className="w-7 h-7 rounded border border-white/15 object-cover"
                                />
                              )}
                              <span
                                className={`text-[11px] leading-tight ${
                                  p.tuning && !p.tuning.isEmpty ? "text-emerald-300" : "text-white/40"
                                }`}
                              >
                                {p.tuning?.name || "No tuning"}
                              </span>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                    <div className="px-3 py-2 border-t border-white/10 flex justify-end">
                      <button
                        type="button"
                        disabled={vaulting === key || !keepByGroup[key]}
                        onClick={() => vaultOthers(key, group.pieces)}
                        className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/15 text-sm disabled:opacity-40"
                      >
                        {vaulting === key ? "Vaulting…" : "Vault the others"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

type StoreItems = { equipped: Record<string, Item[]>; carried: Record<string, Item[]> };

export default function Inventory({ authed }: { authed: boolean }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<Item | null>(null);
  const [dupeOpen, setDupeOpen] = useState(false);
  const [activeItem, setActiveItem] = useState<Item | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      // Small move before drag so clicks still open item detail.
      activationConstraint: { distance: 6 },
    })
  );

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setProfile(await api.profile());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (authed) load();
  }, [authed]);

  // Per-character equipped/carried maps, plus the vault, all keyed by bucket.
  // Search greys out non-matches instead of hiding them.
  const { byChar, vault } = useMemo(() => {
    const byChar: Record<string, StoreItems> = {};
    const vault: Record<string, Item[]> = {};
    if (profile) {
      for (const c of profile.characters) byChar[c.characterId] = { equipped: {}, carried: {} };
      for (const i of profile.items) {
        const key = bucketKey(i);
        if (!key) continue;
        if (i.location === "vault") {
          (vault[key] ||= []).push(i);
        } else if (i.characterId && byChar[i.characterId]) {
          const store = byChar[i.characterId];
          const target = i.location === "equipped" ? store.equipped : store.carried;
          (target[key] ||= []).push(i);
        }
      }
    }
    return { byChar, vault };
  }, [profile]);

  const searching = search.trim().length > 0;
  const isDimmed = (i: Item) => searching && !matchesQuery(i, search);

  const vaultCount = useMemo(
    () => (profile?.items || []).filter((i) => i.location === "vault").length,
    [profile]
  );

  // Class order follows character order (like DIM), then leftovers.
  const classOrder = useMemo(() => {
    const order: string[] = [];
    for (const c of profile?.characters || []) {
      if (!order.includes(c.classType)) order.push(c.classType);
    }
    for (const cl of ["titan", "hunter", "warlock"]) if (!order.includes(cl)) order.push(cl);
    return order;
  }, [profile]);

  /** Instantly move an item in local state so empty slots open like DIM. */
  function optimisticMove(item: Item, toStore: string) {
    setProfile((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((i) => {
          if (i.itemInstanceId !== item.itemInstanceId) return i;
          if (toStore === "vault") {
            return { ...i, location: "vault", characterId: null };
          }
          // Onto a character inventory (not equipped).
          return { ...i, location: "character", characterId: toStore };
        }),
      };
    });
  }

  function optimisticEquip(item: Item, characterId: string) {
    setProfile((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((i) => {
          if (i.itemInstanceId === item.itemInstanceId) {
            return { ...i, location: "equipped", characterId };
          }
          // Swap: previous equipped in same slot becomes carried.
          if (
            i.location === "equipped" &&
            i.characterId === characterId &&
            i.kind === item.kind &&
            i.slot === item.slot
          ) {
            return { ...i, location: "character" };
          }
          return i;
        }),
      };
    });
  }

  async function runAction(fn: () => Promise<{ message: string }>, opts?: { reload?: boolean }) {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await fn();
      setActionMsg(res.message);
      // Optimistic UI already updated — skip full profile reload (that was the sticky lag).
      if (opts?.reload) await load();
    } catch (e) {
      setActionMsg("Action failed: " + (e as Error).message);
      await load();
    } finally {
      setBusy(false);
    }
  }

  function transferMove(item: Item, toStore: string) {
    if (!item.itemInstanceId) return;
    if (toStore === "vault" && item.location === "vault") return;
    if (toStore !== "vault" && item.location === "character" && item.characterId === toStore) {
      return;
    }
    optimisticMove(item, toStore);
    void runAction(() => api.moveItem({ itemInstanceId: item.itemInstanceId!, toStore }));
  }

  function transferEquip(item: Item, characterId: string) {
    if (!item.itemInstanceId) return;
    if (item.location === "equipped" && item.characterId === characterId) return;
    optimisticEquip(item, characterId);
    void runAction(() => api.equipItem({ itemInstanceId: item.itemInstanceId!, characterId }));
  }

  function onDragStart(event: DragStartEvent) {
    const item = event.active.data.current?.item as Item | undefined;
    setActiveItem(item || null);
  }

  function onDragEnd(event: DragEndEvent) {
    setActiveItem(null);
    const item = event.active.data.current?.item as Item | undefined;
    const over = event.over;
    if (!item?.itemInstanceId || !over) return;
    const data = over.data.current as
      | { kind: "move" | "equip"; toStore?: string; characterId?: string }
      | undefined;
    if (!data) return;
    if (data.kind === "equip" && data.characterId) {
      transferEquip(item, data.characterId);
      return;
    }
    if (data.kind === "move" && data.toStore) {
      transferMove(item, data.toStore);
    }
  }

  function onDragCancel() {
    setActiveItem(null);
  }

  if (!authed) return <p className="text-white/60">Log in to view your inventory.</p>;

  const characters = profile?.characters || [];
  // DIM: fixed character columns (equipped box + 3x3) + vault fills the rest.
  // 56px tiles: equipped ~64 + gap + 3*56 + 2*4 gaps + padding ≈ 280
  const gridCols = `repeat(${Math.max(characters.length, 1)}, 290px) minmax(320px, 1fr)`;
  const gridMinWidth = characters.length * 290 + 340;

  const SECTIONS = [
    { title: "", groups: TOP_GROUPS, top: true as const },
    { title: "WEAPONS", groups: WEAPON_GROUPS, top: false as const },
    { title: "ARMOR", groups: ARMOR_GROUPS, top: false as const },
  ];

  function CharCell({ character, group }: { character: Character; group: { key: string; label: string } }) {
    const store = byChar[character.characterId];
    const equipped = sortInventoryItems(store?.equipped[group.key] || []);
    const carried = sortInventoryItems(store?.carried[group.key] || []);
    const equipZone = `equip:${character.characterId}:${group.key}`;
    const cellZone = `char:${character.characterId}:${group.key}`;
    // In-game character inventory holds 9 items per bucket (+ 1 equipped).
    const MAX_INV = 9;
    const slots: (Item | null)[] = [...carried.slice(0, MAX_INV)];
    while (slots.length < MAX_INV) slots.push(null);

    return (
      <DropZone
        id={cellZone}
        data={{ kind: "move", toStore: character.characterId }}
        className="flex gap-2 p-2 min-w-0 rounded-sm"
        overClassName="bg-blue-500/10 ring-1 ring-blue-400/40"
      >
        <DropZone
          id={equipZone}
          data={{ kind: "equip", characterId: character.characterId }}
          className="shrink-0 p-1.5 rounded-sm border self-start bg-black/25 border-white/15"
          overClassName="!bg-exotic/15 !border-exotic/60"
          title="Equipped (drop to equip)"
        >
          {equipped.length ? (
            equipped.map((i) => (
              <Tile key={i.itemInstanceId} item={i} onSelect={setSelected} dimmed={isDimmed(i)} />
            ))
          ) : (
            <div className={`box-border ${TILE_SIZE} border border-dashed border-white/20`} />
          )}
        </DropZone>

        <div className="grid grid-cols-3 gap-1 p-1.5 rounded-sm bg-black/20 border border-white/10 content-start w-max">
          {slots.map((i, idx) =>
            i ? (
              <Tile
                key={(i.itemInstanceId || i.itemHash) + i.location + idx}
                item={i}
                onSelect={setSelected}
                dimmed={isDimmed(i)}
              />
            ) : (
              <div
                key={`empty-${idx}`}
                className={`box-border ${TILE_SIZE} border border-dashed border-white/10 bg-white/[0.02]`}
              />
            )
          )}
        </div>
      </DropZone>
    );
  }

  // Postmaster / Engrams — always shown above weapons (DIM), even when empty.
  function TopCell({
    character,
    group,
  }: {
    character: Character;
    group: { key: string; label: string };
  }) {
    const store = byChar[character.characterId];
    const items = [...(store?.carried[group.key] || []), ...(store?.equipped[group.key] || [])];
    const cellZone = `char:${character.characterId}:${group.key}`;
    return (
      <DropZone
        id={cellZone}
        data={{ kind: "move", toStore: character.characterId }}
        className="flex flex-wrap gap-1 p-2 content-start min-h-[3.5rem] rounded"
        overClassName="bg-blue-500/10 ring-1 ring-blue-400/40"
      >
        <div className="w-full text-[10px] uppercase tracking-wide text-white/45 mb-0.5">
          {group.label}{" "}
          <span className="text-white/25">({items.length})</span>
        </div>
        {items.map((i) => (
          <Tile
            key={(i.itemInstanceId || i.itemHash) + i.location}
            item={i}
            onSelect={setSelected}
            dimmed={isDimmed(i)}
          />
        ))}
        {items.length === 0 && (
          <div className={`box-border ${TILE_SIZE} border border-dashed border-white/10 bg-white/[0.02]`} />
        )}
      </DropZone>
    );
  }

  function VaultCell({ group, isArmor }: { group: { key: string; label: string }; isArmor: boolean }) {
    const items = sortInventoryItems(vault[group.key] || []);
    const zone = `vault:${group.key}`;
    const base = "p-2 pl-2 border-l border-white/10 min-w-0 min-h-[11.5rem] rounded";
    const over = "bg-blue-500/10 ring-1 ring-blue-400/40";

    if (!isArmor) {
      return (
        <DropZone
          id={zone}
          data={{ kind: "move", toStore: "vault" }}
          className={`flex flex-wrap gap-1 content-start ${base}`}
          overClassName={over}
        >
          {items.map((i) => (
            <Tile
              key={(i.itemInstanceId || i.itemHash) + i.location}
              item={i}
              onSelect={setSelected}
              dimmed={isDimmed(i)}
            />
          ))}
          {items.length === 0 && (
            <div className="text-[10px] text-white/25 self-center py-8 w-full text-center">
              Drop here
            </div>
          )}
        </DropZone>
      );
    }

    const grouped: Record<string, Item[]> = {};
    for (const i of items) (grouped[i.classType] ||= []).push(i);
    for (const cl of Object.keys(grouped)) grouped[cl] = sortInventoryItems(grouped[cl]);
    const classes = [
      ...classOrder.filter((cl) => (grouped[cl] || []).length > 0),
      ...Object.keys(grouped).filter((cl) => !classOrder.includes(cl) && grouped[cl].length),
    ];

    return (
      <DropZone
        id={zone}
        data={{ kind: "move", toStore: "vault" }}
        className={base}
        overClassName={over}
      >
        <div className="space-y-1">
          {classes.map((cl) => (
            <div key={cl} className="flex items-start gap-1.5">
              <div
                className="w-4 shrink-0 flex justify-center pt-1.5 text-white/45"
                title={CLASS_LABELS[cl] || cl}
              >
                {CLASS_ICON_PATHS[cl] ? (
                  <ClassIcon classType={cl} className="w-3.5 h-3.5" />
                ) : (
                  <span className="text-[9px]">×</span>
                )}
              </div>
              <div className="flex flex-wrap gap-1 content-start min-w-0">
                {(grouped[cl] || []).map((i) => (
                  <Tile
                    key={(i.itemInstanceId || i.itemHash) + i.location}
                    item={i}
                    onSelect={setSelected}
                    dimmed={isDimmed(i)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </DropZone>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={pointerWithin}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={onDragCancel}
    >
    <div>
      {/* Sticky search — outside any overflow-x container so it sticks to the viewport */}
      <div className="sticky top-14 z-30 -mx-4 lg:-mx-6 px-4 lg:px-6 py-2 mb-2 bg-[#0b0e14]/95 backdrop-blur border-b border-white/10">
        <div className="flex flex-wrap items-center gap-2 max-w-[1800px] mx-auto">
          <button onClick={load} className="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-sm shrink-0">
            {loading ? "Loading…" : "Reload"}
          </button>
          <button
            type="button"
            onClick={() => setDupeOpen(true)}
            disabled={!authed || loading}
            className="px-3 py-1.5 rounded bg-exotic/90 text-black text-sm font-medium shrink-0 disabled:opacity-40"
            title="Find duplicate weapons and armor for vault cleaning"
          >
            Vault cleaner
          </button>
          <div className="relative flex-1 min-w-[220px] max-w-xl">
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40 pointer-events-none"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.5-3.5" />
            </svg>
            <input
              placeholder="Search item/perk  is:exotic is:masterwork is:armor is:hunter…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-9 py-2 rounded bg-white/5 border border-white/15 text-sm focus:outline-none focus:border-white/35"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 w-6 h-6 rounded text-white/50 hover:text-white hover:bg-white/10"
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>
          {busy && <span className="text-sm text-white/50">Working…</span>}
          <span className="text-xs text-white/35 ml-auto shrink-0">Vault {vaultCount}</span>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}
      {actionMsg && (
        <p
          className={`text-sm mb-3 ${
            actionMsg.startsWith("Action failed") ? "text-red-400" : "text-green-400"
          }`}
        >
          {actionMsg}
        </p>
      )}

      {profile && (
        // No overflow-x-auto here — that breaks position:sticky vs the page scroll.
        // Wide grids scroll with the document instead.
        <div style={{ minWidth: gridMinWidth }}>
          <div
            className="grid gap-x-2 mb-2 sticky top-[7.25rem] z-20 bg-[#0b0e14] py-1 border-b border-white/10"
            style={{ gridTemplateColumns: gridCols }}
          >
            {characters.map((c) => (
              <CharacterHeader key={c.characterId} character={c} />
            ))}
            <div className="flex items-center h-14 pl-3 border-l border-white/10 font-semibold text-sm bg-[#0b0e14]">
              Vault <span className="text-white/40 font-normal ml-1">({vaultCount})</span>
            </div>
          </div>

          {SECTIONS.map((section) => (
            <div key={section.title || "top"}>
              {section.title ? (
                <div className="text-xs font-semibold text-white/70 mt-3 mb-1 flex items-center gap-2">
                  {section.title}
                </div>
              ) : (
                <div className="mt-1" />
              )}
              <div className="grid gap-x-2 gap-y-1" style={{ gridTemplateColumns: gridCols }}>
                {section.groups.map((g) => (
                  <div key={g.key} className="contents">
                    {characters.map((c) =>
                      section.top ? (
                        <TopCell key={c.characterId + g.key} character={c} group={g} />
                      ) : (
                        <CharCell key={c.characterId + g.key} character={c} group={g} />
                      )
                    )}
                    {section.top ? (
                      <div className="border-l border-white/10 min-h-[3.5rem]" />
                    ) : (
                      <VaultCell group={g} isArmor={section.title === "ARMOR"} />
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {selected && <ItemDetailModal item={selected} onClose={() => setSelected(null)} />}
      <VaultCleanPanel
        open={dupeOpen}
        onClose={() => setDupeOpen(false)}
        onVaulted={() => load()}
      />
    </div>
    <DragOverlay dropAnimation={null}>
      {activeItem ? <TileFace item={activeItem} ghost /> : null}
    </DragOverlay>
    </DndContext>
  );
}
