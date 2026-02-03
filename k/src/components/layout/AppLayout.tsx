import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import './AppLayout.css';

const AppLayout: React.FC = () => {
  const location = useLocation();

  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="app-layout">
      <header className="app-header">
        <div className="header-brand">
          <h1>Agentic Search</h1>
          <span className="header-subtitle">AI-First Business Intelligence</span>
        </div>
        <nav className="header-nav">
          <Link to="/" className={`nav-link ${isActive('/') ? 'active' : ''}`}>
            Dashboards
          </Link>
          <Link to="/explore" className={`nav-link ${isActive('/explore') ? 'active' : ''}`}>
            Explore
          </Link>
          <Link to="/settings" className={`nav-link ${isActive('/settings') ? 'active' : ''}`}>
            Settings
          </Link>
        </nav>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
};

export default AppLayout;
