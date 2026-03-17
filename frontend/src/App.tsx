import { Routes, Route } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import MarketMonitor from './pages/MarketMonitor'
import TradeIdeas from './pages/TradeIdeas'
import Positions from './pages/Positions'
import Journal from './pages/Journal'
import Analytics from './pages/Analytics'
import SystemHealth from './pages/SystemHealth'
import Settings from './pages/Settings'
import Agents from './pages/Agents'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="market" element={<MarketMonitor />} />
        <Route path="agents" element={<Agents />} />
        <Route path="ideas" element={<TradeIdeas />} />
        <Route path="positions" element={<Positions />} />
        <Route path="journal" element={<Journal />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="system" element={<SystemHealth />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
