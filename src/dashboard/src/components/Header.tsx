/**
 * Header.tsx -- Application Header and Navigation Bar
 *
 * Renders the top navigation bar with the Newshare Network brand, navigation
 * links (Dashboard, Publishers, Transactions, Privacy, Account), and the
 * current user's networkUserId and homeBaseId. Includes a responsive mobile
 * navigation that scrolls horizontally. The logout button clears the local
 * session (localStorage) and redirects to the login prompt.
 */

import { NavLink } from 'react-router-dom';
import { logout } from '../api/auth';
import type { SessionData } from '../api/auth';

interface HeaderProps {
  session: SessionData;
  onLogout: () => void;
}

const navItems = [
  { to: '/demo', label: 'How it works' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/publishers', label: 'Publishers' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/privacy', label: 'Privacy' },
  { to: '/account', label: 'Account' },
];

export default function Header({ session, onLogout }: HeaderProps) {
  const handleLogout = () => {
    onLogout();
    logout();
  };

  return (
    <header className="bg-navy-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo and brand */}
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-teal-500 rounded-md flex items-center justify-center font-bold text-sm">
                N
              </div>
              <span className="font-semibold text-lg tracking-tight">
                Newshare Network
              </span>
            </div>

            {/* Navigation links */}
            <nav className="hidden md:flex items-center gap-1">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `nav-link ${isActive ? 'nav-link-active' : 'nav-link-inactive'}`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>

          {/* User info and logout */}
          <div className="flex items-center gap-4">
            <div className="hidden sm:block text-right">
              <p className="text-sm font-medium text-navy-100">
                {session.networkUserId}
              </p>
              <p className="text-xs text-navy-400">{session.homeBaseId}</p>
            </div>
            <button
              onClick={handleLogout}
              className="text-sm text-navy-300 hover:text-white px-3 py-1.5
                         border border-navy-600 rounded-md hover:border-navy-400
                         transition-colors duration-150"
            >
              Log out
            </button>
          </div>
        </div>
      </div>

      {/* Mobile navigation */}
      <nav className="md:hidden border-t border-navy-700 px-4 pb-3 pt-2 flex gap-1 overflow-x-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `nav-link whitespace-nowrap ${isActive ? 'nav-link-active' : 'nav-link-inactive'}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
}
