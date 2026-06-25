import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: 'Signaler' },
  { to: '/backtest', label: 'Backtest' },
  { to: '/robusthet', label: 'Robusthet' },
  { to: '/regimer', label: 'Regimer' },
]

export function NavBar() {
  return (
    <nav className="navbar">
      <div className="navbar__brand">Momentum ML</div>
      <div className="navbar__links">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => `navbar__link${isActive ? ' navbar__link--active' : ''}`}
          >
            {link.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
