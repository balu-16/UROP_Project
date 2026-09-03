export interface RetrievalInfo {
  depth: number; // 0,1,2
  confidence: number;
  strategy: string; // ZERO_HOP / ONE_HOP / TWO_HOP
  initial_confidence?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  sessionId?: string;
  selectedArm?: string;
  sources?: SourceChunk[];
  reward?: number;
  latencyMs?: number;
  reasoningMetadata?: ReasoningMetadata;
  retrievalDiagnostics?: Record<string, unknown>;
  retrieval?: RetrievalInfo;
  stage?: string;
  followUps?: string[];
}

export interface ReasoningMetadata {
  latest?: string;
  reasoning_details?: string[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ConversationGroup {
  label: string;
  conversations: Conversation[];
}

export interface SourceChunk {
  chunk_id: string;
  document_id?: string;
  text: string;
  score: number;
  metadata: Record<string, unknown>;
  entity_ids?: string[];
}

export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface BackendSession {
  _id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
