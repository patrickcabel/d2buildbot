const BASE = "http://localhost:8000";

async function req<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json();
}

export interface AuthStatus {
  configured: boolean;
  authenticated: boolean;
  membershipId: string | null;
}

export interface Item {
  itemHash: number;
  itemInstanceId: string | null;
  name: string;
  icon: string | null;
  kind: string | null;
  slot: string | null;
  tier: string;
  isExotic: boolean;
  ammoType: string;
  classType: string;
  location: string;
  power?: number | null;
  perks?: number[] | null;
}

export interface Character {
  characterId: string;
  classType: string;
  light: number | null;
  emblemPath: string | null;
}

export interface Profile {
  membership: { display_name?: string; bungie_global_display_name?: string };
  characters: Character[];
  items: Item[];
}

export interface ReferenceSummary {
  id: number;
  source_type: string;
  url: string;
  title: string | null;
  status: string;
  error: string | null;
  fetched_at: number | null;
  fact_count: number;
}

export interface Fact {
  entity_type: string;
  manifest_hash: number;
  name: string;
  mention_count: number;
  snippet: string | null;
}

export interface ReferenceDetail extends ReferenceSummary {
  facts: Fact[];
  raw_meta?: any;
}

export interface BuildItem extends Item {
  reason?: string;
  wishlist?: { is_wishlisted: boolean; matched_perks: number; notes: string | null };
}

export interface NamedRec {
  name: string;
  hash: number | null;
  sources: number;
  owned: boolean | null;
  from: string;
}

export interface Build {
  query: string;
  matched: boolean;
  exotic: { name: string; hash: number; type: string; owned: boolean } | null;
  classType: string;
  subclass: string | null;
  weapons: Record<string, BuildItem | null>;
  armor: Record<string, BuildItem | null>;
  aspects: NamedRec[];
  fragments: NamedRec[];
  mods: NamedRec[];
  statPriority: string[];
  rationale: string;
  references: { url: string; title: string; type: string }[];
  notes: string | null;
  dim: { search: string; url: string } | null;
}

export const api = {
  authStatus: () => req<AuthStatus>("/api/auth/status"),
  loginUrl: () => `${BASE}/api/auth/login`,
  logout: () => req("/api/auth/logout", { method: "POST" }),
  manifestStatus: () => req<{ version: string | null }>("/api/manifest/status"),
  syncManifest: (force = false) =>
    req<{ status: string; version: string }>(`/api/manifest/sync?force=${force}`, {
      method: "POST",
    }),
  profile: () => req<Profile>("/api/profile"),
  listReferences: () => req<{ references: ReferenceSummary[] }>("/api/references"),
  getReference: (id: number) => req<ReferenceDetail>(`/api/references/${id}`),
  addReference: (url: string) =>
    req<ReferenceDetail>("/api/references", { method: "POST", body: JSON.stringify({ url }) }),
  refreshReference: (id: number) =>
    req<ReferenceDetail>(`/api/references/${id}/refresh`, { method: "POST" }),
  deleteReference: (id: number) =>
    req(`/api/references/${id}`, { method: "DELETE" }),
  createBuild: (query: string) =>
    req<Build>("/api/builds", { method: "POST", body: JSON.stringify({ query }) }),
  wishlistStatus: () =>
    req<{ items: number; rolls: number; files: string[] }>("/api/wishlists/status"),
  downloadVoltron: () =>
    req<{ ok: boolean; bytes: number; items: number; rolls: number }>(
      "/api/wishlists/download-voltron",
      { method: "POST" }
    ),
};
