import { Routes, Route } from 'react-router-dom'
import { AccountProvider } from './context/AccountContext'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import HoldingsPage from './pages/HoldingsPage'
import WatchlistPage from './pages/WatchlistPage'
import InsightsPage from './pages/InsightsPage'
import AccountsPage from './pages/AccountsPage'

export default function App() {
  return (
    <AccountProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="holdings" element={<HoldingsPage />} />
          <Route path="watchlist" element={<WatchlistPage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="accounts/callback" element={<AccountsPage />} />
        </Route>
      </Routes>
    </AccountProvider>
  )
}
