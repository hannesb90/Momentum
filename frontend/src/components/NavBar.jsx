import { NavLink } from 'react-router-dom'
import { TickerSearch } from './TickerSearch'

const ICONS = {
  home: (
    <path d="M3 10.5 12 3l9 7.5M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
  ),
  signals: <path d="M3 17l5-6 4 4 5-7 4 5M3 21h18" />,
  portfolio: (
    <>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2M3 12h18" />
    </>
  ),
  sectors: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3v9l6.5 4" />
    </>
  ),
  analysis: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  watchlist: (
    <>
      <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
}

const links = [
  { to: '/', label: 'Hem', icon: 'home' },
  { to: '/signaler', label: 'Signaler', icon: 'signals' },
  { to: '/portfolj', label: 'Portfölj', icon: 'portfolio' },
  { to: '/bevakning', label: 'Bevakning', icon: 'watchlist' },
  { to: '/sektorer', label: 'Sektorer', icon: 'sectors' },
  { to: '/analys', label: 'Analys', icon: 'analysis' },
]

function Icon({ name }) {
  return (
    <svg
      className="navbar__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  )
}

export function NavBar() {
  return (
    <nav className="navbar">
      <div className="navbar__brand">
        <span className="navbar__logo">M</span>
        Momentum
      </div>
      <div className="navbar__links">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.to === '/'}
            className={({ isActive }) => `navbar__link${isActive ? ' navbar__link--active' : ''}`}
          >
            <Icon name={link.icon} />
            <span className="navbar__label">{link.label}</span>
          </NavLink>
        ))}
      </div>
      <TickerSearch />
    </nav>
  )
}
