import { useId } from 'react'

/** Four-point star with the QueryBuddy gradient, used as the assistant's avatar. */
export function Sparkle({ size = 28, className = '' }: { size?: number; className?: string }) {
  const gradientId = useId()
  return (
    <svg
      className={`sparkle ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="2" y1="2" x2="22" y2="22">
          <stop offset="0%" stopColor="#4f8bff" />
          <stop offset="55%" stopColor="#9b72f2" />
          <stop offset="100%" stopColor="#f472b6" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${gradientId})`}
        d="M12 1.5c.5 4.6 2.2 7.6 4.6 9.1 1.7 1 3.6 1.3 5.9 1.4-2.3.1-4.2.4-5.9 1.4-2.4 1.5-4.1 4.5-4.6 9.1-.5-4.6-2.2-7.6-4.6-9.1C5.7 12.4 3.8 12.1 1.5 12c2.3-.1 4.2-.4 5.9-1.4C9.8 9.1 11.5 6.1 12 1.5Z"
      />
    </svg>
  )
}
