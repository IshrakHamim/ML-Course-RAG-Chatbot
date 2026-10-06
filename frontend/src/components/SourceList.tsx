import type { Source } from '../api/types'

function label(source: Source): string {
  return source.page != null ? `${source.title}, p. ${source.page}` : source.title
}

export function SourceList({ sources }: { sources: Source[] }) {
  return (
    <div className="sources">
      <span className="sources-heading">Sources</span>
      <ul aria-label="Sources">
        {sources.map((source) => (
          <li key={`${source.title}|${source.page}|${source.url}`}>
            {source.url ? (
              <a href={source.url} target="_blank" rel="noreferrer">
                {source.title}
              </a>
            ) : (
              label(source)
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
