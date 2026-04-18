import type { AmazonCategoryPreset } from './amazonCategories';

export type GlinerEntity = { text: string; label: string; score: number };

export type CompressedAmazonItem = {
  item_name: string;
  item_detail: string;
  item_reviews_summarized: string;
  item_review_evidence?: string[];
  item_review_source?: string;
  item_price: number | null;
  item_sold_quantity: number | null;
  item_rating: number | null;
  item_review_count: number | null;
  source_url: string | null;
  asin: string | null;
  gliner_entities: GlinerEntity[];
  item_entities_compact: string;
};

export type AmazonIngestResponse = {
  search_term: string;
  amazon_domain: string;
  amazon_rh: string | null;
  amazon_browse_node: string | null;
  amazon_category_preset: string | null;
  raw_organic_count: number;
  dropped_compliance_count: number;
  items: CompressedAmazonItem[];
  raw_preview: Record<string, unknown>[] | null;
};

export type AmazonIngestRequest = {
  query: string;
  max_products: number;
  amazon_domain?: string;
  include_raw_preview?: boolean;
  category_preset: AmazonCategoryPreset;
};

export async function postAmazonIngest(body: AmazonIngestRequest): Promise<AmazonIngestResponse> {
  const res = await fetch('/api/pipeline/amazon-ingest', {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: body.query,
      max_products: body.max_products,
      amazon_domain: body.amazon_domain ?? 'amazon.com',
      include_raw_preview: body.include_raw_preview ?? false,
      category_preset: body.category_preset,
    }),
  });
  const text = await res.text();
  let data: unknown;
  try {
    data = JSON.parse(text) as unknown;
  } catch {
    throw new Error(`Amazon ingest: invalid JSON (${res.status})`);
  }
  if (!res.ok) {
    const detail = (data as { detail?: string }).detail ?? text;
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`);
  }
  return data as AmazonIngestResponse;
}
