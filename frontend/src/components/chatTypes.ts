import type { AnswerKind, Message, Source } from '../api/types'

export interface ChatMessageView {
  role: 'user' | 'assistant'
  content: string
  sources: Source[]
  kind: AnswerKind | null
}

export function toView(message: Message): ChatMessageView {
  return {
    role: message.role,
    content: message.content,
    sources: message.sources ?? [],
    kind: message.kind,
  }
}
