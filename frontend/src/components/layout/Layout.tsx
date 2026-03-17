import { Outlet, NavLink } from 'react-router-dom'
import { 
  LayoutDashboard, 
  LineChart, 
  Lightbulb, 
  Briefcase, 
  BookOpen,
  BarChart3,
  Activity,
  Settings,
  AlertTriangle,
  Brain
} from 'lucide-react'
import { useSystemStatus } from '../../hooks/useSystemStatus'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/market', icon: LineChart, label: 'Market Monitor' },
  { to: '/agents', icon: Brain, label: 'Agents' },
  { to: '/ideas', icon: Lightbulb, label: 'Trade Ideas' },
  { to: '/positions', icon: Briefcase, label: 'Positions' },
  { to: '/journal', icon: BookOpen, label: 'Journal' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/system', icon: Activity, label: 'System Health' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout() {
  const { data: status } = useSystemStatus()
  
  const tradingMode = status?.trading_mode || 'paper'
  const isLive = tradingMode === 'live'
  
  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-[var(--bg-secondary)] border-r border-[var(--border-color)] flex flex-col">
        {/* Logo/Title */}
        <div className="p-4 border-b border-[var(--border-color)]">
          <h1 className="text-xl font-bold">Forex Platform</h1>
          <div className={`mt-2 inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
            isLive ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'
          }`}>
            {isLive && <AlertTriangle className="w-3 h-3 mr-1" />}
            {tradingMode.toUpperCase()} MODE
          </div>
        </div>
        
        {/* Navigation */}
        <nav className="flex-1 p-2">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg mb-1 transition-colors ${
                  isActive
                    ? 'bg-[var(--accent-blue)] text-white'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]'
                }`
              }
            >
              <Icon className="w-5 h-5" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        
        {/* Account Summary */}
        <div className="p-4 border-t border-[var(--border-color)]">
          <div className="text-xs text-[var(--text-muted)] uppercase mb-2">Account</div>
          <div className="text-lg font-bold">
            ${status?.equity?.toLocaleString() || '10,000.00'}
          </div>
          <div className={`text-sm ${
            (status?.today_pnl || 0) >= 0 ? 'text-bullish' : 'text-bearish'
          }`}>
            {(status?.today_pnl || 0) >= 0 ? '+' : ''}
            ${status?.today_pnl?.toFixed(2) || '0.00'} today
          </div>
        </div>
      </aside>
      
      {/* Main Content */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
