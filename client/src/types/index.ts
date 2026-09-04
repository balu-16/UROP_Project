export interface RetrievalInfo {
  depth: number; // 0,1,2
  confidence: number;
  strategy: string; // ZERO_HOP / ONE_HOP / TWO_HOP (never repurposed)
  initial_confidence?: number;
  retrieval_mode?: string; // "hybrid" when RRF fusion ran
  candidate_count?: number; // pre-rerank final set size
  reranked_count?: number; // chunks sent to context after rerank
  reranker_model?: string | null;
}

export interface Attachment {
  /** Original filename, e.g. "UG-PG Seed Grant(1).pptx" */
  name: string;
  /** Extension-derived kind used for the chip icon */
  kind: "pdf" | "slides" | "text";
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
  /** Filenames attached to the message that sent them (user messages only). */
  attachments?: Attachment[];
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
