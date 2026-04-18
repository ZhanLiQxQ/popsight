import { useState } from 'react';
import { Radar, RefreshCw, Sparkles } from 'lucide-react';
import type { CompressedAmazonItem } from './lib/amazonPipeline';
import {
  DISCOVERY_LANE_OPTIONS,
  postMacroColdStart,
  type DiscoveryLaneId,
  type MacroColdStartResponse,
} from './lib/discoveryPipeline';

export default function App() {
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const [discoveryResult, setDiscoveryResult] = useState<MacroColdStartResponse | null>(null);
  const [discoveryLaneFilter, setDiscoveryLaneFilter] = useState<string>('');

  const handleRunDiscoveryColdStart = async () => {
    setDiscoveryLoading(true);
    setDiscoveryError(null);
    try {
      const data = await postMacroColdStart({
        userId: 'default-user',
        googleTrendsGeo: 'US',
        amazonDomain: 'amazon.com',
        discoveryLaneIds: discoveryLaneFilter ? [discoveryLaneFilter as DiscoveryLaneId] : undefined,
      });
      setDiscoveryResult(data);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Discovery pipeline failed';
      setDiscoveryError(message);
      setDiscoveryResult(null);
    } finally {
      setDiscoveryLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--bg-app)] text-[var(--ink-strong)]">
      <header className="border-b border-[var(--line-soft)] bg-white/90 px-8 py-6 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent-muted)] text-[var(--accent-deep)]">
              <Radar className="h-5 w-5" />
            </div>
            <div>
              <p className="text-lg font-semibold tracking-tight">PopSight</p>
              <p className="text-xs text-[var(--ink-soft)]">Discovery pipeline (Node 0 → Node 3)</p>
            </div>
          </div>
          <span className="rounded-full bg-[var(--bg-app)] px-3 py-1 text-xs text-[var(--ink-faint)]">
            {discoveryLoading ? 'Running…' : discoveryResult ? 'Results below' : 'Ready'}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-8 py-8">
        <section className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 shadow-[0_18px_50px_rgba(16,24,40,0.08)]">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">LangGraph</p>
              <h1 className="mt-1 text-xl font-semibold">Cold start: Node 0 → Node 3</h1>
              <p className="mt-1 max-w-3xl text-sm text-[var(--ink-soft)]">
                Google Trends (Node 0) → MacroScout terms (Node 1) → Amazon grocery Serp{' '}
                <code className="rounded bg-[var(--bg-app)] px-1 text-xs">rh=n:16310101</code> (Node 2) → FDA +
                compression + optional GLiNER (Node 3). Requires <code className="rounded bg-[var(--bg-app)] px-1 text-xs">SERPAPI_API_KEY</code>; Gemini recommended for Node 1.
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-[var(--ink-soft)]">
                <span className="uppercase tracking-[0.14em] text-[var(--ink-faint)]">Lane filter</span>
                <select
                  value={discoveryLaneFilter}
                  onChange={(e) => setDiscoveryLaneFilter(e.target.value)}
                  className="min-w-[220px] rounded-2xl border border-[var(--line-soft)] bg-white px-3 py-2 text-sm text-[var(--ink-strong)] outline-none focus:border-[var(--accent)]"
                >
                  <option value="">All six lanes</option>
                  {DISCOVERY_LANE_OPTIONS.map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                type="button"
                onClick={handleRunDiscoveryColdStart}
                disabled={discoveryLoading}
                className="inline-flex items-center gap-2 rounded-2xl bg-[var(--panel-strong)] px-5 py-2.5 text-sm font-medium text-white transition hover:brightness-110 disabled:opacity-50"
              >
                {discoveryLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Sparkles className="h-4 w-4" aria-hidden />
                )}
                Run pipeline
              </button>
            </div>
          </div>
          {discoveryError && (
            <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{discoveryError}</p>
          )}
        </section>

        {discoveryResult && (
          <div className="mt-8 space-y-6">
            {discoveryResult.discoveryAborted && (
              <div className="rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                <strong>Stopped after Node 0.</strong>{' '}
                {discoveryResult.discoveryAbortReason ??
                  'No usable Google Trends RELATED_QUERIES for any selected lane.'}{' '}
                MacroScout, Amazon crawl, and GLiNER were <strong>not</strong> run.
              </div>
            )}

            <div className="rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] px-4 py-3 text-sm text-[var(--ink-soft)]">
              <span className="font-medium text-[var(--ink-strong)]">Summary:</span>{' '}
              {discoveryResult.discoveryAborted ? (
                <>{(discoveryResult.lanes ?? []).length} lane(s) — downstream skipped.</>
              ) : (
                <>
                  {(discoveryResult.lanes ?? []).length} lane(s) ·{' '}
                  {(discoveryResult.compressedItems ?? []).length} compressed SKU row(s) (Node 3).
                </>
              )}
            </div>

            {!discoveryResult.discoveryAborted &&
              (discoveryResult.compressedItems ?? []).length > 0 &&
              (discoveryResult.lanes ?? []).every((l) => (l.compressedItems ?? []).length === 0) && (
                <>
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                    API returned <strong>{(discoveryResult.compressedItems ?? []).length}</strong> flat compressed item(s),
                    but per-lane buckets were empty. Showing flat Node 3 list below.
                  </div>
                  <section className="rounded-[28px] border border-[var(--line-soft)] bg-white p-6 shadow-sm">
                    <p className="mb-3 text-xs uppercase tracking-[0.2em] text-[var(--ink-faint)]">Node 3 — Compressed (flat)</p>
                    <div className="grid gap-3 md:grid-cols-2">
                      {(discoveryResult.compressedItems ?? []).map((item, index) => (
                        <DiscoveryCompressedCard
                          key={`flat-${item.asin ?? item.item_name}-${index}`}
                          item={item}
                        />
                      ))}
                    </div>
                  </section>
                </>
              )}

            {(discoveryResult.lanes ?? []).map((lane) => (
              <section
                key={lane.categoryId}
                className="rounded-[28px] border border-[var(--line-soft)] bg-white p-6 shadow-sm"
              >
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-[var(--ink-faint)]">Lane</p>
                    <h2 className="text-lg font-semibold text-[var(--ink-strong)]">{lane.categoryLabel}</h2>
                    <p className="text-xs text-[var(--ink-faint)]">
                      Trends seed: <span className="font-mono text-[var(--ink-soft)]">{lane.trendsSeed}</span>
                    </p>
                  </div>
                  <span className="rounded-full bg-[var(--accent-muted)] px-3 py-1 text-xs font-medium text-[var(--accent-deep)]">
                    {discoveryResult.discoveryAborted
                      ? 'Node 3: skipped'
                      : `Node 3: ${(lane.compressedItems ?? []).length} item(s)`}
                  </span>
                </div>

                <details className="mb-4 rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] px-4 py-3">
                  <summary className="cursor-pointer text-sm font-medium text-[var(--ink-strong)]">
                    Node 0 — Google Trends ({(lane.googleTrendsSignals ?? []).length})
                  </summary>
                  <pre className="mt-2 max-h-48 overflow-auto text-xs leading-relaxed text-[var(--ink-soft)]">
                    {JSON.stringify(lane.googleTrendsSignals ?? [], null, 2)}
                  </pre>
                </details>

                <details className="mb-5 rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] px-4 py-3">
                  <summary className="cursor-pointer text-sm font-medium text-[var(--ink-strong)]">
                    Node 1 — MacroScout terms ({(lane.amazonSearchTerms ?? []).length})
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-auto text-xs leading-relaxed text-[var(--ink-soft)]">
                    {JSON.stringify(lane.amazonSearchTerms ?? [], null, 2)}
                  </pre>
                </details>

                {(lane.compressedItems ?? []).length === 0 ? (
                  <EmptyState
                    text={
                      discoveryResult.discoveryAborted
                        ? 'Downstream skipped: no usable Google Trends queries for this lane.'
                        : 'No compressed items for this lane.'
                    }
                    compact
                  />
                ) : (
                  <div>
                    <p className="mb-3 text-xs uppercase tracking-[0.2em] text-[var(--ink-faint)]">Node 3 — Compressed</p>
                    <div className="grid gap-3 md:grid-cols-2">
                      {(lane.compressedItems ?? []).map((item, index) => (
                        <DiscoveryCompressedCard
                          key={`${lane.categoryId}-${item.asin ?? item.item_name}-${index}`}
                          item={item}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </section>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function DiscoveryCompressedCard({ item }: { item: CompressedAmazonItem }) {
  const reviewSummary = item.item_reviews_summarized ?? '';
  return (
    <div className="rounded-2xl border border-[var(--line-soft)] bg-[var(--surface)] p-4 text-left text-sm">
      <p className="text-base font-semibold text-[var(--ink-strong)]">{item.item_name}</p>
      <p className="mt-2 line-clamp-4 text-[var(--ink-soft)]">{item.item_detail ?? ''}</p>
      {item.item_entities_compact ? (
        <p className="mt-2 text-xs text-[var(--accent-deep)]">GLiNER: {item.item_entities_compact}</p>
      ) : null}
      {item.item_review_evidence && item.item_review_evidence.length > 0 ? (
        <ul className="mt-2 list-inside list-disc text-xs text-[var(--ink-soft)]">
          {item.item_review_evidence.map((ev, i) => (
            <li key={i}>{ev}</li>
          ))}
        </ul>
      ) : null}
      <p className="mt-2 text-xs text-[var(--ink-faint)]">
        {item.item_price != null ? `$${item.item_price}` : '—'} · {item.item_review_source ?? 'reviews'}:{' '}
        {reviewSummary.slice(0, 140)}
        {reviewSummary.length > 140 ? '…' : ''}
      </p>
      {item.source_url ? (
        <a
          href={item.source_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-block text-xs font-medium text-[var(--accent)] hover:underline"
        >
          Open listing
        </a>
      ) : null}
    </div>
  );
}

function EmptyState({ text, compact = false }: { text: string; compact?: boolean }) {
  return (
    <div
      className={`rounded-3xl border border-dashed border-[var(--line-soft)] bg-[var(--bg-app)] text-center text-[var(--ink-soft)] ${
        compact ? 'px-4 py-6 text-sm' : 'px-6 py-12 text-sm'
      }`}
    >
      {text}
    </div>
  );
}
