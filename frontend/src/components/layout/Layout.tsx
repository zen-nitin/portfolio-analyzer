import { useState } from 'react'
import { Outlet, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getAccounts } from '../../api/endpoints'
import { useAccount } from '../../context/AccountContext'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '◈' },
  { to: '/holdings', label: 'Holdings', icon: '◉' },
  { to: '/watchlist', label: 'Watchlist', icon: '◎' },
  { to: '/insights', label: 'AI Insights', icon: '✦' },
  { to: '/accounts', label: 'Accounts', icon: '⊕' },
]

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/holdings': 'Holdings',
  '/watchlist': 'Watchlist',
  '/insights': 'AI Insights',
  '/accounts': 'Accounts & Connect',
}

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const { selectedAccountId, setSelectedAccountId } = useAccount()
  const [stockSearch, setStockSearch] = useState('')

  function handleStockSearch(e: React.FormEvent) {
    e.preventDefault()
    const sym = stockSearch.trim().toUpperCase()
    if (!sym) return
    navigate(`/stock/${encodeURIComponent(sym)}`)
    setStockSearch('')
  }

  const { data: accounts } = useQuery({
    queryKey: ['accounts'],
    queryFn: getAccounts,
  })

  const pageTitle = PAGE_TITLES[location.pathname] ?? 'Portfolio Analyzer'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h2>
            <span>Portfolio</span> Analyzer
          </h2>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {/* Stock search */}
          <form onSubmit={handleStockSearch} style={{ marginBottom: 14 }}>
            <span
              style={{
                fontSize: 11,
                textTransform: 'uppercase',
                letterSpacing: '0.8px',
                color: 'var(--text-muted)',
                fontWeight: 600,
                display: 'block',
                marginBottom: 6,
              }}
            >
              Stock Lookup
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                className="select-control"
                style={{ flex: 1, fontSize: 12, padding: '5px 8px' }}
                placeholder="Symbol…"
                value={stockSearch}
                onChange={(e) => setStockSearch(e.target.value)}
              />
              <button
                type="submit"
                style={{
                  background: 'var(--accent)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  padding: '5px 10px',
                  fontSize: 12,
                  cursor: 'pointer',
                  flexShrink: 0,
                }}
              >
                →
              </button>
            </div>
          </form>

          <div className="account-selector-wrap">
            <span className="account-selector-label">Account</span>
            <select
              className="select-control"
              value={selectedAccountId ?? ''}
              onChange={(e) => setSelectedAccountId(e.target.value || undefined)}
            >
              <option value="">All Accounts</option>
              {accounts?.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </aside>

      <div className="main-area">
        <header className="top-bar">
          <span className="top-bar-title">{pageTitle}</span>
          {selectedAccountId && accounts && (
            <span className="badge badge-flat">
              {accounts.find((a) => a.id === selectedAccountId)?.label ?? selectedAccountId}
            </span>
          )}
        </header>
        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
