import React, { useState, useCallback, useRef } from 'react';
import { agentService, StreamEvent } from '../../services/agentService';
import { useAppSelector } from '../../store';
import './AISearchBar.css';

interface AISearchBarProps {
  onQueryResult?: (result: {
    response: string;
    sources?: Array<{ title: string; url?: string }>;
    chartConfigs?: Array<unknown>;
  }) => void;
  onThinkingUpdate?: (step: { node: string; message: string }) => void;
  placeholder?: string;
}

const AISearchBar: React.FC<AISearchBarProps> = ({
  onQueryResult,
  onThinkingUpdate,
  placeholder = 'Ask a question about your data...',
}) => {
  const [query, setQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamingResponse, setStreamingResponse] = useState('');
  const [thinkingSteps, setThinkingSteps] = useState<Array<{ node: string; message: string }>>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  const globalFilters = useAppSelector((state) => state.filters.globalFilters);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!query.trim() || isLoading) return;

      setIsLoading(true);
      setError(null);
      setStreamingResponse('');
      setThinkingSteps([]);

      // Create abort controller for cancellation
      abortControllerRef.current = new AbortController();

      try {
        let fullResponse = '';
        let sources: Array<{ title: string; url?: string }> = [];
        let chartConfigs: Array<unknown> = [];

        // Use streaming API with global filters
        for await (const event of agentService.searchStream({
          query,
          conversationHistory: [],
          llmProvider: 'ollama',
          enabledTools: [],
          filters: globalFilters,
        })) {
          // Check if aborted
          if (abortControllerRef.current?.signal.aborted) {
            break;
          }

          handleStreamEvent(event, {
            onThinking: (step) => {
              setThinkingSteps((prev) => [...prev, step]);
              onThinkingUpdate?.(step);
            },
            onResponseChar: (char) => {
              fullResponse += char;
              setStreamingResponse(fullResponse);
            },
            onSources: (s) => {
              sources = s;
            },
            onCharts: (c) => {
              chartConfigs = c;
            },
            onError: (msg) => {
              setError(msg);
            },
          });
        }

        // Call result callback with final data
        if (fullResponse) {
          onQueryResult?.({
            response: fullResponse,
            sources,
            chartConfigs,
          });
        }

        setQuery('');
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          setError(err.message || 'Failed to process query');
        }
      } finally {
        setIsLoading(false);
        abortControllerRef.current = null;
      }
    },
    [query, isLoading, onQueryResult, onThinkingUpdate]
  );

  const handleCancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsLoading(false);
    }
  }, []);

  return (
    <div className="ai-search-bar">
      <form onSubmit={handleSubmit}>
        <div className="search-input-container">
          <span className="search-icon">🔍</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            disabled={isLoading}
            className="search-input"
          />
          {isLoading ? (
            <button type="button" onClick={handleCancel} className="search-btn cancel-btn">
              Cancel
            </button>
          ) : (
            <button type="submit" disabled={!query.trim()} className="search-btn">
              Ask AI
            </button>
          )}
        </div>
      </form>

      {/* Thinking Steps */}
      {thinkingSteps.length > 0 && isLoading && (
        <div className="thinking-steps">
          {thinkingSteps.slice(-3).map((step, i) => (
            <div key={i} className="thinking-step">
              <span className="thinking-icon">💭</span>
              <span className="thinking-node">{step.node}:</span>
              <span className="thinking-message">{step.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* Streaming Response Preview */}
      {streamingResponse && isLoading && (
        <div className="streaming-preview">
          <div className="streaming-content">
            {streamingResponse.slice(0, 200)}
            {streamingResponse.length > 200 && '...'}
          </div>
        </div>
      )}

      {error && <div className="search-error">{error}</div>}
    </div>
  );
};

// Helper to handle stream events
function handleStreamEvent(
  event: StreamEvent,
  handlers: {
    onThinking: (step: { node: string; message: string }) => void;
    onResponseChar: (char: string) => void;
    onSources: (sources: Array<{ title: string; url?: string }>) => void;
    onCharts: (charts: Array<unknown>) => void;
    onError: (message: string) => void;
  }
) {
  const { type, data } = event;

  switch (type) {
    case 'thinking': {
      const thinkingData = data as { type: string; node?: string; message?: string };
      if (thinkingData.type === 'node_start' && thinkingData.node) {
        handlers.onThinking({ node: thinkingData.node, message: 'Starting...' });
      } else if (thinkingData.type === 'step' && thinkingData.message) {
        handlers.onThinking({
          node: thinkingData.node || 'agent',
          message: thinkingData.message,
        });
      }
      break;
    }
    case 'response': {
      const responseData = data as { type: string; char?: string };
      if (responseData.type === 'char' && responseData.char) {
        handlers.onResponseChar(responseData.char);
      }
      break;
    }
    case 'sources':
      handlers.onSources(data as Array<{ title: string; url?: string }>);
      break;
    case 'charts':
      handlers.onCharts(data as Array<unknown>);
      break;
    case 'error': {
      const errorData = data as { message: string };
      handlers.onError(errorData.message);
      break;
    }
  }
}

export default AISearchBar;
