import { Routes, Route } from 'react-router-dom'
import { AccountProvider } from './context/AccountContext'
import { StockModalProvider } from './context/StockModalContext'
import Layout from './components/layout/Layout'
import DashboardPage from './pages/DashboardPage'
import HoldingsPage from './pages/HoldingsPage'
import WatchlistPage from './pages/WatchlistPage'
import AccountsPage from './pages/AccountsPage'
import StockPage from './pages/StockPage'

export default function App() {
  return (
    <AccountProvider>
      <StockModalProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<DashboardPage />} />
            <Route path="holdings" element={<HoldingsPage />} />
            <Route path="watchlist" element={<WatchlistPage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="accounts/callback" element={<AccountsPage />} />
            <Route path="stock/:symbol" element={<StockPage />} />
          </Route>
        </Routes>
      </StockModalProvider>
    </AccountProvider>
  )
}
