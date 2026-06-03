import { ApiError } from '../../api/client'

interface Props {
  error: unknown
  context?: string
}

export default function ErrorState({ error, context }: Props) {
  if (error instanceof ApiError && error.status === 503) {
    return (
      <div className="ai-unconfigured">
        <span>⚠</span>
        <div>
          <strong>AI provider not configured.</strong>{' '}
          Go to <em>Accounts</em> to add an API key.
        </div>
      </div>
    )
  }

  const message =
    error instanceof Error ? error.message : 'An unexpected error occurred.'

  return (
    <div className="error-state">
      {context && <strong>{context}: </strong>}
      {message}
    </div>
  )
}
