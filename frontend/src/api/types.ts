// Mirrors the backend Pydantic schemas (backend/app/schemas).

export type Role = 'user' | 'admin'

export interface User {
  id: string
  email: string
  role: Role
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface Source {
  // Missing on answers saved before PDFs could be viewed.
  document_id?: string | null
  title: string
  source_type: string
  page: number | null
  url: string | null
}

export type AnswerKind = 'answer' | 'fallback' | 'greeting'

export interface ChatResponse {
  answer: string
  sources: Source[]
  session_id: string
  grounded: boolean
  kind: AnswerKind
}

export interface SessionSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  role: 'user' | 'assistant'
  content: string
  sources: Source[] | null
  grounded: boolean | null
  kind: AnswerKind | null
  created_at: string
}

export interface SessionDetail {
  id: string
  title: string
  messages: Message[]
}

export interface DocumentItem {
  id: string
  title: string
  source_type: 'pdf' | 'text' | 'url'
  source: string
  chunk_count: number
  created_at: string
  duplicate: boolean
  has_file: boolean
}
