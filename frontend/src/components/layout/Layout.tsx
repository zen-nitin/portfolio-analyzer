import { Outlet, NavLink, useLocation } from 'react-router-dom'
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
  const { selectedAccountId, setSelectedAccountId } = useAccount()

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
