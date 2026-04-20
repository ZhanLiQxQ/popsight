import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Blocks,
  BookOpen,
  Bookmark,
  BookmarkCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  LayoutDashboard,
  MessageSquare,
  Pin,
  Radar,
  RefreshCw,
  Sparkles,
  Star,
  Trash2,
  X,
} from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import {
  AgentLog,
  AgentRole,
  AgentStatus,
  ChatMessage,
  Conversation,
  LongTermMemoryItem,
  MacroSuggestion,
  Manufacturer,
  Product,
  ScanSession,
  Trend,
} from './types';
import { chatWithAgent, deleteMemory, getAgentAnalysis, getBootstrap, saveMemory } from './lib/gemini';
import {
  DISCOVERY_LANE_OPTIONS,
  buildTrendyProducts,
  postMacroColdStart,
  type DiscoveryLaneId,
  type MacroColdStartResponse,
  type TrendyProduct,
} from './lib/discoveryPipeline';

type AppView = 'workspace' | 'conversations' | 'memory' | 'agents';
type ResultTab = 'products' | 'trends' | 'supply';

const INITIAL_AGENTS: AgentStatus[] = [
  { role: 'MarketCrawler', status: 'Idle', lastAction: 'Standby' },
  { role: 'TrendAnalyst', status: 'Idle', lastAction: 'Standby' },
  { role: 'ProductSleuth', status: 'Idle', lastAction: 'Standby' },
  { role: 'SupplyPartner', status: 'Idle', lastAction: 'Standby' },
  { role: 'Strategist', status: 'Idle', lastAction: 'Standby' },
];

function createId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso() {
  return new Date().toISOString();
}

function createInitialAssistantMessage(): ChatMessage {
  return {
    id: createId('msg'),
    role: 'assistant',
    content:
      'I can follow up on the products from the current scan, remember the active context in this conversation, and save durable business insights into long-term memory.',
    timestamp: nowIso(),
  };
}

const TRENDY_CONTEXT_MARKER = '[Active product context';

function displayMessageContent(content: string): { body: string; contextLine: string | null } {
  if (!content.startsWith(TRENDY_CONTEXT_MARKER)) {
    return { body: content, contextLine: null };
  }
  const idx = content.indexOf('User question:');
  if (idx === -1) return { body: content, contextLine: null };
  const body = content.slice(idx + 'User question:'.length).trim();
  const match = content.match(/-\s*Product:\s*([^\n]+)/);
  const productName = match ? match[1].trim() : 'selected product';
  return { body, contextLine: `Asking about: ${productName}` };
}

function formatTime(value: string) {
  return new Date(value).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function App() {
  const [activeView, setActiveView] = useState<AppView>('workspace');
  const [activeTab, setActiveTab] = useState<ResultTab>('products');
  const [topic, setTopic] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isDiscovering, setIsDiscovering] = useState(true);

  const [macros, setMacros] = useState<MacroSuggestion[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>(INITIAL_AGENTS);
  const [agentLogs, setAgentLogs] = useState<AgentLog[]>([]);
  const [scanSessions, setScanSessions] = useState<ScanSession[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [longTermMemories, setLongTermMemories] = useState<LongTermMemoryItem[]>([]);

  const [currentScanId, setCurrentScanId] = useState<string | null>(null);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [selectedTrendId, setSelectedTrendId] = useState<string | null>(null);
  const [selectedManufacturerId, setSelectedManufacturerId] = useState<string | null>(null);

  const [activeLaneId, setActiveLaneId] = useState<DiscoveryLaneId | null>(null);
  const [laneResponse, setLaneResponse] = useState<MacroColdStartResponse | null>(null);
  const [isLaneLoading, setIsLaneLoading] = useState(false);
  const [laneError, setLaneError] = useState<string | null>(null);
  const [selectedTrendyId, setSelectedTrendyId] = useState<string | null>(null);
  const [detailTrendyId, setDetailTrendyId] = useState<string | null>(null);

  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isChatbotCollapsed, setIsChatbotCollapsed] = useState(false);
  const [isPinnedMemoryCollapsed, setIsPinnedMemoryCollapsed] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const fallbackAssistantMessageRef = useRef<ChatMessage>(createInitialAssistantMessage());
  const productConvIdsRef = useRef<Record<string, string>>({});

  const currentScan = scanSessions.find((session) => session.id === currentScanId) ?? null;
  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId) ?? null;
  const chatMessages = activeConversation?.messages ?? [fallbackAssistantMessageRef.current];
  const trends = currentScan?.trends ?? [];
  const opportunities = currentScan?.opportunities ?? [];
  const manufacturers = currentScan?.manufacturers ?? [];
  const selectedProduct = opportunities.find((item) => item.id === selectedProductId);
  const selectedTrend = trends.find((item) => item.id === selectedTrendId);
  const selectedManufacturer = manufacturers.find((item) => item.id === selectedManufacturerId);
  const recentConversations = conversations.slice(0, 8);
  const pinnedMemories = longTermMemories.filter((item) => item.pinned);
  const trendyProducts = useMemo(
    () => (laneResponse && activeLaneId ? buildTrendyProducts(laneResponse, activeLaneId) : []),
    [laneResponse, activeLaneId],
  );
  const selectedTrendy = trendyProducts.find((p) => p.id === selectedTrendyId) ?? null;
  const detailTrendy = trendyProducts.find((p) => p.id === detailTrendyId) ?? null;
  const activeLaneLabel =
    laneResponse?.lanes.find((lane) => lane.categoryId === activeLaneId)?.categoryLabel ?? null;
  const highCount = trendyProducts.filter((p) => p.priority === 'HIGH').length;
  const mediumCount = trendyProducts.filter((p) => p.priority === 'MEDIUM').length;

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatLoading]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentLogs]);

  useEffect(() => {
    if (!activeConversationId && conversations[0]) setActiveConversationId(conversations[0].id);
  }, [conversations, activeConversationId]);

  useEffect(() => {
    if (!selectedTrendyId) return;
    const trendy = trendyProducts.find((p) => p.id === selectedTrendyId);
    if (!trendy) return;
    const nextTopic = trendy.product_name;

    const existingId = productConvIdsRef.current[nextTopic];
    if (existingId) {
      setActiveConversationId(existingId);
      return;
    }

    const conversation: Conversation = {
      id: createId('conv'),
      title: nextTopic,
      topic: nextTopic,
      scanSessionId: undefined,
      createdAt: nowIso(),
      updatedAt: nowIso(),
      messages: [createInitialAssistantMessage()],
    };
    productConvIdsRef.current[nextTopic] = conversation.id;
    setConversations((previous) => [conversation, ...previous]);
    setActiveConversationId(conversation.id);
  }, [selectedTrendyId, trendyProducts]);

  useEffect(() => {
    if (!currentScan) {
      setSelectedProductId(null);
      setSelectedTrendId(null);
      setSelectedManufacturerId(null);
      return;
    }

    if (selectedProductId && !currentScan.opportunities.some((item) => item.id === selectedProductId)) {
      setSelectedProductId(currentScan.opportunities[0]?.id ?? null);
    }

    if (selectedTrendId && !currentScan.trends.some((item) => item.id === selectedTrendId)) {
      setSelectedTrendId(currentScan.trends[0]?.id ?? null);
    }

    if (selectedManufacturerId && !currentScan.manufacturers.some((item) => item.id === selectedManufacturerId)) {
      setSelectedManufacturerId(currentScan.manufacturers[0]?.id ?? null);
    }
  }, [currentScan, selectedProductId, selectedTrendId, selectedManufacturerId]);

  useEffect(() => {
    const hydrate = async () => {
      setIsDiscovering(true);
      try {
        const data = await getBootstrap();
        setMacros(data.macros);
        setConversations([]);
        setActiveConversationId(null);
        setLongTermMemories(data.memories);
        setScanSessions(data.scanSessions);
        setAgentLogs(data.agentLogs);
      } catch (error) {
        console.error(error);
      } finally {
        setIsDiscovering(false);
      }
    };

    hydrate();
  }, []);

  const updateAgentStatus = (role: AgentRole, status: AgentStatus['status'], lastAction: string) => {
    setAgents((previous) => previous.map((agent) => (agent.role === role ? { ...agent, status, lastAction } : agent)));
  };

  const addAgentLog = (
    agentName: string,
    message: string,
    type: AgentLog['type'] = 'info',
  ) => {
    const entry: AgentLog = {
      id: createId('log'),
      agentName,
      message,
      timestamp: nowIso(),
      type,
    };

    setAgentLogs((previous) => [entry, ...previous].slice(0, 120));
  };

  const ensureConversation = (nextTopic: string, scanSessionId?: string) => {
    const existingConversation =
      activeConversation && activeConversation.topic === nextTopic ? activeConversation : null;

    if (existingConversation) {
      if (!existingConversation.scanSessionId && scanSessionId) {
        setConversations((previous) =>
          previous.map((conversation) =>
            conversation.id === existingConversation.id
              ? { ...conversation, scanSessionId, updatedAt: nowIso() }
              : conversation,
          ),
        );
      }

      return existingConversation.id;
    }

    const conversation: Conversation = {
      id: createId('conv'),
      title: nextTopic,
      topic: nextTopic,
      scanSessionId,
      createdAt: nowIso(),
      updatedAt: nowIso(),
      messages: [createInitialAssistantMessage()],
    };

    setConversations((previous) => [conversation, ...previous]);
    setActiveConversationId(conversation.id);
    return conversation.id;
  };

  const appendMessageToConversation = (conversationId: string, message: ChatMessage) => {
    setConversations((previous) =>
      previous.map((conversation) =>
        conversation.id === conversationId
          ? {
              ...conversation,
              updatedAt: message.timestamp,
              messages: [...conversation.messages, message],
            }
          : conversation,
      ),
    );
  };

  const runAnalysis = async (selectedTopic?: string) => {
    const nextTopic = (selectedTopic ?? topic).trim();
    if (!nextTopic) return;

    setTopic(nextTopic);
    setIsLoading(true);
    setActiveView('workspace');
    setActiveTab('products');

    updateAgentStatus('MarketCrawler', 'Searching', 'Crawling retail channels');
    updateAgentStatus('TrendAnalyst', 'Analyzing', 'Comparing momentum signals');
    updateAgentStatus('ProductSleuth', 'Searching', 'Mapping product whitespace');
    updateAgentStatus('SupplyPartner', 'Searching', 'Checking sourcing regions');
    updateAgentStatus('Strategist', 'Summarizing', 'Preparing business summary');
    addAgentLog('Strategist', `New scan started for "${nextTopic}".`, 'info');

    const result = await getAgentAnalysis(nextTopic);

    if (!result) {
      setAgents((previous) => previous.map((agent) => ({ ...agent, status: 'Idle', lastAction: 'Error' })));
      addAgentLog('Strategist', 'Analysis failed to converge.', 'error');
      setIsLoading(false);
      return;
    }

    const scanSession = result.scanSession;
    const conversation = result.conversation;

    setScanSessions((previous) => [scanSession, ...previous.filter((item) => item.id !== scanSession.id)].slice(0, 30));
    setConversations((previous) => [conversation, ...previous.filter((item) => item.id !== conversation.id)]);
    setAgentLogs(result.agentLogs);
    setActiveConversationId(conversation.id);
    setCurrentScanId(scanSession.id);
    setSelectedProductId(scanSession.opportunities[0]?.id ?? null);
    setSelectedTrendId(scanSession.trends[0]?.id ?? null);
    setSelectedManufacturerId(scanSession.manufacturers[0]?.id ?? null);

    setAgents((previous) =>
      previous.map((agent) => ({ ...agent, status: 'Idle', lastAction: 'Ready for review' })),
    );

    addAgentLog('Strategist', `Scan completed for "${nextTopic}".`, 'success');
    setIsLoading(false);
  };

  const handleSelectLane = async (laneId: DiscoveryLaneId, laneLabel: string) => {
    if (isLaneLoading) return;

    setActiveView('workspace');
    setActiveLaneId(laneId);
    setIsLaneLoading(true);
    setLaneError(null);
    setLaneResponse(null);
    setSelectedTrendyId(null);
    setDetailTrendyId(null);
    setTopic(laneLabel);

    updateAgentStatus('MarketCrawler', 'Searching', `Pulling trendy items for ${laneLabel}`);
    addAgentLog('MarketCrawler', `Fetching trendy products for lane "${laneLabel}".`, 'info');

    try {
      const response = await postMacroColdStart({ discoveryLaneIds: [laneId] });
      setLaneResponse(response);

      if (response.discoveryAborted) {
        addAgentLog(
          'MarketCrawler',
          `Discovery aborted: ${response.discoveryAbortReason ?? 'no usable Google Trends signal.'}`,
          'warning',
        );
      } else {
        const merged = buildTrendyProducts(response, laneId);
        const high = merged.filter((p) => p.priority === 'HIGH').length;
        const medium = merged.filter((p) => p.priority === 'MEDIUM').length;
        addAgentLog(
          'MarketCrawler',
          `Loaded ${merged.length} ranked product${merged.length === 1 ? '' : 's'} for "${laneLabel}" (HIGH ${high} · MEDIUM ${medium}).`,
          'success',
        );
      }
    } catch (error) {
      const message = (error as Error)?.message || String(error);
      setLaneError(message);
      addAgentLog('MarketCrawler', `Lane fetch failed: ${message}`, 'error');
    } finally {
      updateAgentStatus('MarketCrawler', 'Idle', 'Standby');
      setIsLaneLoading(false);
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim() || isChatLoading) return;

    const currentConversationId =
      activeConversationId || ensureConversation(topic || currentScan?.topic || 'New sourcing thread', currentScanId ?? undefined);
    const userMessage = chatInput.trim();

    let pendingMessage = userMessage;
    if (selectedTrendy) {
      const priceStr = selectedTrendy.item_price != null ? `$${selectedTrendy.item_price.toFixed(2)}` : 'n/a';
      const ratingStr = selectedTrendy.item_rating != null ? selectedTrendy.item_rating.toFixed(1) : 'n/a';
      const reviewsStr =
        selectedTrendy.item_review_count != null ? selectedTrendy.item_review_count.toLocaleString() : 'n/a';
      const supplierStr = selectedTrendy.supplier
        ? `${selectedTrendy.supplier}${selectedTrendy.supplier_region ? ` (${selectedTrendy.supplier_region})` : ''}`
        : 'none assigned';
      const reasonStr = selectedTrendy.reason ? selectedTrendy.reason.slice(0, 240) : 'n/a';
      const contextBlock = [
        '[Active product context — use this as grounding for the next answer]',
        `- Product: ${selectedTrendy.product_name}`,
        `- Category: ${selectedTrendy.category}`,
        `- Priority: ${selectedTrendy.priority} (rank_score ${selectedTrendy.rank_score.toFixed(2)})`,
        `- Price: ${priceStr} · Rating: ★${ratingStr} · Reviews: ${reviewsStr} · Sold: ${selectedTrendy.external_sold_quantity.toLocaleString()}`,
        `- Supplier: ${supplierStr}`,
        `- Reason: ${reasonStr}`,
      ].join('\n');
      pendingMessage = `${contextBlock}\n\nUser question: ${userMessage}`;
    }

    setChatInput('');
    setIsChatLoading(true);

    const optimisticUserMessage: ChatMessage = {
      id: createId('msg'),
      role: 'user',
      content: pendingMessage,
      timestamp: nowIso(),
    };
    appendMessageToConversation(currentConversationId, optimisticUserMessage);

    try {
      const response = await chatWithAgent({
        conversationId: currentConversationId,
        scanSessionId: currentScanId,
        message: pendingMessage,
        selectedProductId,
        selectedTrendId,
        selectedManufacturerId,
      });

      setConversations((previous) => {
        const prev = previous.find((c) => c.id === response.conversation.id);
        const trendyName = selectedTrendy?.product_name;
        const incomingConv: Conversation = {
          ...response.conversation,
          topic: trendyName || prev?.topic || response.conversation.topic,
          title: trendyName || prev?.title || response.conversation.title,
        };
        if (trendyName) {
          productConvIdsRef.current[trendyName] = incomingConv.id;
        }
        return [
          incomingConv,
          ...previous.filter((item) => item.id !== incomingConv.id),
        ];
      });
      setLongTermMemories(response.memories);
      setAgentLogs(response.agentLogs);
      setActiveConversationId(response.conversation.id);
    } catch (error) {
      console.error(error);
      addAgentLog('Strategist', 'Chat request failed.', 'error');
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSaveMemory = async (payload: Pick<LongTermMemoryItem, 'kind' | 'title' | 'content'>) => {
    try {
      const response = await saveMemory({
        conversationId: activeConversationId,
        scanSessionId: currentScanId,
        kind: payload.kind,
        title: payload.title,
        content: payload.content,
      });
      setLongTermMemories(response.memories);
      addAgentLog('Strategist', `Saved memory: ${payload.title}`, 'success');
    } catch (error) {
      console.error(error);
      addAgentLog('Strategist', 'Failed to save long-term memory.', 'error');
    }
  };

  const favoriteTag = (product: TrendyProduct) => `[favorite:trendy_product:${product.id}]`;
  const findFavoriteMemory = (product: TrendyProduct): LongTermMemoryItem | undefined =>
    longTermMemories.find((m) => m.content.startsWith(favoriteTag(product)));
  const isProductFavorited = (product: TrendyProduct) => Boolean(findFavoriteMemory(product));

  const buildFavoriteContent = (product: TrendyProduct) => {
    const lines = [
      favoriteTag(product),
      `Product: ${product.product_name}`,
      `Lane: ${product.category}`,
      `Priority: ${product.priority} (rank_score ${product.rank_score.toFixed(2)})`,
    ];
    if (product.item_price != null) lines.push(`Price: $${product.item_price.toFixed(2)}`);
    if (product.item_rating != null) lines.push(`Rating: ★${product.item_rating.toFixed(1)}`);
    if (product.external_sold_quantity) lines.push(`Sold: ${product.external_sold_quantity.toLocaleString()}`);
    if (product.supplier) {
      lines.push(`Supplier: ${product.supplier}${product.supplier_region ? ` (${product.supplier_region})` : ''}`);
    }
    if (product.reason) lines.push(`Why: ${product.reason.slice(0, 400)}`);
    return lines.join('\n');
  };

  const handleToggleFavorite = async (product: TrendyProduct) => {
    const existing = findFavoriteMemory(product);
    if (existing) {
      try {
        const response = await deleteMemory(existing.id);
        setLongTermMemories(response.memories);
        addAgentLog('Strategist', `Removed from favorites: ${product.product_name}`, 'info');
      } catch (error) {
        console.error(error);
        addAgentLog('Strategist', 'Failed to remove favorite.', 'error');
      }
      return;
    }
    try {
      const response = await saveMemory({
        conversationId: activeConversationId,
        scanSessionId: currentScanId,
        kind: 'product_insight',
        title: product.product_name,
        content: buildFavoriteContent(product),
        pinned: true,
      });
      setLongTermMemories(response.memories);
      addAgentLog('Strategist', `Saved to favorites: ${product.product_name}`, 'success');
    } catch (error) {
      console.error(error);
      addAgentLog('Strategist', 'Failed to save favorite.', 'error');
    }
  };

  const handleDeleteMemory = async (memoryId: string) => {
    try {
      const response = await deleteMemory(memoryId);
      setLongTermMemories(response.memories);
      addAgentLog('Strategist', 'Removed saved item.', 'info');
    } catch (error) {
      console.error(error);
      addAgentLog('Strategist', 'Failed to delete saved item.', 'error');
    }
  };

  const navItems: { id: AppView; label: string; icon: typeof LayoutDashboard; helper: string }[] = [
    { id: 'workspace', label: 'Workspace', icon: LayoutDashboard, helper: 'Search + results + chat' },
    { id: 'conversations', label: 'Conversations', icon: MessageSquare, helper: 'Stored threads' },
    { id: 'memory', label: 'Saved', icon: Bookmark, helper: 'Starred items' },
    { id: 'agents', label: 'Agent Status', icon: Blocks, helper: 'Detailed runtime state' },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-app)] text-[var(--ink-strong)]">
      <aside
        className={`flex flex-col border-r border-[var(--line-soft)] bg-[var(--panel-strong)] text-white transition-[width] duration-200 ${
          isSidebarCollapsed ? 'w-14' : 'w-72'
        }`}
      >
        {isSidebarCollapsed ? (
          <>
            <div className="flex items-center justify-center border-b border-white/10 py-4">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--accent)]/15 text-[var(--accent)]">
                <Radar className="h-4 w-4" />
              </div>
            </div>
            <nav className="flex-1 space-y-2 px-2 py-4">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActiveView(item.id)}
                  title={item.label}
                  className={`flex w-full items-center justify-center rounded-xl border py-2.5 transition ${
                    activeView === item.id
                      ? 'border-white/15 bg-white/10'
                      : 'border-transparent bg-white/5 hover:bg-white/8'
                  }`}
                >
                  <item.icon className="h-4 w-4 text-[var(--accent)]" />
                </button>
              ))}
            </nav>
            <button
              onClick={() => setIsSidebarCollapsed(false)}
              title="Expand sidebar"
              className="m-2 flex items-center justify-center rounded-xl border border-white/10 bg-white/5 py-2 text-white/70 transition hover:bg-white/10"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </>
        ) : (
          <>
            <div className="border-b border-white/10 px-6 py-6">
              <div className="mb-2 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent)]/15 text-[var(--accent)]">
                  <Radar className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-lg font-semibold tracking-tight">PopSight</p>
                  <p className="text-xs text-white/50">CPG sourcing cockpit</p>
                </div>
                <button
                  onClick={() => setIsSidebarCollapsed(true)}
                  title="Collapse sidebar"
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white/70 transition hover:bg-white/10"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
              </div>
            </div>

            <nav className="flex-1 space-y-2 px-4 py-5">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setActiveView(item.id)}
                  className={`w-full rounded-2xl border px-4 py-3 text-left transition ${
                    activeView === item.id
                      ? 'border-white/15 bg-white/10'
                      : 'border-transparent bg-white/5 hover:bg-white/8'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <item.icon className="h-4 w-4 text-[var(--accent)]" />
                    <div>
                      <div className="text-sm font-medium">{item.label}</div>
                      <div className="text-[11px] text-white/50">{item.helper}</div>
                    </div>
                  </div>
                </button>
              ))}
            </nav>

            <div className="space-y-4 border-t border-white/10 px-4 py-5">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-xs uppercase tracking-[0.2em] text-white/45">Current context</p>
                  <Clock3 className="h-3.5 w-3.5 text-white/35" />
                </div>
                <p className="mb-1 text-sm font-medium text-white/90">
                  {selectedTrendy?.product_name || activeLaneLabel || 'No active lane'}
                </p>
                <p className="text-xs text-white/50">
                  {laneResponse
                    ? `${trendyProducts.length} trendy products · HIGH ${highCount} · MEDIUM ${mediumCount}`
                    : 'Pick a discovery lane to start.'}
                </p>
              </div>

            </div>
          </>
        )}
      </aside>

      <main className="flex min-w-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-[var(--line-soft)] bg-white/85 px-8 py-5 backdrop-blur">
            <div className="flex items-center justify-between gap-6">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {activeView === 'workspace' && 'Sourcing Workspace'}
                  {activeView === 'conversations' && 'Conversation History'}
                  {activeView === 'memory' && 'Saved Items'}
                  {activeView === 'agents' && 'Agent Status'}
                </h1>
                <p className="mt-1 text-sm text-[var(--ink-soft)]">
                  {activeView === 'workspace' &&
                    'Keep the main page focused on search, results, and contextual follow-up questions.'}
                  {activeView === 'conversations' &&
                    'Every follow-up thread is saved so users can return without losing context.'}
                  {activeView === 'memory' &&
                    'Items you starred from discovery lanes or chat. These are also injected into follow-up chat as context.'}
                  {activeView === 'agents' &&
                    'Operational detail has been moved out of the main page into a dedicated runtime panel.'}
                </p>
              </div>

              {activeView === 'workspace' && isLaneLoading && (
                <span className="inline-flex items-center gap-2 rounded-full border border-[var(--line-soft)] bg-white px-3 py-1.5 text-xs text-[var(--ink-soft)]">
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  Running discovery pipeline…
                </span>
              )}
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
            {activeView === 'workspace' && (
              <div className="space-y-8">
                <section className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 shadow-[0_18px_50px_rgba(16,24,40,0.08)]">
                  <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Discovery lanes</p>
                      <h2 className="mt-1 text-xl font-semibold">Pick a category to pull trendy products</h2>
                      <p className="mt-1 text-sm text-[var(--ink-soft)]">
                        Six fixed retail lanes. Each click runs the full pipeline: Google Trends → MacroScout → Amazon Top 5 → Compress + NER → Rank → Supply Plan → Final list.
                      </p>
                    </div>
                    {laneResponse && !isLaneLoading && activeLaneLabel && (
                      <span className="rounded-full bg-[var(--accent-muted)] px-3 py-1 text-xs text-[var(--accent-deep)]">
                        {trendyProducts.length} product{trendyProducts.length === 1 ? '' : 's'} · HIGH {highCount} · MEDIUM {mediumCount} · {activeLaneLabel}
                      </span>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {DISCOVERY_LANE_OPTIONS.map((lane) => {
                      const isActive = activeLaneId === lane.id;
                      const showSpinner = isActive && isLaneLoading;
                      return (
                        <button
                          key={lane.id}
                          type="button"
                          onClick={() => handleSelectLane(lane.id, lane.label)}
                          disabled={isLaneLoading}
                          className={`rounded-full border px-4 py-2 text-sm transition disabled:cursor-not-allowed disabled:opacity-70 ${
                            isActive
                              ? 'border-[var(--accent)] bg-[var(--accent-muted)] text-[var(--accent-deep)]'
                              : 'border-[var(--line-soft)] bg-white hover:border-[var(--accent)]/60'
                          }`}
                        >
                          <span className="inline-flex items-center gap-2">
                            {showSpinner && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                            {lane.label}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {laneError && (
                    <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                      {laneError}
                    </div>
                  )}

                  {(laneResponse || isLaneLoading) && (
                    <div className="mt-6">
                      {isLaneLoading && !laneResponse ? (
                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                          {Array.from({ length: 6 }).map((_, index) => (
                            <div
                              key={index}
                              className="h-44 animate-pulse rounded-3xl border border-[var(--line-soft)] bg-[var(--bg-app)]"
                            />
                          ))}
                        </div>
                      ) : laneResponse ? (
                        trendyProducts.length === 0 ? (
                          <EmptyState
                            text={
                              laneResponse.discoveryAborted
                                ? `Discovery aborted: ${laneResponse.discoveryAbortReason ?? 'no usable Google Trends signal.'}`
                                : 'No ranked products surfaced for this lane. Try another category or check API quotas.'
                            }
                          />
                        ) : (
                          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                            {trendyProducts.map((product) => (
                              <TrendyProductCard
                                key={product.id}
                                product={product}
                                isActive={selectedTrendyId === product.id}
                                isFavorited={isProductFavorited(product)}
                                onSelect={() =>
                                  setSelectedTrendyId((prev) =>
                                    prev === product.id ? null : product.id,
                                  )
                                }
                                onOpenDetails={() => {
                                  setSelectedTrendyId(product.id);
                                  setDetailTrendyId(product.id);
                                }}
                                onToggleFavorite={() => handleToggleFavorite(product)}
                              />
                            ))}
                          </div>
                        )
                      ) : null}
                    </div>
                  )}

                  {!laneResponse && !isLaneLoading && !laneError && (
                    <p className="mt-6 text-sm text-[var(--ink-soft)]">
                      Select a lane above to run the full discovery pipeline and get a ranked, supply-planned product list.
                    </p>
                  )}
                </section>

                {recentConversations.length > 0 && (
                  <section className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                    <div className="mb-4 flex items-center justify-between">
                      <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Recent threads</p>
                      <BookOpen className="h-4 w-4 text-[var(--ink-faint)]" />
                    </div>
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {recentConversations.map((conversation) => (
                        <button
                          key={conversation.id}
                          onClick={() => {
                            setActiveConversationId(conversation.id);
                            setCurrentScanId(conversation.scanSessionId ?? null);
                            setActiveView('conversations');
                          }}
                          className="w-full rounded-2xl border border-[var(--line-soft)] bg-white px-4 py-3 text-left transition hover:border-[var(--accent)]/50"
                        >
                          <div className="flex items-center justify-between gap-4">
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium">{conversation.title}</p>
                              <p className="text-xs text-[var(--ink-soft)]">{conversation.messages.length} messages</p>
                            </div>
                            <span className="shrink-0 text-xs text-[var(--ink-faint)]">{formatTime(conversation.updatedAt)}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            )}

            {activeView === 'conversations' && (
              <div className="grid gap-5 xl:grid-cols-[0.88fr_1.12fr]">
                <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Stored conversations</p>
                  <div className="mt-4 space-y-3">
                    {conversations.length === 0 && <EmptyState text="No chat history yet." />}
                    {conversations.map((conversation) => (
                      <button
                        key={conversation.id}
                        onClick={() => {
                          setActiveConversationId(conversation.id);
                          setCurrentScanId(conversation.scanSessionId ?? null);
                        }}
                        className={`w-full rounded-3xl border p-4 text-left transition ${
                          activeConversationId === conversation.id
                            ? 'border-[var(--accent)] bg-[var(--accent-muted)]/55'
                            : 'border-[var(--line-soft)] bg-white hover:border-[var(--accent)]/50'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-base font-semibold">{conversation.title}</p>
                            <p className="mt-1 text-sm text-[var(--ink-soft)]">
                              {conversation.messages.length} messages · {conversation.topic}
                            </p>
                          </div>
                          <span className="text-xs text-[var(--ink-faint)]">{formatTime(conversation.updatedAt)}</span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Conversation detail</p>
                  <div className="mt-4 space-y-4">
                    {chatMessages.map((message) => {
                      const { body, contextLine } =
                        message.role === 'user'
                          ? displayMessageContent(message.content)
                          : { body: message.content, contextLine: null };
                      return (
                        <div
                          key={message.id}
                          className={`rounded-3xl px-4 py-3 ${
                            message.role === 'user'
                              ? 'ml-auto max-w-[85%] bg-[var(--panel-strong)] text-white'
                              : 'max-w-[90%] border border-[var(--line-soft)] bg-white'
                          }`}
                        >
                          {contextLine && (
                            <p className="mb-1 text-[10px] uppercase tracking-[0.18em] text-white/60">
                              {contextLine}
                            </p>
                          )}
                          <p className="whitespace-pre-wrap text-sm leading-6">{body}</p>
                          <p
                            className={`mt-2 text-[11px] ${
                              message.role === 'user' ? 'text-white/55' : 'text-[var(--ink-faint)]'
                            }`}
                          >
                            {formatTime(message.timestamp)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {activeView === 'memory' && (
              <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                <div className="mb-4 flex items-center justify-between">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">
                    Saved items · {longTermMemories.length}
                  </p>
                  <span className="text-xs text-[var(--ink-faint)]">
                    Starred from discovery lanes, also injected into chat context.
                  </span>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {longTermMemories.length === 0 && (
                    <div className="md:col-span-2">
                      <EmptyState text="Nothing saved yet. Open a discovery lane and click the bookmark icon on a product to save it here." />
                    </div>
                  )}
                  {longTermMemories.map((memory) => {
                    const displayLines = memory.content
                      .split('\n')
                      .filter((line) => !line.startsWith('[favorite:'))
                      .join('\n');
                    return (
                      <div
                        key={memory.id}
                        className="flex flex-col rounded-3xl border border-[var(--line-soft)] bg-white p-5"
                      >
                        <div className="mb-2 flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-base font-semibold">{memory.title}</p>
                            <div className="mt-1.5 flex flex-wrap items-center gap-2">
                              <span className="rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-[11px] capitalize text-[var(--accent-deep)]">
                                {memory.kind.replace('_', ' ')}
                              </span>
                              {memory.pinned && (
                                <span className="flex items-center gap-1 text-[11px] text-[var(--accent-deep)]">
                                  <Pin className="h-3 w-3" />
                                  pinned
                                </span>
                              )}
                              <span className="text-[11px] text-[var(--ink-faint)]">
                                {formatTime(memory.updatedAt)}
                              </span>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => handleDeleteMemory(memory.id)}
                            title="Remove from saved"
                            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--line-soft)] bg-white text-[var(--ink-soft)] transition hover:border-red-400 hover:text-red-500"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                        <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-[var(--ink-soft)]">
                          {displayLines || memory.content}
                        </pre>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {activeView === 'agents' && (
              <div className="space-y-5">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                  {agents.map((agent) => (
                    <div key={agent.role} className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-5">
                      <div className="mb-3 flex items-center justify-between">
                        <span className="text-sm font-semibold">{agent.role}</span>
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            agent.status === 'Idle' ? 'bg-emerald-500' : 'animate-pulse bg-amber-500'
                          }`}
                        />
                      </div>
                      <p className="text-sm text-[var(--ink-soft)]">{agent.lastAction}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--panel-strong)] p-6 text-white">
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-xs uppercase tracking-[0.24em] text-white/45">Runtime log</p>
                    <span className="text-xs text-white/45">{agentLogs.length} entries</span>
                  </div>
                  <div className="space-y-3">
                    {agentLogs.length === 0 && <p className="text-sm text-white/55">Logs will appear after scans and chat actions.</p>}
                    {agentLogs.map((log) => (
                      <div key={log.id} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                        <div className="mb-1 flex items-center gap-3 text-xs">
                          <span className="text-white/35">{formatTime(log.timestamp)}</span>
                          <span className="font-medium text-[var(--accent)]">@{log.agentName}</span>
                        </div>
                        <p className="text-sm text-white/80">{log.message}</p>
                      </div>
                    ))}
                    <div ref={logsEndRef} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {isChatbotCollapsed ? (
          <aside className="flex w-12 flex-col items-center border-l border-[var(--line-soft)] bg-white py-3">
            <button
              onClick={() => setIsChatbotCollapsed(false)}
              title="Expand chatbot"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line-soft)] bg-white text-[var(--ink-soft)] transition hover:border-[var(--accent)]/60"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <div className="mt-3 flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--accent-muted)] text-[var(--accent-deep)]">
              <MessageSquare className="h-4 w-4" />
            </div>
          </aside>
        ) : (
          <aside className="flex w-[420px] min-w-[380px] flex-col border-l border-[var(--line-soft)] bg-white">
          <div className="border-b border-[var(--line-soft)] px-5 py-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Chatbot</p>
                <h2 className="mt-1 truncate text-lg font-semibold" title={
                  selectedTrendy?.product_name ||
                  activeLaneLabel ||
                  currentScan?.topic ||
                  'Follow up on the current scan'
                }>
                  {selectedTrendy
                    ? `Follow up on ${selectedTrendy.product_name}`
                    : activeLaneLabel
                      ? `Follow up on ${activeLaneLabel}`
                      : 'Follow up on the current scan'}
                </h2>
              </div>
              <span className="rounded-full bg-[var(--accent-muted)] px-3 py-1 text-xs text-[var(--accent-deep)]">
                Context aware
              </span>
              <button
                onClick={() => setIsChatbotCollapsed(true)}
                title="Collapse chatbot"
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--line-soft)] bg-white text-[var(--ink-soft)] transition hover:border-[var(--accent)]/60"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <ContextChip
                label="Lane"
                value={activeLaneLabel || currentScan?.topic || 'None'}
              />
              <ContextChip
                label="Product"
                value={selectedTrendy?.product_name || selectedProduct?.name || 'None'}
              />
              <ContextChip label="Saved" value={String(longTermMemories.length)} />
            </div>

            {pinnedMemories.length > 0 && (
              <div className="mt-4 rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] p-3">
                <button
                  type="button"
                  onClick={() => setIsPinnedMemoryCollapsed((prev) => !prev)}
                  className="flex w-full items-center justify-between gap-2 text-left"
                  title={isPinnedMemoryCollapsed ? 'Expand pinned memory' : 'Collapse pinned memory'}
                >
                  <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">
                    <Pin className="h-3 w-3" />
                    Pinned memory
                    <span className="text-[var(--ink-faint)]">· {pinnedMemories.length}</span>
                  </span>
                  <ChevronDown
                    className={`h-3.5 w-3.5 text-[var(--ink-faint)] transition-transform ${
                      isPinnedMemoryCollapsed ? '-rotate-90' : ''
                    }`}
                  />
                </button>
                {!isPinnedMemoryCollapsed && (
                  <p className="mt-2 text-sm text-[var(--ink-soft)]">{pinnedMemories[0]?.content}</p>
                )}
              </div>
            )}
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {chatMessages.map((message) => {
              const { body, contextLine } =
                message.role === 'user'
                  ? displayMessageContent(message.content)
                  : { body: message.content, contextLine: null };
              return (
                <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[88%] rounded-[24px] px-4 py-3 ${
                      message.role === 'user'
                        ? 'bg-[var(--panel-strong)] text-white'
                        : 'border border-[var(--line-soft)] bg-[var(--surface)]'
                    }`}
                  >
                    {contextLine && (
                      <p className="mb-1 text-[10px] uppercase tracking-[0.18em] text-white/60">
                        {contextLine}
                      </p>
                    )}
                    <p className="whitespace-pre-wrap text-sm leading-6">{body}</p>
                    <p className={`mt-2 text-[11px] ${message.role === 'user' ? 'text-white/50' : 'text-[var(--ink-faint)]'}`}>
                      {formatTime(message.timestamp)}
                    </p>
                  </div>
                </div>
              );
            })}

            {isChatLoading && (
              <div className="max-w-[120px] rounded-[24px] border border-[var(--line-soft)] bg-[var(--surface)] px-4 py-3">
                <div className="flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--ink-faint)]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--ink-faint)] [animation-delay:0.15s]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[var(--ink-faint)] [animation-delay:0.3s]" />
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="border-t border-[var(--line-soft)] px-5 py-4">
            <div className="mb-3 flex flex-wrap gap-2">
              {selectedProduct && (
                <button
                  onClick={() =>
                    setChatInput(`Compare this product with the closest alternatives and explain the sourcing upside.`)
                  }
                  className="rounded-full border border-[var(--line-soft)] px-3 py-1.5 text-xs transition hover:border-[var(--accent)]"
                >
                  Compare this product
                </button>
              )}
              {currentScan && (
                <button
                  onClick={() => setChatInput('Summarize the top 3 actions we should take from this scan.')}
                  className="rounded-full border border-[var(--line-soft)] px-3 py-1.5 text-xs transition hover:border-[var(--accent)]"
                >
                  Next actions
                </button>
              )}
              <button
                onClick={() => {
                  if (selectedTrendy) handleToggleFavorite(selectedTrendy);
                }}
                disabled={!selectedTrendy}
                title={
                  !selectedTrendy
                    ? 'Select a trendy product in the lane first'
                    : isProductFavorited(selectedTrendy)
                      ? 'Remove from saved items'
                      : 'Save this product to your saved items'
                }
                className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition ${
                  !selectedTrendy
                    ? 'cursor-not-allowed border-[var(--line-soft)] text-[var(--ink-faint)] opacity-50'
                    : isProductFavorited(selectedTrendy)
                      ? 'border-[var(--accent)] bg-[var(--accent-muted)] text-[var(--accent-deep)]'
                      : 'border-[var(--line-soft)] hover:border-[var(--accent)]'
                }`}
              >
                {selectedTrendy && isProductFavorited(selectedTrendy) ? (
                  <>
                    <BookmarkCheck className="h-3.5 w-3.5" />
                    Saved
                  </>
                ) : (
                  <>
                    <Star className="h-3.5 w-3.5" />
                    Save to favorites
                  </>
                )}
              </button>
            </div>

            <div className="relative">
              <textarea
                value={chatInput}
                onChange={(event) => setChatInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder="Ask about the selected product, the current scan, or a saved memory..."
                className="min-h-[104px] w-full resize-none rounded-[24px] border border-[var(--line-soft)] bg-[var(--bg-app)] px-4 py-3 pr-14 text-sm leading-6 outline-none transition focus:border-[var(--accent)]"
              />
              <button
                onClick={handleSendMessage}
                disabled={isChatLoading}
                className="absolute bottom-3 right-3 flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--panel-strong)] text-white transition hover:brightness-110 disabled:opacity-50"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <p className="mt-3 text-xs leading-5 text-[var(--ink-faint)]">
              Chat history is stored as conversation records. Only stable business facts should be promoted into long-term memory.
            </p>
          </div>
          </aside>
        )}
      </main>

      <AnimatePresence>
        {detailTrendy && (
          <TrendyDetailModal
            product={detailTrendy}
            onClose={() => setDetailTrendyId(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  helper,
}: {
  icon: ReactNode;
  label: string;
  value: number;
  helper: string;
}) {
  return (
    <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--accent-muted)] text-[var(--accent-deep)]">
          {icon}
        </div>
        <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">active</span>
      </div>
      <p className="text-3xl font-semibold">{value}</p>
      <p className="mt-1 text-sm font-medium">{label}</p>
      <p className="mt-1 text-xs text-[var(--ink-soft)]">{helper}</p>
    </div>
  );
}

function ContextChip({ label, value }: { label: string; value: string }) {
  return (
    <div
      title={value}
      className="flex max-w-full items-center gap-1 rounded-full bg-[var(--bg-app)] px-3 py-1.5 text-xs text-[var(--ink-soft)]"
    >
      <span className="shrink-0 text-[var(--ink-faint)]">{label}:</span>
      <span className="truncate font-medium text-[var(--ink-strong)]">{value}</span>
    </div>
  );
}

function FocusCard({ title, subtitle, body }: { title: string; subtitle: string; body: string }) {
  return (
    <div className="rounded-3xl border border-[var(--line-soft)] bg-white p-5">
      <p className="text-base font-semibold">{title}</p>
      <p className="mt-1 text-sm text-[var(--ink-soft)]">{subtitle}</p>
      <p className="mt-3 text-sm leading-6 text-[var(--ink-soft)]">{body}</p>
    </div>
  );
}

const PRIORITY_BADGE: Record<TrendyProduct['priority'], string> = {
  HIGH: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  LOW: 'bg-slate-100 text-slate-600 border-slate-200',
};

function TrendyProductCard({
  product,
  isActive,
  isFavorited,
  onSelect,
  onOpenDetails,
  onToggleFavorite,
}: {
  product: TrendyProduct;
  isActive: boolean;
  isFavorited: boolean;
  onSelect: () => void;
  onOpenDetails: () => void;
  onToggleFavorite: () => void;
}) {
  const price = product.item_price != null ? `$${product.item_price.toFixed(2)}` : '—';
  const rating = product.item_rating != null ? product.item_rating.toFixed(1) : '—';
  const reviews =
    product.item_review_count != null ? product.item_review_count.toLocaleString() : '—';
  const sold = product.external_sold_quantity.toLocaleString();

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect();
        }
      }}
      className={`group flex h-full cursor-pointer flex-col rounded-3xl border bg-white p-5 text-left transition hover:shadow-[0_12px_30px_rgba(16,24,40,0.08)] ${
        isActive
          ? 'border-[var(--accent)] ring-2 ring-[var(--accent)]/30'
          : 'border-[var(--line-soft)] hover:border-[var(--accent)]/60'
      }`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="text-base font-semibold leading-6">{product.product_name}</p>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleFavorite();
            }}
            title={isFavorited ? 'Remove from saved' : 'Save to favorites'}
            className={`flex h-7 w-7 items-center justify-center rounded-full border transition ${
              isFavorited
                ? 'border-[var(--accent)] bg-[var(--accent-muted)] text-[var(--accent-deep)]'
                : 'border-[var(--line-soft)] bg-white text-[var(--ink-faint)] hover:border-[var(--accent)] hover:text-[var(--accent-deep)]'
            }`}
          >
            {isFavorited ? (
              <BookmarkCheck className="h-3.5 w-3.5" />
            ) : (
              <Bookmark className="h-3.5 w-3.5" />
            )}
          </button>
          <span
            className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${PRIORITY_BADGE[product.priority]}`}
          >
            {product.priority}
          </span>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{price}</span>
        <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">★ {rating}</span>
        <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{reviews} reviews</span>
        <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{sold} sold</span>
        {product.is_actionable && product.supplier && (
          <span className="rounded-full bg-[var(--accent-muted)] px-3 py-1 text-[var(--accent-deep)]">
            Supplier ready
          </span>
        )}
      </div>
      {product.reason && (
        <p className="mb-3 line-clamp-3 text-sm leading-6 text-[var(--ink-soft)]">
          {product.reason}
        </p>
      )}
      <div className="mt-auto flex items-center justify-between gap-3 pt-3 text-xs text-[var(--ink-faint)]">
        <span>Rank score {product.rank_score.toFixed(2)}</span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onOpenDetails();
          }}
          className="rounded-full border border-[var(--line-soft)] bg-white px-3 py-1 text-xs font-medium text-[var(--ink)] transition hover:border-[var(--accent)] hover:text-[var(--accent-deep)]"
        >
          Details →
        </button>
      </div>
      {isActive && (
        <span className="mt-3 inline-flex w-fit items-center gap-1 rounded-full bg-[var(--accent-muted)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--accent-deep)]">
          Active context
        </span>
      )}
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">{label}</span>
      <span className="text-sm text-[var(--ink)]">{value}</span>
    </div>
  );
}

function TrendyDetailModal({
  product,
  onClose,
}: {
  product: TrendyProduct;
  onClose: () => void;
}) {
  const price = product.item_price != null ? `$${product.item_price.toFixed(2)}` : '—';
  const estCost =
    product.estimated_cost != null ? `$${product.estimated_cost.toFixed(2)}` : '—';
  const rating = product.item_rating != null ? product.item_rating.toFixed(1) : '—';
  const reviews =
    product.item_review_count != null ? product.item_review_count.toLocaleString() : '—';
  const sold = product.external_sold_quantity.toLocaleString();
  const velocity =
    product.internal_sales_velocity != null ? product.internal_sales_velocity.toFixed(2) : '—';
  const inventory =
    product.inventory_health != null ? product.inventory_health.toFixed(2) : '—';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-8 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.98 }}
        transition={{ duration: 0.2 }}
        onClick={(e) => e.stopPropagation()}
        className="relative flex max-h-[86vh] w-full max-w-3xl flex-col overflow-hidden rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] shadow-[0_30px_90px_rgba(16,24,40,0.3)]"
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 z-10 rounded-full border border-[var(--line-soft)] bg-white p-1.5 text-[var(--ink-soft)] transition hover:text-[var(--ink)]"
          aria-label="Close details"
        >
          <X className="h-4 w-4" />
        </button>

        <div className="border-b border-[var(--line-soft)] bg-[var(--bg-app)] px-7 py-6">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${PRIORITY_BADGE[product.priority]}`}
            >
              {product.priority}
            </span>
            <span className="text-xs text-[var(--ink-faint)]">{product.category}</span>
            <span className="text-xs text-[var(--ink-faint)]">
              · Rank score {product.rank_score.toFixed(2)}
            </span>
          </div>
          <h2 className="mt-2 text-lg font-semibold leading-7">{product.product_name}</h2>
          {product.reason && (
            <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{product.reason}</p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-7 py-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <DetailRow label="Price" value={price} />
            <DetailRow label="Rating" value={`★ ${rating}`} />
            <DetailRow label="Reviews" value={reviews} />
            <DetailRow label="Sold (external)" value={sold} />
            <DetailRow
              label="Est. landed cost"
              value={product.is_actionable ? estCost : '—'}
            />
            <DetailRow
              label="Supplier"
              value={
                product.supplier
                  ? `${product.supplier}${product.supplier_region ? ` · ${product.supplier_region}` : ''}`
                  : product.needs_vendor_development
                    ? 'Needs vendor development'
                    : '—'
              }
            />
            <DetailRow
              label="Internal match"
              value={product.internal_match ? 'Yes' : 'No'}
            />
            <DetailRow label="Sales velocity" value={velocity} />
            <DetailRow label="Inventory health" value={inventory} />
          </div>

          {product.item_review_summarized && (
            <div className="mt-6">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">
                Review summary
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--ink)]">
                {product.item_review_summarized}
              </p>
            </div>
          )}

          {product.item_review_evidence.length > 0 && (
            <div className="mt-5">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">
                Review evidence
              </p>
              <ul className="mt-2 space-y-1.5 text-sm leading-6 text-[var(--ink-soft)]">
                {product.item_review_evidence.slice(0, 6).map((line, index) => (
                  <li key={index} className="flex gap-2">
                    <span className="text-[var(--accent-deep)]">•</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {product.item_detail && (
            <div className="mt-5">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">
                Amazon listing detail
              </p>
              <p className="mt-1 text-sm leading-6 text-[var(--ink-soft)]">{product.item_detail}</p>
            </div>
          )}

          {product.gliner_entities.length > 0 && (
            <div className="mt-5">
              <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">
                Extracted entities
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                {product.gliner_entities.map((entity, index) => (
                  <span
                    key={`${entity.text}-${index}`}
                    className="rounded-full bg-[var(--accent-muted)] px-2 py-0.5 text-[var(--accent-deep)]"
                  >
                    {entity.label}: {entity.text}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[var(--line-soft)] bg-[var(--bg-app)] px-7 py-4 text-xs text-[var(--ink-soft)]">
          <span>
            {product.asin ? `ASIN ${product.asin}` : 'No ASIN'}
          </span>
          {product.source_url ? (
            <a
              href={product.source_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-full bg-[var(--accent)] px-4 py-1.5 text-xs font-semibold text-white transition hover:opacity-90"
            >
              Open on Amazon ↗
            </a>
          ) : (
            <span>No source link</span>
          )}
        </div>
      </motion.div>
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

export default App;
