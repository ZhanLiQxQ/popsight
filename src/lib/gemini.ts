import {
  AgentLog,
  Conversation,
  LongTermMemoryItem,
  MacroSuggestion,
  ScanSession,
} from '../types';

const JSON_HEADERS = {
  'Content-Type': 'application/json',
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export interface BootstrapPayload {
  conversations: Conversation[];
  memories: LongTermMemoryItem[];
  scanSessions: ScanSession[];
  agentLogs: AgentLog[];
  macros: MacroSuggestion[];
}

export async function getBootstrap(userId = 'default-user') {
  return request<BootstrapPayload>(`/api/bootstrap?user_id=${encodeURIComponent(userId)}`);
}

export async function getMacroDiscoveries(userId = 'default-user') {
  const payload = await getBootstrap(userId);
  return payload.macros;
}

export async function getAgentAnalysis(topic: string, userId = 'default-user') {
  return request<{
    conversation: Conversation;
    scanSession: ScanSession;
    agentLogs: AgentLog[];
  }>('/api/scan', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ topic, userId }),
  });
}

export async function chatWithAgent(input: {
  conversationId?: string | null;
  scanSessionId?: string | null;
  message: string;
  userId?: string;
  selectedProductId?: string | null;
  selectedTrendId?: string | null;
  selectedManufacturerId?: string | null;
}) {
  return request<{
    conversation: Conversation;
    memories: LongTermMemoryItem[];
    agentLogs: AgentLog[];
  }>('/api/chat', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      conversationId: input.conversationId,
      scanSessionId: input.scanSessionId,
      userId: input.userId || 'default-user',
      message: input.message,
      selectedProductId: input.selectedProductId,
      selectedTrendId: input.selectedTrendId,
      selectedManufacturerId: input.selectedManufacturerId,
    }),
  });
}

export async function saveMemory(input: {
  userId?: string;
  conversationId?: string | null;
  scanSessionId?: string | null;
  kind: LongTermMemoryItem['kind'];
  title: string;
  content: string;
}) {
  return request<{
    memory: LongTermMemoryItem;
    memories: LongTermMemoryItem[];
  }>('/api/memory', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      userId: input.userId || 'default-user',
      conversationId: input.conversationId,
      scanSessionId: input.scanSessionId,
      kind: input.kind,
      title: input.title,
      content: input.content,
    }),
  });
}
