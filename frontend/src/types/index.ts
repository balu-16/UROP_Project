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
  reasoningMetadata?: Record<string, unknown>;
  retrievalDiagnostics?: Record<string, unknown>;
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
