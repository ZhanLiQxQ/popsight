import type { CompressedAmazonItem } from './amazonPipeline';

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
