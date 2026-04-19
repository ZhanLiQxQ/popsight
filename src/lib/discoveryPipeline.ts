import type { CompressedAmazonItem, GlinerEntity } from './amazonPipeline';

export type ProductPriority = 'HIGH' | 'MEDIUM' | 'LOW';

export type RankedProduct = {
  product_name: string;
  category: string;
  priority: ProductPriority;
  reason: string;
  external_sold_quantity: number;
  item_price: number | null;
  item_review_summarized: string;
  internal_match: boolean;
  internal_sales_velocity: number | null;
  inventory_health: number | null;
  catalog_rag_hit: boolean;
  rank_score: number;
};

export type ActionableProduct = {
  product_name: string;
  category: string;
  priority: ProductPriority;
  reason: string;
  supplier: string | null;
  supplier_region: string | null;
  estimated_cost: number | null;
  external_sold_quantity: number;
  rank_score: number;
  needs_vendor_development: boolean;
};

/**
 * Merged view for the UI: one row combining Node 4 (rank) + Node 5 (supply) + Node 3 (compress + NER).
 * This is what the user sees as a "trendy product" card; everything needed for the detail view lives here.
 */
export type TrendyProduct = {
  id: string;
  product_name: string;
  category: string;
  priority: ProductPriority;
  reason: string;
  rank_score: number;
  external_sold_quantity: number;
  item_price: number | null;
  item_rating: number | null;
  item_review_count: number | null;
  item_sold_quantity: number | null;
  item_detail: string;
  item_review_summarized: string;
  item_review_evidence: string[];
  item_review_source: string;
  source_url: string | null;
  asin: string | null;
  gliner_entities: GlinerEntity[];
  item_entities_compact: string;
  internal_match: boolean;
  internal_sales_velocity: number | null;
  inventory_health: number | null;
  supplier: string | null;
  supplier_region: string | null;
  estimated_cost: number | null;
  needs_vendor_development: boolean;
  is_actionable: boolean;
};

/** Must match backend `DiscoveryLaneId` enum. */
export const DISCOVERY_LANE_OPTIONS = [
  { id: 'asian_snacks', label: 'Asian Snacks' },
  { id: 'functional_beverages', label: 'Functional Beverages' },
  { id: 'pantry_staples_asia', label: 'Pantry Staples Asia' },
  { id: 'instant_noodles_premium', label: 'Instant Noodles Premium' },
  { id: 'herbal_tea_drinks', label: 'Herbal Tea Drinks' },
  { id: 'better_for_you_candy', label: 'Better For You Candy' },
] as const;

export type DiscoveryLaneId = (typeof DISCOVERY_LANE_OPTIONS)[number]['id'];

export type DiscoveryLaneResult = {
  categoryId: string;
  categoryLabel: string;
  trendsSeed: string;
  googleTrendsSignals: Record<string, unknown>[];
  amazonSearchTerms: { category: string; search_term: string }[];
  rawAmazonData: Record<string, unknown>[];
  compressedItems: CompressedAmazonItem[];
};

export type MacroColdStartResponse = {
  lanes: DiscoveryLaneResult[];
  googleTrendsSignals: Record<string, unknown>[];
  amazonSearchTerms: { category: string; search_term: string }[];
  rawAmazonData: Record<string, unknown>[];
  compressedItems: CompressedAmazonItem[];
  rankedProductList: Record<string, unknown>[];
  finalActionableList: Record<string, unknown>[];
  executiveSummary: string;
  discoveryAborted?: boolean;
  discoveryAbortReason?: string | null;
};

export type MacroColdStartRequestBody = {
  userId?: string;
  googleTrendsGeo?: string;
  amazonDomain?: string;
  /** Omit or empty → all six lanes. */
  discoveryLaneIds?: DiscoveryLaneId[];
};

function asRecord(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

/** Coerce one compressed row (snake_case from API) into the UI shape. */
export function normalizeCompressedItem(x: unknown): CompressedAmazonItem | null {
  const o = asRecord(x);
  if (!o) return null;
  const item_name = String(o.item_name ?? o.itemName ?? '').trim();
  if (!item_name) return null;
  const ev = o.item_review_evidence ?? o.itemReviewEvidence;
  const evidence = Array.isArray(ev) ? ev.map((s) => String(s)) : [];
  const entitiesRaw = o.gliner_entities ?? o.glinerEntities;
  const gliner_entities: CompressedAmazonItem['gliner_entities'] = [];
  if (Array.isArray(entitiesRaw)) {
    for (const e of entitiesRaw) {
      const er = asRecord(e);
      if (!er) continue;
      const text = String(er.text ?? '').trim();
      const label = String(er.label ?? '').trim();
      if (!text || !label) continue;
      const score = typeof er.score === 'number' ? er.score : Number(er.score) || 0;
      gliner_entities.push({ text, label, score });
    }
  }
  return {
    item_name,
    item_detail: String(o.item_detail ?? o.itemDetail ?? ''),
    item_reviews_summarized: String(o.item_reviews_summarized ?? o.itemReviewsSummarized ?? ''),
    item_review_evidence: evidence,
    item_review_source: String(o.item_review_source ?? o.itemReviewSource ?? 'amazon_search_serp_snippets'),
    item_price: typeof o.item_price === 'number' ? o.item_price : o.item_price != null ? Number(o.item_price) : null,
    item_sold_quantity:
      typeof o.item_sold_quantity === 'number'
        ? o.item_sold_quantity
        : o.item_sold_quantity != null
          ? Number(o.item_sold_quantity)
          : null,
    item_rating:
      typeof o.item_rating === 'number' ? o.item_rating : o.item_rating != null ? Number(o.item_rating) : null,
    item_review_count:
      typeof o.item_review_count === 'number'
        ? o.item_review_count
        : o.item_review_count != null
          ? Number(o.item_review_count)
          : null,
    source_url: (o.source_url ?? o.sourceUrl ?? null) as string | null,
    asin: (o.asin ?? null) as string | null,
    gliner_entities,
    item_entities_compact: String(o.item_entities_compact ?? o.itemEntitiesCompact ?? ''),
  };
}

function normalizeLane(raw: unknown): DiscoveryLaneResult {
  const r = asRecord(raw) ?? {};
  const signals = (r.googleTrendsSignals ?? r.google_trends_signals ?? []) as Record<string, unknown>[];
  const terms = (r.amazonSearchTerms ?? r.amazon_search_terms ?? []) as DiscoveryLaneResult['amazonSearchTerms'];
  const rawAmazon = (r.rawAmazonData ?? r.raw_amazon_data ?? []) as Record<string, unknown>[];
  const itemsRaw = r.compressedItems ?? r.compressed_items;
  const compressedItems: CompressedAmazonItem[] = [];
  if (Array.isArray(itemsRaw)) {
    for (const row of itemsRaw) {
      const it = normalizeCompressedItem(row);
      if (it) compressedItems.push(it);
    }
  }
  return {
    categoryId: String(r.categoryId ?? r.category_id ?? ''),
    categoryLabel: String(r.categoryLabel ?? r.category_label ?? ''),
    trendsSeed: String(r.trendsSeed ?? r.trends_seed ?? ''),
    googleTrendsSignals: Array.isArray(signals) ? signals : [],
    amazonSearchTerms: Array.isArray(terms) ? terms : [],
    rawAmazonData: Array.isArray(rawAmazon) ? rawAmazon : [],
    compressedItems,
  };
}

/** Normalize API JSON (handles snake_case lane keys if present). */
export function normalizeMacroColdStartResponse(raw: unknown): MacroColdStartResponse {
  const r = asRecord(raw);
  if (!r) {
    return {
      lanes: [],
      googleTrendsSignals: [],
      amazonSearchTerms: [],
      rawAmazonData: [],
      compressedItems: [],
      rankedProductList: [],
      finalActionableList: [],
      executiveSummary: '',
      discoveryAborted: false,
      discoveryAbortReason: null,
    };
  }
  const lanesRaw = r.lanes;
  const lanes = Array.isArray(lanesRaw) ? lanesRaw.map(normalizeLane) : [];
  const flatRaw = r.compressedItems ?? r.compressed_items;
  const flat: CompressedAmazonItem[] = [];
  if (Array.isArray(flatRaw)) {
    for (const row of flatRaw) {
      const it = normalizeCompressedItem(row);
      if (it) flat.push(it);
    }
  }
  return {
    lanes,
    googleTrendsSignals: (r.googleTrendsSignals ?? r.google_trends_signals ?? []) as Record<string, unknown>[],
    amazonSearchTerms: (r.amazonSearchTerms ?? r.amazon_search_terms ?? []) as MacroColdStartResponse['amazonSearchTerms'],
    rawAmazonData: (r.rawAmazonData ?? r.raw_amazon_data ?? []) as Record<string, unknown>[],
    compressedItems: flat,
    rankedProductList: (r.rankedProductList ?? r.ranked_product_list ?? []) as Record<string, unknown>[],
    finalActionableList: (r.finalActionableList ?? r.final_actionable_list ?? []) as Record<string, unknown>[],
    executiveSummary: String(r.executiveSummary ?? r.executive_summary ?? ''),
    discoveryAborted: Boolean(r.discoveryAborted ?? r.discovery_aborted),
    discoveryAbortReason: (r.discoveryAbortReason ?? r.discovery_abort_reason ?? null) as string | null,
  };
}

function normalizePriority(raw: unknown): ProductPriority {
  const s = String(raw ?? '').toUpperCase();
  return s === 'HIGH' || s === 'MEDIUM' ? (s as ProductPriority) : 'LOW';
}

function toNumberOrNull(v: unknown): number | null {
  if (typeof v === 'number') return v;
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function normalizeKey(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, ' ');
}

/**
 * Merge Node 4 (ranked) + Node 5 (actionable) + Node 3 (compressed + NER) for the selected lane
 * into a single list the UI can render as product cards with a detail view.
 *
 * Matching is done by case-insensitive product_name so backend dicts don't need to carry shared IDs.
 */
export function buildTrendyProducts(
  response: MacroColdStartResponse,
  laneId: string,
): TrendyProduct[] {
  const lane = response.lanes.find((l) => l.categoryId === laneId);
  if (!lane) return [];

  const laneLabel = lane.categoryLabel;
  const laneLabelKey = normalizeKey(laneLabel);

  const compressedByName = new Map<string, CompressedAmazonItem>();
  for (const item of lane.compressedItems) {
    compressedByName.set(normalizeKey(item.item_name), item);
  }

  const actionableByName = new Map<string, Record<string, unknown>>();
  for (const raw of response.finalActionableList) {
    const r = asRecord(raw);
    if (!r) continue;
    const cat = String(r.category ?? '').trim();
    if (cat && normalizeKey(cat) !== laneLabelKey) continue;
    const name = String(r.product_name ?? '').trim();
    if (!name) continue;
    actionableByName.set(normalizeKey(name), r);
  }

  const priorityOrder: Record<ProductPriority, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };
  const merged: TrendyProduct[] = [];

  for (const raw of response.rankedProductList) {
    const r = asRecord(raw);
    if (!r) continue;

    const cat = String(r.category ?? '').trim();
    if (cat && normalizeKey(cat) !== laneLabelKey) continue;

    const name = String(r.product_name ?? '').trim();
    if (!name) continue;

    const nameKey = normalizeKey(name);
    const compressed = compressedByName.get(nameKey) ?? null;
    const actionable = actionableByName.get(nameKey) ?? null;

    const priority = normalizePriority(r.priority);
    const rank_score = toNumberOrNull(r.rank_score) ?? 0;

    merged.push({
      id: `${nameKey}::${compressed?.asin ?? merged.length}`,
      product_name: name,
      category: cat || laneLabel,
      priority,
      reason: String(r.reason ?? ''),
      rank_score,
      external_sold_quantity: toNumberOrNull(r.external_sold_quantity) ?? 0,
      item_price: toNumberOrNull(r.item_price) ?? compressed?.item_price ?? null,
      item_rating: compressed?.item_rating ?? null,
      item_review_count: compressed?.item_review_count ?? null,
      item_sold_quantity: compressed?.item_sold_quantity ?? null,
      item_detail: compressed?.item_detail ?? '',
      item_review_summarized:
        String(r.item_review_summarized ?? '') || (compressed?.item_reviews_summarized ?? ''),
      item_review_evidence: compressed?.item_review_evidence ?? [],
      item_review_source: compressed?.item_review_source ?? '',
      source_url: compressed?.source_url ?? null,
      asin: compressed?.asin ?? null,
      gliner_entities: compressed?.gliner_entities ?? [],
      item_entities_compact: compressed?.item_entities_compact ?? '',
      internal_match: Boolean(r.internal_match),
      internal_sales_velocity: toNumberOrNull(r.internal_sales_velocity),
      inventory_health: toNumberOrNull(r.inventory_health),
      supplier: actionable ? String(actionable.supplier ?? '') || null : null,
      supplier_region: actionable ? String(actionable.supplier_region ?? '') || null : null,
      estimated_cost: actionable ? toNumberOrNull(actionable.estimated_cost) : null,
      needs_vendor_development: Boolean(actionable?.needs_vendor_development),
      is_actionable: actionable !== null,
    });
  }

  merged.sort((a, b) => {
    const p = priorityOrder[a.priority] - priorityOrder[b.priority];
    if (p !== 0) return p;
    return b.rank_score - a.rank_score;
  });

  return merged;
}

export async function postMacroColdStart(body: MacroColdStartRequestBody): Promise<MacroColdStartResponse> {
  const res = await fetch('/api/pipeline/macro-cold-start', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({
      userId: body.userId ?? 'default-user',
      googleTrendsGeo: body.googleTrendsGeo ?? 'US',
      amazonDomain: body.amazonDomain ?? 'amazon.com',
      ...(body.discoveryLaneIds && body.discoveryLaneIds.length > 0
        ? { discoveryLaneIds: body.discoveryLaneIds }
        : {}),
    }),
  });
  const text = await res.text();
  let data: unknown;
  try {
    data = JSON.parse(text) as unknown;
  } catch {
    throw new Error(`Discovery pipeline: invalid JSON (${res.status})`);
  }
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail ?? text;
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`);
  }
  return normalizeMacroColdStartResponse(data);
}
