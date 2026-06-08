import { useState } from 'react'

const CHATGPT_URL = 'https://chatgpt.com/'
const CLAUDE_URL = 'https://claude.ai/new'

/**
 * Tolerant JSON extraction: strips ```json fences / surrounding prose and falls
 * back to the first {...} or [...] span, so pasted model output "just works".
 */
export function parseLooseJson(text: string): unknown {
  let t = text.trim()
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) t = fence[1].trim()
  try {
    return JSON.parse(t)
  } catch {
    /* fall through to span extraction */
  }
  const candidates = ['{', '[']
    .map((c) => t.indexOf(c))
    .filter((i) => i >= 0)
  if (candidates.length === 0) throw new Error('No JSON object found in the pasted text.')
  const start = Math.min(...candidates)
  const end = Math.max(t.lastIndexOf('}'), t.lastIndexOf(']'))
  if (end <= start) throw new Error('Could not find a complete JSON object.')
  return JSON.parse(t.slice(start, end + 1))
}

/**
 * "Generate elsewhere" panel — copy the app's exact prompt, open ChatGPT/Claude
 * (use your subscription, no API key), then paste the JSON back to ingest it.
 *
 * `fetchPrompt` returns the assembled prompt; `onApply` ingests parsed JSON and
 * returns an error message (or null on success).
 */
export default function ExternalGenerate({
  fetchPrompt,
  onApply,
  label = 'suggestions',
}: {
  fetchPrompt: () => Promise<string>
  onApply: (parsed: unknown) => string | null
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [preparing, setPreparing] = useState(false)
  const [copied, setCopied] = useState(false)
  const [pasted, setPasted] = useState('')
  const [error, setError] = useState('')
  const [applied, setApplied] = useState(false)

  async function copyAndOpen(url: string | null) {
    setError('')
    setCopied(false)
    setPreparing(true)
    try {
      const prompt = await fetchPrompt()
      try {
        await navigator.clipboard.writeText(prompt)
        setCopied(true)
      } catch {
        // Clipboard blocked — surface the prompt so the user can copy manually.
        setError('Could not access clipboard — copy the prompt from the box below.')
        setPasted(prompt)
      }
      if (url) window.open(url, '_blank', 'noopener')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to build the prompt.')
    } finally {
      setPreparing(false)
    }
  }

  function apply() {
    setError('')
    setApplied(false)
    let parsed: unknown
    try {
      parsed = parseLooseJson(pasted)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid JSON.')
      return
    }
    const err = onApply(parsed)
    if (err) {
      setError(err)
      return
    }
    setApplied(true)
    setPasted('')
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
          padding: 0, cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 12,
        }}
      >
        <span style={{ fontSize: 10, transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none' }}>▸</span>
        Generate with ChatGPT / Claude (use your subscription, no API key)
      </button>

      {open && (
        <div className="card" style={{ marginTop: 8, padding: 12 }}>
          <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginBottom: 8 }}>
            Copies the exact prompt (with your live portfolio context) and opens the chat app.
            Paste it there, then paste the JSON it returns back here.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => copyAndOpen(CHATGPT_URL)} disabled={preparing}>
              {preparing ? 'Preparing…' : '↗ Copy & open ChatGPT'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => copyAndOpen(CLAUDE_URL)} disabled={preparing}>
              {preparing ? 'Preparing…' : '↗ Copy & open Claude'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => copyAndOpen(null)} disabled={preparing}>
              {preparing ? '…' : '⧉ Copy prompt only'}
            </button>
          </div>
          {copied && (
            <div style={{ fontSize: 11.5, color: 'var(--positive)', marginBottom: 8 }}>
              ✓ Prompt copied — paste it into the chat, then bring the JSON back below.
            </div>
          )}
          <textarea
            className="form-input"
            style={{ width: '100%', minHeight: 90, fontFamily: 'var(--font-mono)', fontSize: 12 }}
            placeholder={`Paste the JSON ${label} here…`}
            value={pasted}
            onChange={(e) => { setPasted(e.target.value); setApplied(false) }}
          />
          {error && (
            <div className="error-state" style={{ marginTop: 8, fontSize: 12 }}>{error}</div>
          )}
          {applied && (
            <div style={{ fontSize: 11.5, color: 'var(--positive)', marginTop: 8 }}>
              ✓ Applied — {label} loaded into the app.
            </div>
          )}
          <button
            className="btn btn-primary btn-sm"
            style={{ marginTop: 8 }}
            onClick={apply}
            disabled={!pasted.trim()}
          >
            Apply JSON
          </button>
        </div>
      )}
    </div>
  )
}
