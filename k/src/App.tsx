import { Provider } from 'react-redux';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { store } from './store';
import AppLayout from './components/layout/AppLayout';
import DashboardPage from './pages/DashboardPage';
import ExplorePage from './pages/ExplorePage';
import SettingsPage from './pages/SettingsPage';
import ChatDashboardPage from './pages/ChatDashboardPage';
import './App.css';

function App() {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <Routes>
          {/* Chat-based Dashboard - Primary Experience */}
          <Route path="/" element={<ChatDashboardPage />} />

          {/* Classic Dashboard Layout */}
          <Route path="/classic" element={<AppLayout />}>
            <Route index element={<DashboardPage />} />
            <Route path="explore" element={<ExplorePage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </Provider>
  );
}

export default App;
