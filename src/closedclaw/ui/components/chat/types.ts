export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  relatedMemories?: RelatedMemory[];
  metadata?: ClosedclawMessageMetadata;
}

export interface ClosedclawMessageMetadata {
  closedclaw_memories_used?: number;
  closedclaw_redactions_applied?: number;
  closedclaw_audit_id?: string;
}

export interface RelatedMemory {
  id: string;
  content: string;
  score: number;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
}

export interface ClosedclawConfig {
  apiKey?: string;
  userId: string;
  agentId?: string;
  baseUrl?: string;
  prefetchMemories?: boolean;
  useClawdBot?: boolean;
}

export type Mem0Config = ClosedclawConfig;
