import { useState, useEffect } from 'react';
import { apiClient } from '../services/api';
import type { AuthProvider } from '../types';

interface LoginPageProps {
  onLoginSuccess: () => void;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(true);

  // Load auth providers on mount
  useEffect(() => {
    const loadProviders = async () => {
      try {
        const fetchedProviders = await apiClient.getAuthProviders();
        setProviders(fetchedProviders.filter(p => p.enabled));

      } catch (err) {

        // Continue anyway - local auth should still work
      } finally {
        setLoadingProviders(false);
      }
    };

    loadProviders();
  }, []);

  const handleLocalLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const result = await apiClient.loginLocal(email, password);

      onLoginSuccess();
    } catch (err: any) {

      // Show user-friendly error message
      let errorMessage = 'Login failed';

      if (err.message.includes('Invalid credentials')) {
        errorMessage = 'Invalid username/email or password';
      } else if (err.message.includes('401')) {
        errorMessage = 'Invalid username/email or password';
      } else if (err.message.includes('Network') || err.message.includes('fetch')) {
        errorMessage = 'Cannot connect to server. Please check if tools_gateway is running.';
      } else {
        errorMessage = err.message || 'Login failed';
      }

      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOAuthLogin = (providerId: string) => {
    // Redirect to OAuth provider
    apiClient.loginOAuth(providerId);
  };

  const getProviderIcon = (providerId: string): string => {
    const icons: Record<string, string> = {
      google: 'fab fa-google',
      microsoft: 'fab fa-microsoft',
      github: 'fab fa-github',
      azure: 'fab fa-microsoft',
      okta: 'fas fa-key',
    };
    return icons[providerId.toLowerCase()] || 'fas fa-sign-in-alt';
  };

  const getProviderColor = (providerId: string): string => {
    const colors: Record<string, string> = {
      google: 'linear-gradient(135deg, #4285F4 0%, #34A853 100%)',
      microsoft: 'linear-gradient(135deg, #00A4EF 0%, #0078D4 100%)',
      github: 'linear-gradient(135deg, #333 0%, #24292e 100%)',
      azure: 'linear-gradient(135deg, #0089D6 0%, #0078D4 100%)',
      okta: 'linear-gradient(135deg, #007DC1 0%, #0073B1 100%)',
    };
    return colors[providerId.toLowerCase()] || 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #0A1929 0%, #1A2027 100%)',
        color: '#E7EBF0',
        padding: '20px',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '440px',
          background: 'rgba(255, 255, 255, 0.05)',
          backdropFilter: 'blur(10px)',
          borderRadius: '16px',
          padding: '40px',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔍</div>
          <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 600 }}>
            Agentic Search
          </h1>
          <p style={{ margin: '8px 0 0', color: '#B2BAC2', fontSize: '14px' }}>
            Sign in to continue
          </p>
        </div>

        {/* OAuth Providers */}
        {!loadingProviders && providers.length > 0 && (
          <div style={{ marginBottom: '24px' }}>
            {providers.map((provider) => (
              <button
                key={provider.provider_id}
                onClick={() => handleOAuthLogin(provider.provider_id)}
                style={{
                  width: '100%',
                  padding: '14px',
                  marginBottom: '12px',
                  fontSize: '15px',
                  fontWeight: 600,
                  color: '#fff',
                  background: getProviderColor(provider.provider_id),
                  border: 'none',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '10px',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 6px 16px rgba(0, 0, 0, 0.25)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
                }}
              >
                <i className={getProviderIcon(provider.provider_id)} style={{ fontSize: '18px' }}></i>
                Continue with {provider.provider_name}
              </button>
            ))}

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                margin: '24px 0',
                color: '#B2BAC2',
                fontSize: '13px',
              }}
            >
              <div style={{ flex: 1, height: '1px', background: 'rgba(255, 255, 255, 0.1)' }}></div>
              <span style={{ padding: '0 16px' }}>OR</span>
              <div style={{ flex: 1, height: '1px', background: 'rgba(255, 255, 255, 0.1)' }}></div>
            </div>
          </div>
        )}

        {/* Local Login Form */}
        <form onSubmit={handleLocalLogin}>
          <div style={{ marginBottom: '20px' }}>
            <label
              htmlFor="email"
              style={{
                display: 'block',
                marginBottom: '8px',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              Username or Email
            </label>
            <input
              id="email"
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
              placeholder="Enter your username or email"
              style={{
                width: '100%',
                padding: '12px',
                fontSize: '14px',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.05)',
                color: '#E7EBF0',
                outline: 'none',
                transition: 'border-color 0.2s',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#2196F3';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'rgba(255, 255, 255, 0.2)';
              }}
            />
          </div>

          <div style={{ marginBottom: '24px' }}>
            <label
              htmlFor="password"
              style={{
                display: 'block',
                marginBottom: '8px',
                fontSize: '14px',
                fontWeight: 500,
              }}
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="Enter your password"
              style={{
                width: '100%',
                padding: '12px',
                fontSize: '14px',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.05)',
                color: '#E7EBF0',
                outline: 'none',
                transition: 'border-color 0.2s',
              }}
              onFocus={(e) => {
                e.target.style.borderColor = '#2196F3';
              }}
              onBlur={(e) => {
                e.target.style.borderColor = 'rgba(255, 255, 255, 0.2)';
              }}
            />
          </div>

          {error && (
            <div
              style={{
                padding: '12px',
                marginBottom: '20px',
                background: 'rgba(211, 47, 47, 0.1)',
                border: '1px solid rgba(211, 47, 47, 0.3)',
                borderRadius: '8px',
                color: '#EF5350',
                fontSize: '14px',
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            style={{
              width: '100%',
              padding: '12px',
              fontSize: '16px',
              fontWeight: 600,
              color: '#fff',
              background: isLoading
                ? 'rgba(33, 150, 243, 0.5)'
                : 'linear-gradient(135deg, #2196F3 0%, #1976D2 100%)',
              border: 'none',
              borderRadius: '8px',
              cursor: isLoading ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s',
              boxShadow: isLoading
                ? 'none'
                : '0 4px 12px rgba(33, 150, 243, 0.3)',
            }}
            onMouseEnter={(e) => {
              if (!isLoading) {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow =
                  '0 6px 16px rgba(33, 150, 243, 0.4)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow =
                '0 4px 12px rgba(33, 150, 243, 0.3)';
            }}
          >
            {isLoading ? 'Signing in...' : 'Sign In with Email'}
          </button>
        </form>

        {providers.length === 0 && !loadingProviders && (
          <div
            style={{
              marginTop: '24px',
              padding: '16px',
              background: 'rgba(33, 150, 243, 0.1)',
              border: '1px solid rgba(33, 150, 243, 0.2)',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#B2BAC2',
            }}
          >
            <strong style={{ color: '#64B5F6' }}>Local Authentication Only</strong>
            <br />
            No OAuth providers configured. Use email/password to sign in.
          </div>
        )}
      </div>
    </div>
  );
}
