import { useEffect, useState } from 'react';
import { ChatProvider } from './contexts/ChatContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ChatInterface } from './components/ChatInterface';
import { apiClient } from './services/api';
import { getBackendUrl } from './config';
import type { Tool } from './types';
import './styles/animations.css';

function App() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(false);

  // Load tools on mount
  useEffect(() => {
    const loadTools = async () => {
      try {
        const fetchedTools = await apiClient.getTools();
        setTools(fetchedTools);
      } catch (error: any) {

        // Check if it's an authentication error
        if (error.message?.includes('401') || error.message?.includes('403') || error.message?.includes('Authentication required')) {
          setAuthError(true);
          // Redirect to backend login page
          // Backend will show redirect_to_app.html which redirects back to React app
          window.location.href = getBackendUrl('/auth/login');
        }
      } finally {
        setIsLoading(false);
      }
    };

    loadTools();
  }, []);

  // Initialize enabled tools
  useEffect(() => {
    if (tools.length > 0) {
      const enabledTools = tools.filter((t) => t.enabled).map((t) => t.name);
      // This will be used by ChatContext when initialized
      localStorage.setItem('enabledTools', JSON.stringify(enabledTools));
    }
  }, [tools]);

  if (authError) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: '#0A1929',
          color: '#E7EBF0',
          fontSize: '18px',
          gap: '16px',
          animation: 'fadeIn 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <div style={{ fontSize: '48px', animation: 'scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1)' }}>🔐</div>
        <div>Authentication Required</div>
        <div style={{ fontSize: '14px', color: '#B2BAC2', animation: 'pulse 2s ease-in-out infinite' }}>
          Redirecting to login page...
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          backgroundColor: '#0A1929',
          color: '#E7EBF0',
          fontSize: '18px',
          gap: '16px',
          animation: 'fadeIn 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <div style={{ fontSize: '48px', animation: 'scaleIn 0.6s cubic-bezier(0.16, 1, 0.3, 1)' }}>💬</div>
        <div style={{ animation: 'pulse 2s ease-in-out infinite' }}>
          Loading Agentic Search...
        </div>
      </div>
    );
  }

  return (
    <ChatProvider>
      <ThemeProvider>
        <ChatInterface />
      </ThemeProvider>
    </ChatProvider>
  );
}

export default App;
