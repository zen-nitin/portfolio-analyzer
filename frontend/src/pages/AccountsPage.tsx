import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  useAccounts,
  useCreateAccount,
  useSyncAccount,
  useAuthStatus,
  useLoginUrl,
  useCreateSession,
} from '../hooks/useAccounts'
import { useAIProviders } from '../hooks/useInsights'
import { importTransactions } from '../api/endpoints'
import LoadingState from '../components/ui/LoadingState'
import ErrorState from '../components/ui/ErrorState'
import EmptyState from '../components/ui/EmptyState'
import { AuthStatusBadge } from '../components/ui/StatusBadge'
import type { Account } from '../api/types'

// Per-account row with status, connect, sync actions
function AccountRow({ account }: { account: Account }) {
  const statusQ = useAuthStatus(account.id)
  const loginMutation = useLoginUrl()
  const syncMutation = useSyncAccount()

  const [syncMsg, setSyncMsg] = useState('')

  async function handleConnect() {
    try {
      const { login_url } = await loginMutation.mutateAsync(account.id)
      window.open(login_url, '_blank', 'noopener,noreferrer')
    } catch (err) {
      console.error(err)
    }
  }

  async function handleSync() {
    setSyncMsg('')
    try {
      const res = await syncMutation.mutateAsync(account.id)
      setSyncMsg(res.message ?? 'Synced!')
      setTimeout(() => setSyncMsg(''), 4000)
    } catch (err) {
      setSyncMsg(err instanceof Error ? err.message : 'Sync failed.')
    }
  }

  const status = statusQ.data?.status

  return (
    <div className="account-card">
      <div className="account-card-header">
        <div>
          <div className="account-label">{account.label}</div>
          <div className="account-broker">{account.broker} · {account.api_key.slice(0, 6)}…</div>
        </div>
        <div>
          {status && <AuthStatusBadge status={status} />}
          {statusQ.isLoading && <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Checking…</span>}
        </div>
      </div>

      <div className="account-actions">
        <button
          className="btn btn-secondary btn-sm"
          onClick={handleConnect}
          disabled={loginMutation.isPending}
        >
          {loginMutation.isPending ? 'Opening…' : '⟳ Connect to Zerodha'}
        </button>

        {status === 'connected' && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleSync}
            disabled={syncMutation.isPending}
          >
            {syncMutation.isPending ? 'Syncing…' : '↻ Sync'}
          </button>
        )}

        {syncMsg && (
          <span style={{ fontSize: 12, color: 'var(--positive)' }}>{syncMsg}</span>
        )}
        {loginMutation.isError && (
          <span style={{ fontSize: 12, color: 'var(--negative)' }}>
            {loginMutation.error instanceof Error ? loginMutation.error.message : 'Error'}
          </span>
        )}
      </div>
    </div>
  )
}

// CSV Import widget
function CSVImport({ accounts }: { accounts: Account[] }) {
  const [file, setFile] = useState<File | null>(null)
  const [accountId, setAccountId] = useState('')
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'err'>('idle')
  const [msg, setMsg] = useState('')
  const [drag, setDrag] = useState(false)

  async function handleImport() {
    if (!file) return
    setStatus('loading')
    try {
      const res = await importTransactions(file, accountId || undefined)
      setStatus('ok')
      setMsg(res.message ?? 'Import successful!')
      setFile(null)
    } catch (err) {
      setStatus('err')
      setMsg(err instanceof Error ? err.message : 'Import failed.')
    }
  }

  return (
    <div className="card">
      <div className="card-title">Import Tradebook CSV</div>

      {accounts.length > 0 && (
        <div className="form-group">
          <label className="form-label">Account (optional)</label>
          <select
            className="form-select"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          >
            <option value="">— None —</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
        </div>
      )}

      <div
        className={`upload-area${drag ? ' drag-over' : ''}`}
        onClick={() => document.getElementById('csv-upload-input')?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          const f = e.dataTransfer.files[0]
          if (f) setFile(f)
        }}
      >
        <div className="upload-icon">📂</div>
        {file ? (
          <div className="upload-text"><strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)</div>
        ) : (
          <div className="upload-text">Drag &amp; drop a CSV or click to browse</div>
        )}
        <input
          id="csv-upload-input"
          type="file"
          accept=".csv"
          style={{ display: 'none' }}
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {file && (
        <button
          className="btn btn-primary"
          style={{ marginTop: 14 }}
          onClick={handleImport}
          disabled={status === 'loading'}
        >
          {status === 'loading' ? 'Importing…' : 'Upload & Import'}
        </button>
      )}

      {status === 'ok' && <div style={{ marginTop: 10, color: 'var(--positive)', fontSize: 13 }}>✓ {msg}</div>}
      {status === 'err' && <div className="error-state" style={{ marginTop: 10 }}>{msg}</div>}
    </div>
  )
}

// Zerodha callback handler — POST session from request_token in URL
function ZerodhaCallback() {
  const [searchParams] = useSearchParams()
  const rt = searchParams.get('request_token')
  const accountsQ = useAccounts()
  const sessionMutation = useCreateSession()
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')

  useEffect(() => {
    if (accountsQ.data?.length && !selectedId) {
      setSelectedId(accountsQ.data[0].id)
    }
  }, [accountsQ.data, selectedId])

  if (!rt) return null

  async function handleExchange() {
    if (!selectedId || !rt) return
    try {
      await sessionMutation.mutateAsync({ id: selectedId, request_token: rt })
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to exchange token.')
    }
  }

  return (
    <div className="card" style={{ marginBottom: 24, borderColor: 'var(--accent)' }}>
      <div className="card-title" style={{ color: 'var(--accent)' }}>Zerodha Login Callback</div>
      {done ? (
        <div style={{ color: 'var(--positive)', fontSize: 13 }}>✓ Session created! Your account is now connected.</div>
      ) : (
        <>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 12 }}>
            Received a request token. Select the account and complete login.
          </p>
          <div className="form-group">
            <label className="form-label">Account</label>
            <select
              className="form-select"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {accountsQ.data?.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
          </div>
          {error && <div className="error-state" style={{ marginBottom: 10 }}>{error}</div>}
          <button
            className="btn btn-primary"
            onClick={handleExchange}
            disabled={sessionMutation.isPending || !selectedId}
          >
            {sessionMutation.isPending ? 'Connecting…' : 'Complete Login'}
          </button>
        </>
      )}
    </div>
  )
}

// Add account form
function AddAccountForm() {
  const createMutation = useCreateAccount()
  const [form, setForm] = useState({
    label: '',
    broker: 'zerodha',
    api_key: '',
    api_secret: '',
  })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr('')
    setMsg('')
    if (!form.label || !form.api_key || !form.api_secret) {
      setErr('All fields are required.')
      return
    }
    try {
      await createMutation.mutateAsync(form)
      setMsg('Account added!')
      setForm({ label: '', broker: 'zerodha', api_key: '', api_secret: '' })
      setTimeout(() => setMsg(''), 3000)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to create account.')
    }
  }

  return (
    <div className="card">
      <div className="card-title">Add New Account</div>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label className="form-label">Label</label>
          <input
            className="form-input"
            placeholder="e.g. My Zerodha"
            value={form.label}
            onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
          />
        </div>
        <div className="form-group">
          <label className="form-label">Broker</label>
          <select
            className="form-select"
            value={form.broker}
            onChange={(e) => setForm((f) => ({ ...f, broker: e.target.value }))}
          >
            <option value="zerodha">Zerodha</option>
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">API Key</label>
          <input
            className="form-input"
            placeholder="Kite API Key"
            value={form.api_key}
            onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
          />
        </div>
        <div className="form-group">
          <label className="form-label">API Secret</label>
          <input
            type="password"
            className="form-input"
            placeholder="Kite API Secret"
            value={form.api_secret}
            onChange={(e) => setForm((f) => ({ ...f, api_secret: e.target.value }))}
          />
        </div>
        {err && <div className="error-state" style={{ marginBottom: 10 }}>{err}</div>}
        {msg && <div style={{ color: 'var(--positive)', fontSize: 13, marginBottom: 10 }}>✓ {msg}</div>}
        <button
          type="submit"
          className="btn btn-primary"
          disabled={createMutation.isPending}
        >
          {createMutation.isPending ? 'Adding…' : '+ Add Account'}
        </button>
      </form>
    </div>
  )
}

export default function AccountsPage() {
  const accountsQ = useAccounts()
  const providersQ = useAIProviders()

  if (accountsQ.isLoading) return <LoadingState message="Loading accounts…" />
  if (accountsQ.isError) return <ErrorState error={accountsQ.error} context="Accounts" />

  const accounts = accountsQ.data ?? []

  return (
    <div>
      <ZerodhaCallback />

      <div className="two-col" style={{ alignItems: 'start' }}>
        <div>
          {/* Accounts list */}
          <div className="section">
            <div className="section-title">
              Connected Accounts ({accounts.length})
            </div>
            {accounts.length === 0 ? (
              <EmptyState
                icon="⊕"
                title="No accounts yet"
                description="Add your Zerodha account to get started."
              />
            ) : (
              <div className="account-list">
                {accounts.map((acc) => (
                  <AccountRow key={acc.id} account={acc} />
                ))}
              </div>
            )}
          </div>

          {/* CSV import */}
          <CSVImport accounts={accounts} />
        </div>

        <div>
          {/* Add account form */}
          <AddAccountForm />

          {/* AI Providers */}
          <div className="card" style={{ marginTop: 20 }}>
            <div className="card-title">AI Providers</div>
            {providersQ.isLoading && <LoadingState />}
            {providersQ.isError && <ErrorState error={providersQ.error} />}
            {providersQ.data && (
              <div className="provider-list">
                {providersQ.data.map((p) => (
                  <div key={p.name} className="provider-item">
                    <span className={`provider-dot ${p.active && p.configured ? 'active' : 'inactive'}`} />
                    <span className="provider-name">{p.name}</span>
                    <span className="provider-status">
                      {p.configured
                        ? p.active
                          ? 'Active'
                          : 'Configured'
                        : 'Not configured'}
                    </span>
                  </div>
                ))}
                {providersQ.data.length === 0 && (
                  <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>No AI providers registered.</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
