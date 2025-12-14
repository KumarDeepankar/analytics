import { useEffect, useState } from 'react';
import { mcpClient } from '../services/mcpClient';

interface OAuthCallbackProps {
  onSuccess: () => void;
  onError: (error: string) => void;
}

export function OAuthCallback({ onSuccess, onError }: OAuthCallbackProps) {
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');

  useEffect(() => {
    const handleCallback = () => {
      // Extract token from URL hash or query params
      // tools_gateway redirects with: /callback#token=<jwt>
      const hash = window.location.hash;
      const params = new URLSearchParams(window.location.search);

      let token: string | null = null;

      // Check hash fragment first (#token=...)
      if (hash) {
        const hashParams = new URLSearchParams(hash.substring(1));
        token = hashParams.get('token') || hashParams.get('access_token');
      }

      // Fallback to query params (?token=...)
      if (!token) {
        token = params.get('token') || params.get('access_token');
      }

      if (token) {

        // Store token in localStorage
        mcpClient.setJwtToken(token);
        setStatus('success');

        // Clean up URL and redirect
        window.history.replaceState({}, document.title, '/');

        // Call success callback after short delay
        setTimeout(() => {
          onSuccess();
        }, 500);
      } else {
        // Check for error
        const error = params.get('error') || hashParams?.get('error') || 'No token received';

        setStatus('error');
        onError(error);
      }
    };

    handleCallback();
  }, [onSuccess, onError]);

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
      }}
    >
      <div
        style={{
          textAlign: 'center',
          padding: '40px',
          background: 'rgba(255, 255, 255, 0.05)',
          backdropFilter: 'blur(10px)',
          borderRadius: '16px',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        {status === 'processing' && (
          <>
            <div
              style={{
                fontSize: '48px',
                marginBottom: '24px',
                animation: 'spin 2s linear infinite',
              }}
            >
              🔄
            </div>
            <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 600 }}>
              Completing Sign In
            </h2>
            <p style={{ margin: '16px 0 0', color: '#B2BAC2' }}>
              Please wait...
            </p>
          </>
        )}

        {status === 'success' && (
          <>
            <div style={{ fontSize: '48px', marginBottom: '24px' }}>✅</div>
            <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 600, color: '#4CAF50' }}>
              Success!
            </h2>
            <p style={{ margin: '16px 0 0', color: '#B2BAC2' }}>
              Redirecting to application...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div style={{ fontSize: '48px', marginBottom: '24px' }}>❌</div>
            <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 600, color: '#EF5350' }}>
              Authentication Failed
            </h2>
            <p style={{ margin: '16px 0 0', color: '#B2BAC2' }}>
              Please try again
            </p>
          </>
        )}
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
