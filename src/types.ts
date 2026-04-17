export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  productIds?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  topic: string;
  scanSessionId?: string;
  createdAt: string;
  updatedAt: string;
  messages: ChatMessage[];
}

export interface LongTermMemoryItem {
  id: string;
  kind: 'user_preference' | 'product_insight' | 'supplier_note' | 'decision';
  title: string;
  content: string;
  sourceConversationId?: string;
  sourceScanSessionId?: string;
  createdAt: string;
  updatedAt: string;
  pinned: boolean;
}

export interface ScanSession {
  id: string;
  topic: string;
  createdAt: string;
  trends: Trend[];
  opportunities: Product[];
  manufacturers: Manufacturer[];
  summary: string;
}

export interface MacroSuggestion {
  category: string;
  reason: string;
  region: string;
  growthIndicator: string;
}

export interface Product {
  id: string;
  name: string;
  brand: string;
  category: string;
  origin: string;
  tractionScore: number;
  velocity: 'Rising' | 'Explosive' | 'Stable';
  distributionStatus: 'Parallel Import' | 'Under-distributed' | 'Not in US';
  pricePoint: string;
  description: string;
  image?: string;
}

export interface Trend {
  id: string;
  topic: string;
  category: string;
  growth: string;
  sentiment: 'Positive' | 'Neutral' | 'Mixed';
  topKeywords: string[];
}

export interface Manufacturer {
  id: string;
  name: string;
  location: string;
  specialization: string[];
  capacity: 'Low' | 'Medium' | 'High';
  contactStatus?: 'Identified' | 'Contacted' | 'Partner';
}

export interface AgentLog {
  id: string;
  agentName: string;
  message: string;
  timestamp: string;
  type: 'info' | 'success' | 'warning' | 'error';
}

export type AgentRole =
  | 'MacroScout'
  | 'MarketCrawler'
  | 'TrendAnalyst'
  | 'ProductSleuth'
  | 'SupplyPartner'
  | 'Strategist';

export interface AgentStatus {
  role: AgentRole;
  status: 'Idle' | 'Analyzing' | 'Searching' | 'Summarizing';
  lastAction: string;
}
