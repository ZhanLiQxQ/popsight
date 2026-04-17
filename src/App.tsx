import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Blocks,
  BookOpen,
  Brain,
  ChevronRight,
  Clock3,
  Database,
  LayoutDashboard,
  MessageSquare,
  Pin,
  Radar,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  TrendingUp,
  Truck,
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
import { chatWithAgent, getAgentAnalysis, getBootstrap, saveMemory } from './lib/gemini';

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

  const chatEndRef = useRef<HTMLDivElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const fallbackAssistantMessageRef = useRef<ChatMessage>(createInitialAssistantMessage());

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

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, isChatLoading]);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [agentLogs]);

  useEffect(() => {
    const initialSession = scanSessions[0];
    if (!currentScanId && initialSession) setCurrentScanId(initialSession.id);
    if (!activeConversationId && conversations[0]) setActiveConversationId(conversations[0].id);
  }, [scanSessions, currentScanId, conversations, activeConversationId]);

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
        setConversations(data.conversations);
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

  const handleSendMessage = async () => {
    if (!chatInput.trim() || isChatLoading) return;

    const currentConversationId =
      activeConversationId || ensureConversation(topic || currentScan?.topic || 'New sourcing thread', currentScanId ?? undefined);
    const pendingMessage = chatInput.trim();
    setChatInput('');
    setIsChatLoading(true);

    try {
      const response = await chatWithAgent({
        conversationId: currentConversationId,
        scanSessionId: currentScanId,
        message: pendingMessage,
        selectedProductId,
        selectedTrendId,
        selectedManufacturerId,
      });

      setConversations((previous) => [
        response.conversation,
        ...previous.filter((item) => item.id !== response.conversation.id),
      ]);
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

  const navItems: { id: AppView; label: string; icon: typeof LayoutDashboard; helper: string }[] = [
    { id: 'workspace', label: 'Workspace', icon: LayoutDashboard, helper: 'Search + results + chat' },
    { id: 'conversations', label: 'Conversations', icon: MessageSquare, helper: 'Stored threads' },
    { id: 'memory', label: 'Memory', icon: Brain, helper: 'Long-term knowledge' },
    { id: 'agents', label: 'Agent Status', icon: Blocks, helper: 'Detailed runtime state' },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-app)] text-[var(--ink-strong)]">
      <aside className="flex w-72 flex-col border-r border-[var(--line-soft)] bg-[var(--panel-strong)] text-white">
        <div className="border-b border-white/10 px-6 py-6">
          <div className="mb-2 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent)]/15 text-[var(--accent)]">
              <Radar className="h-5 w-5" />
            </div>
            <div>
              <p className="text-lg font-semibold tracking-tight">PopSight</p>
              <p className="text-xs text-white/50">CPG sourcing cockpit</p>
            </div>
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
            <p className="mb-1 text-sm font-medium text-white/90">{currentScan?.topic || 'No active scan'}</p>
            <p className="text-xs text-white/50">
              {currentScan ? `${opportunities.length} products, ${trends.length} trends, ${manufacturers.length} suppliers` : 'Run a scan to build working memory.'}
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.2em] text-white/45">Memory split</p>
              <Database className="h-3.5 w-3.5 text-white/35" />
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <p className="text-white/80">Short-term</p>
                <p className="text-white/45">Current scan, selected product, recent messages</p>
              </div>
              <div>
                <p className="text-white/80">Long-term</p>
                <p className="text-white/45">Pinned preferences, reusable insights, decisions</p>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1">
        <section className="flex min-w-0 flex-1 flex-col">
          <header className="border-b border-[var(--line-soft)] bg-white/85 px-8 py-5 backdrop-blur">
            <div className="flex items-center justify-between gap-6">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {activeView === 'workspace' && 'Sourcing Workspace'}
                  {activeView === 'conversations' && 'Conversation History'}
                  {activeView === 'memory' && 'Memory Center'}
                  {activeView === 'agents' && 'Agent Status'}
                </h1>
                <p className="mt-1 text-sm text-[var(--ink-soft)]">
                  {activeView === 'workspace' &&
                    'Keep the main page focused on search, results, and contextual follow-up questions.'}
                  {activeView === 'conversations' &&
                    'Every follow-up thread is saved so users can return without losing context.'}
                  {activeView === 'memory' &&
                    'Only durable business knowledge belongs in long-term memory; everything else stays session-scoped.'}
                  {activeView === 'agents' &&
                    'Operational detail has been moved out of the main page into a dedicated runtime panel.'}
                </p>
              </div>

              {activeView === 'workspace' && (
                <div className="flex w-full max-w-2xl items-center gap-3">
                  <div className="relative flex-1">
                    <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--ink-faint)]" />
                    <input
                      type="text"
                      value={topic}
                      onChange={(event) => setTopic(event.target.value)}
                      onKeyDown={(event) => event.key === 'Enter' && runAnalysis()}
                      placeholder="Search trends, product formats, or retail whitespace"
                      className="h-12 w-full rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] pl-11 pr-4 text-sm outline-none transition focus:border-[var(--accent)]"
                    />
                  </div>
                  <button
                    onClick={() => runAnalysis()}
                    disabled={isLoading}
                    className="flex h-12 items-center gap-2 rounded-2xl bg-[var(--accent)] px-5 text-sm font-medium text-[var(--panel-strong)] transition hover:brightness-95 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                    Scan
                  </button>
                </div>
              )}
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-8 py-7">
            {activeView === 'workspace' && (
              <div className="space-y-8">
                <section className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6 shadow-[0_18px_50px_rgba(16,24,40,0.08)]">
                  <div className="mb-5 flex items-center justify-between">
                    <div>
                      <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Macro cues</p>
                      <h2 className="mt-1 text-xl font-semibold">Start from what is moving, not from a blank search box</h2>
                    </div>
                    <div className="rounded-full bg-[var(--bg-app)] px-3 py-1 text-xs text-[var(--ink-soft)]">
                      {isDiscovering ? 'Updating suggestions' : 'Autonomous suggestions'}
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                    {isDiscovering
                      ? Array.from({ length: 4 }).map((_, index) => (
                          <div
                            key={index}
                            className="h-36 animate-pulse rounded-3xl border border-[var(--line-soft)] bg-[var(--bg-app)]"
                          />
                        ))
                      : macros.slice(0, 4).map((macro) => (
                          <button
                            key={macro.category}
                            onClick={() => runAnalysis(macro.category)}
                            className="rounded-3xl border border-[var(--line-soft)] bg-white p-5 text-left transition hover:-translate-y-0.5 hover:border-[var(--accent)]"
                          >
                            <div className="mb-3 flex items-center justify-between">
                              <span className="rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--accent-deep)]">
                                {macro.region}
                              </span>
                              <span className="text-[11px] text-[var(--ink-faint)]">{macro.growthIndicator}</span>
                            </div>
                            <p className="mb-2 text-base font-semibold">{macro.category}</p>
                            <p className="text-sm leading-6 text-[var(--ink-soft)]">{macro.reason}</p>
                          </button>
                        ))}
                  </div>
                </section>

                <section className="grid gap-5 xl:grid-cols-[1.4fr_0.9fr]">
                  <div className="space-y-5">
                    <div className="grid gap-4 md:grid-cols-3">
                      <MetricCard
                        label="Products"
                        value={opportunities.length}
                        helper={currentScan ? 'Follow-up ready' : 'Waiting for scan'}
                        icon={<Target className="h-4 w-4" />}
                      />
                      <MetricCard
                        label="Trends"
                        value={trends.length}
                        helper={currentScan ? 'Attached to current topic' : 'Waiting for scan'}
                        icon={<TrendingUp className="h-4 w-4" />}
                      />
                      <MetricCard
                        label="Suppliers"
                        value={manufacturers.length}
                        helper={currentScan ? 'Visible on demand' : 'Waiting for scan'}
                        icon={<Truck className="h-4 w-4" />}
                      />
                    </div>

                    <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Results</p>
                          <h3 className="mt-1 text-lg font-semibold">{currentScan?.topic || 'No active scan yet'}</h3>
                        </div>
                        <div className="flex gap-2 rounded-full bg-[var(--bg-app)] p-1">
                          {[
                            { id: 'products', label: 'Products' },
                            { id: 'trends', label: 'Trends' },
                            { id: 'supply', label: 'Supply' },
                          ].map((tab) => (
                            <button
                              key={tab.id}
                              onClick={() => setActiveTab(tab.id as ResultTab)}
                              className={`rounded-full px-4 py-2 text-sm transition ${
                                activeTab === tab.id
                                  ? 'bg-white text-[var(--ink-strong)] shadow-sm'
                                  : 'text-[var(--ink-soft)]'
                              }`}
                            >
                              {tab.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      {currentScan && (
                        <div className="mb-5 rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] p-4 text-sm text-[var(--ink-soft)]">
                          {currentScan.summary}
                        </div>
                      )}

                      <AnimatePresence mode="wait">
                        {activeTab === 'products' && (
                          <motion.div
                            key="products"
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -6 }}
                            className="grid gap-4"
                          >
                            {opportunities.length === 0 && <EmptyState text="Run a scan to surface product opportunities." />}
                            {opportunities.map((product) => (
                              <button
                                key={product.id}
                                onClick={() => {
                                  setSelectedProductId(product.id);
                                  setSelectedTrendId(null);
                                  setSelectedManufacturerId(null);
                                }}
                                className={`rounded-3xl border p-5 text-left transition ${
                                  selectedProductId === product.id
                                    ? 'border-[var(--accent)] bg-[var(--accent-muted)]/55'
                                    : 'border-[var(--line-soft)] bg-white hover:border-[var(--accent)]/50'
                                }`}
                              >
                                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                                  <div>
                                    <p className="text-lg font-semibold">{product.name}</p>
                                    <p className="text-sm text-[var(--ink-soft)]">
                                      {product.brand} · {product.origin}
                                    </p>
                                  </div>
                                  <div className="rounded-2xl bg-[var(--panel-strong)] px-3 py-2 text-right text-white">
                                    <div className="text-[11px] uppercase tracking-[0.16em] text-white/55">traction</div>
                                    <div className="text-lg font-semibold">{product.tractionScore}</div>
                                  </div>
                                </div>
                                <div className="mb-3 flex flex-wrap gap-2 text-xs">
                                  <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{product.category}</span>
                                  <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{product.velocity}</span>
                                  <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{product.distributionStatus}</span>
                                  <span className="rounded-full bg-[var(--bg-app)] px-3 py-1">{product.pricePoint}</span>
                                </div>
                                <p className="text-sm leading-6 text-[var(--ink-soft)]">{product.description}</p>
                              </button>
                            ))}
                          </motion.div>
                        )}

                        {activeTab === 'trends' && (
                          <motion.div
                            key="trends"
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -6 }}
                            className="grid gap-4 md:grid-cols-2"
                          >
                            {trends.length === 0 && <EmptyState text="Trend cards will appear after a scan." />}
                            {trends.map((trend) => (
                              <button
                                key={trend.id}
                                onClick={() => {
                                  setSelectedTrendId(trend.id);
                                  setSelectedProductId(null);
                                  setSelectedManufacturerId(null);
                                }}
                                className={`rounded-3xl border p-5 text-left transition ${
                                  selectedTrendId === trend.id
                                    ? 'border-[var(--accent)] bg-[var(--accent-muted)]/55'
                                    : 'border-[var(--line-soft)] bg-white hover:border-[var(--accent)]/50'
                                }`}
                              >
                                <div className="mb-3 flex items-center justify-between gap-3">
                                  <span className="rounded-full bg-[var(--bg-app)] px-3 py-1 text-xs">{trend.category}</span>
                                  <span className="text-xs text-[var(--ink-soft)]">{trend.sentiment}</span>
                                </div>
                                <p className="mb-2 text-lg font-semibold">{trend.topic}</p>
                                <p className="mb-3 text-sm text-[var(--ink-soft)]">{trend.growth}</p>
                                <div className="flex flex-wrap gap-2">
                                  {trend.topKeywords.map((keyword) => (
                                    <span
                                      key={keyword}
                                      className="rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-xs text-[var(--accent-deep)]"
                                    >
                                      #{keyword}
                                    </span>
                                  ))}
                                </div>
                              </button>
                            ))}
                          </motion.div>
                        )}

                        {activeTab === 'supply' && (
                          <motion.div
                            key="supply"
                            initial={{ opacity: 0, y: 6 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -6 }}
                            className="grid gap-4 md:grid-cols-2"
                          >
                            {manufacturers.length === 0 && <EmptyState text="Supplier candidates will appear after a scan." />}
                            {manufacturers.map((manufacturer) => (
                              <button
                                key={manufacturer.id}
                                onClick={() => {
                                  setSelectedManufacturerId(manufacturer.id);
                                  setSelectedProductId(null);
                                  setSelectedTrendId(null);
                                }}
                                className={`rounded-3xl border p-5 text-left transition ${
                                  selectedManufacturerId === manufacturer.id
                                    ? 'border-[var(--accent)] bg-[var(--accent-muted)]/55'
                                    : 'border-[var(--line-soft)] bg-white hover:border-[var(--accent)]/50'
                                }`}
                              >
                                <div className="mb-2 flex items-center justify-between gap-3">
                                  <p className="text-lg font-semibold">{manufacturer.name}</p>
                                  <span className="rounded-full bg-[var(--bg-app)] px-3 py-1 text-xs">
                                    {manufacturer.capacity}
                                  </span>
                                </div>
                                <p className="mb-3 text-sm text-[var(--ink-soft)]">{manufacturer.location}</p>
                                <div className="flex flex-wrap gap-2">
                                  {manufacturer.specialization.map((item) => (
                                    <span key={item} className="rounded-full bg-[var(--bg-app)] px-3 py-1 text-xs">
                                      {item}
                                    </span>
                                  ))}
                                </div>
                              </button>
                            ))}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>

                  <div className="space-y-5">
                    <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                      <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Selected context</p>
                      <div className="mt-4 space-y-4">
                        {selectedProduct && (
                          <FocusCard
                            title={selectedProduct.name}
                            subtitle={`${selectedProduct.brand} · ${selectedProduct.origin}`}
                            body={selectedProduct.description}
                          />
                        )}
                        {selectedTrend && (
                          <FocusCard title={selectedTrend.topic} subtitle={selectedTrend.category} body={selectedTrend.growth} />
                        )}
                        {selectedManufacturer && (
                          <FocusCard
                            title={selectedManufacturer.name}
                            subtitle={selectedManufacturer.location}
                            body={selectedManufacturer.specialization.join(', ')}
                          />
                        )}
                        {!selectedProduct && !selectedTrend && !selectedManufacturer && (
                          <EmptyState text="Pick a product, trend, or supplier to make follow-up chat more precise." />
                        )}
                      </div>
                    </div>

                    <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                      <div className="mb-4 flex items-center justify-between">
                        <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Recent threads</p>
                        <BookOpen className="h-4 w-4 text-[var(--ink-faint)]" />
                      </div>
                      <div className="space-y-3">
                        {recentConversations.length === 0 && <EmptyState text="Conversation history will appear here." compact />}
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
                              <div>
                                <p className="text-sm font-medium">{conversation.title}</p>
                                <p className="text-xs text-[var(--ink-soft)]">{conversation.messages.length} messages</p>
                              </div>
                              <span className="text-xs text-[var(--ink-faint)]">{formatTime(conversation.updatedAt)}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>
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
                    {chatMessages.map((message) => (
                      <div
                        key={message.id}
                        className={`rounded-3xl px-4 py-3 ${
                          message.role === 'user'
                            ? 'ml-auto max-w-[85%] bg-[var(--panel-strong)] text-white'
                            : 'max-w-[90%] border border-[var(--line-soft)] bg-white'
                        }`}
                      >
                        <p className="text-sm leading-6">{message.content}</p>
                        <p
                          className={`mt-2 text-[11px] ${
                            message.role === 'user' ? 'text-white/55' : 'text-[var(--ink-faint)]'
                          }`}
                        >
                          {formatTime(message.timestamp)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeView === 'memory' && (
              <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
                <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                  <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Memory design guidance</p>
                  <div className="mt-4 space-y-4 text-sm leading-7 text-[var(--ink-soft)]">
                    <div className="rounded-3xl border border-[var(--line-soft)] bg-white p-5">
                      <p className="mb-2 font-semibold text-[var(--ink-strong)]">Short-term memory</p>
                      <p>
                        Use it for the current scan, selected product or supplier, and the most recent chat turns.
                        This is the right place for "based on these results, compare the top 3" style follow-up.
                      </p>
                    </div>
                    <div className="rounded-3xl border border-[var(--line-soft)] bg-white p-5">
                      <p className="mb-2 font-semibold text-[var(--ink-strong)]">Long-term memory</p>
                      <p>
                        Save only durable facts: buyer preferences, target price bands, repeated sourcing rules,
                        approved suppliers, and confirmed strategic decisions. Raw chat logs should not all be
                        promoted here.
                      </p>
                    </div>
                    <div className="rounded-3xl border border-[var(--line-soft)] bg-white p-5">
                      <p className="mb-2 font-semibold text-[var(--ink-strong)]">Chat history</p>
                      <p>
                        Chat history should be stored as conversation records. It supports recall and auditability,
                        but it is neither pure short-term nor pure long-term memory. Think of it as the source layer
                        from which you selectively extract long-term memory.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="rounded-[28px] border border-[var(--line-soft)] bg-[var(--surface)] p-6">
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Saved long-term memory</p>
                    <button
                      onClick={() =>
                        handleSaveMemory({
                          kind: 'user_preference',
                          title: 'Example preference',
                          content: 'Prefer under-distributed Asian functional beverages with import-ready pricing.',
                        })
                      }
                      className="rounded-full border border-[var(--line-soft)] px-3 py-1.5 text-xs transition hover:border-[var(--accent)]"
                    >
                      Add sample
                    </button>
                  </div>

                  <div className="space-y-3">
                    {longTermMemories.length === 0 && (
                      <EmptyState text="Save durable insights here instead of keeping them mixed into the main dashboard." />
                    )}
                    {longTermMemories.map((memory) => (
                      <div key={memory.id} className="rounded-3xl border border-[var(--line-soft)] bg-white p-5">
                        <div className="mb-2 flex items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <span className="rounded-full bg-[var(--accent-muted)] px-2.5 py-1 text-[11px] capitalize text-[var(--accent-deep)]">
                              {memory.kind.replace('_', ' ')}
                            </span>
                            {memory.pinned && <Pin className="h-3.5 w-3.5 text-[var(--accent-deep)]" />}
                          </div>
                          <span className="text-[11px] text-[var(--ink-faint)]">{formatTime(memory.updatedAt)}</span>
                        </div>
                        <p className="mb-2 text-base font-semibold">{memory.title}</p>
                        <p className="text-sm leading-6 text-[var(--ink-soft)]">{memory.content}</p>
                      </div>
                    ))}
                  </div>
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

        <aside className="flex w-[420px] min-w-[380px] flex-col border-l border-[var(--line-soft)] bg-white">
          <div className="border-b border-[var(--line-soft)] px-5 py-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-[var(--ink-faint)]">Chatbot</p>
                <h2 className="mt-1 text-lg font-semibold">Follow up on the current scan</h2>
              </div>
              <span className="rounded-full bg-[var(--accent-muted)] px-3 py-1 text-xs text-[var(--accent-deep)]">
                Context aware
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <ContextChip label="Topic" value={currentScan?.topic || 'None'} />
              <ContextChip label="Product" value={selectedProduct?.name || 'None'} />
              <ContextChip label="Memories" value={String(longTermMemories.length)} />
            </div>

            {pinnedMemories.length > 0 && (
              <div className="mt-4 rounded-2xl border border-[var(--line-soft)] bg-[var(--bg-app)] p-3">
                <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[var(--ink-faint)]">Pinned memory</p>
                <p className="text-sm text-[var(--ink-soft)]">{pinnedMemories[0]?.content}</p>
              </div>
            )}
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
            {chatMessages.map((message) => (
              <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[88%] rounded-[24px] px-4 py-3 ${
                    message.role === 'user'
                      ? 'bg-[var(--panel-strong)] text-white'
                      : 'border border-[var(--line-soft)] bg-[var(--surface)]'
                  }`}
                >
                  <p className="text-sm leading-6">{message.content}</p>
                  <p className={`mt-2 text-[11px] ${message.role === 'user' ? 'text-white/50' : 'text-[var(--ink-faint)]'}`}>
                    {formatTime(message.timestamp)}
                  </p>
                </div>
              </div>
            ))}

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
                onClick={() =>
                  handleSaveMemory({
                    kind: 'decision',
                    title: selectedProduct?.name || currentScan?.topic || 'Saved decision',
                    content:
                      selectedProduct?.description ||
                      currentScan?.summary ||
                      'User manually saved the current working conclusion.',
                  })
                }
                className="rounded-full border border-[var(--line-soft)] px-3 py-1.5 text-xs transition hover:border-[var(--accent)]"
              >
                Save current insight
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
      </main>
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
    <div className="rounded-full bg-[var(--bg-app)] px-3 py-1.5 text-xs text-[var(--ink-soft)]">
      <span className="mr-1 text-[var(--ink-faint)]">{label}:</span>
      <span className="font-medium text-[var(--ink-strong)]">{value}</span>
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
