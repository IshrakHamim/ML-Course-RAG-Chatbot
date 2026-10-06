import { useState } from 'react'
import type { Source } from '../api/types'
import { PdfViewer, type PdfTarget } from './PdfViewer'

function label(source: Source): string {
  return source.page != null ? `${source.title}, p. ${source.page}` : source.title
}

export function SourceList({ sources }: { sources: Source[] }) {
  const [viewing, setViewing] = useState<PdfTarget | null>(null)
  return (
    <div className="sources">
      <span className="sources-heading">Sources</span>
      <ul aria-label="Sources">
        {sources.map((source) => {
          const documentId = source.source_type === 'pdf' ? source.document_id : null
          return (
            <li key={`${source.title}|${source.page}|${source.url}`}>
              {source.url ? (
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
              ) : documentId ? (
                <button
                  type="button"
                  className="link"
                  title="View the PDF"
                  onClick={() => setViewing({ documentId, title: source.title, page: source.page })}
                >
                  {label(source)}
                </button>
              ) : (
                label(source)
              )}
            </li>
          )
        })}
      </ul>
      {viewing && <PdfViewer {...viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}
