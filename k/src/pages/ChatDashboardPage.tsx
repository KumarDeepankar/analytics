/**
 * Chat Dashboard Page - Three-phase adaptive layout:
 *   Hero  → clean centered search (no messages)
 *   Chat  → standard chat layout (messages, no charts)
 *   Split → dashboard main + chat side panel (charts exist)
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Settings, Maximize2, ArrowLeft, X, MessageCircle, Menu, LayoutDashboard, Presentation } from 'lucide-react';
import { useAppSelector, useAppDispatch } from '../store';
import {
  createChatDashboard,
  addUserMessage,
  addAssistantMessage,
  updateMessageContent,
  addThinkingStep,
  completeMessage,
  setProcessing,
  loadDashboardsFromBackend,
  saveDashboardToBackend,
} from '../store/slices/chatSlice';
import {
  toggleSettingsPanel,
  fetchModels,
  fetchTools,
} from '../store/slices/settingsSlice';
import { restoreFilters } from '../store/slices/filterSlice';
import { setPresentation } from '../store/slices/presentationSlice';
import { store } from '../store';
import { agentService, StreamEvent } from '../services/agentService';
import { fromApiStreamChartConfigs } from '../services/api';
import ChatSidebar from '../components/chat/ChatSidebar';
import ChatMessageList from '../components/chat/ChatMessageList';
import ChatInput from '../components/chat/ChatInput';
import DashboardView from '../components/chat/DashboardView';
import SlideViewer from '../components/slides/SlideViewer';
import SettingsPanel from '../components/chat/SettingsPanel';
import type { ChartConfig } from '../types';
import type { ChatDashboard, ChatMessage } from '../types/chat';
import type { LLMModel } from '../services/agentService';
import './ChatDashboardPage.css';

const HERO_SUGGESTIONS = [
  'Events by country',
  'Revenue trends over time',
  'Top 10 themes',
  'Monthly event count',
];

const ChatDashboardPage: React.FC = () => {
  const dispatch = useAppDispatch();
  const { dashboards, activeDashboardId, isProcessing, isLoading, isLoaded } = useAppSelector((state) => state.chat);
  const globalFilters = useAppSelector((state) => state.filters.globalFilters);
  const { selectedProvider, selectedModel, enabledTools, availableModels, dashboardTheme: settingsTheme } = useAppSelector(
    (state) => state.settings
  );

  const [isDashboardOpen, setIsDashboardOpen] = useState(false);
  const [fullViewTarget, setFullViewTarget] = useState<'none' | 'dashboard' | 'chat' | 'slides'>('none');
  const [isChatPopupOpen, setIsChatPopupOpen] = useState(false);
  const [activePanel, setActivePanel] = useState<'dashboard' | 'slides'>('dashboard');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => {
    return localStorage.getItem('sidebarCollapsed') === 'true';
  });
  const [windowWidth, setWindowWidth] = useState(window.innerWidth);
  const [showMobileSidebar, setShowMobileSidebar] = useState(false);
  const [chatWidth, setChatWidth] = useState<number | null>(null);
  const isResizingRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentMessageIdRef = useRef<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>([]);

  const isMobile = windowWidth < 768;
  const isTablet = windowWidth >= 768 && windowWidth < 1024;

  const handleToggleSidebar = useCallback(() => {
    setIsSidebarCollapsed(prev => {
      const next = !prev;
      localStorage.setItem('sidebarCollapsed', String(next));
      return next;
    });
  }, []);

  // Load dashboards from backend on mount
  useEffect(() => {
    dispatch(loadDashboardsFromBackend());
  }, [dispatch]);

  // Note: no auto-create — hero phase handles the empty state with the "+" button

  // Fetch models and tools on mount
  useEffect(() => {
    dispatch(fetchModels());
    dispatch(fetchTools());
  }, [dispatch]);

  // Window resize listener for responsive breakpoints
  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Resize handle for chat panel
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizingRef.current) return;
      // sidebar collapsed = 48px in split mode
      const sidebarWidth = 48;
      const newWidth = window.innerWidth - e.clientX - sidebarWidth;
      const clamped = Math.max(300, Math.min(600, newWidth));
      setChatWidth(clamped);
    };
    const handleMouseUp = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isResizingRef.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  // Get selected model display name (guard against undefined from stale localStorage)
  const selectedModelInfo = (availableModels || []).find(
    (m: LLMModel) => m.id === selectedModel && m.provider === selectedProvider
  );

  const activeDashboard = dashboards.find((d: ChatDashboard) => d.id === activeDashboardId);
  const dashboardTheme = activeDashboard?.dashboardTheme || settingsTheme;

  const hasMessages = (activeDashboard?.messages.length ?? 0) > 0;
  const hasCharts = (activeDashboard?.dashboardCharts.length ?? 0) > 0;
  const phase: 'hero' | 'chat' | 'split' = !hasMessages ? 'hero' : hasCharts ? 'split' : 'chat';

  // Auto-open dashboard and collapse sidebar when charts appear (entering split phase)
  useEffect(() => {
    if (hasCharts && !isDashboardOpen) {
      setIsDashboardOpen(true);
      setIsSidebarCollapsed(true);
      localStorage.setItem('sidebarCollapsed', 'true');
    }
  }, [hasCharts]);

  // Auto-save new dashboards to backend on creation
  useEffect(() => {
    if (activeDashboard && !activeDashboard.isSaved && !activeDashboard.lastSavedAt) {
      dispatch(saveDashboardToBackend(activeDashboard));
    }
  }, [activeDashboardId]);

  // Auto-save after chat message streaming completes
  const prevProcessingRef = useRef(false);
  useEffect(() => {
    if (prevProcessingRef.current && !isProcessing && activeDashboard) {
      dispatch(saveDashboardToBackend(activeDashboard));
    }
    prevProcessingRef.current = isProcessing;
  }, [isProcessing]);

  // Restore filters when active dashboard changes
  useEffect(() => {
    if (activeDashboard?.filters && activeDashboard.filters.length > 0) {
      dispatch(restoreFilters(activeDashboard.filters));
    } else if (activeDashboard) {
      dispatch(restoreFilters([]));
    }
  }, [activeDashboardId, activeDashboard?.filters, dispatch]);

  // Keep messages ref in sync for use in callbacks without causing re-renders
  messagesRef.current = activeDashboard?.messages || [];

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (isProcessing) return;

      // Auto-create a dashboard if none exists
      let dashboardId = activeDashboardId;
      if (!dashboardId) {
        const newId = `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        dispatch(createChatDashboard({ title: 'My Dashboard', id: newId }));
        dashboardId = newId;
      }

      // Add user message
      dispatch(addUserMessage({ dashboardId, content }));

      // Create assistant message for streaming
      const messageId = `msg-${Date.now()}`;
      currentMessageIdRef.current = messageId;
      dispatch(addAssistantMessage({ dashboardId, messageId }));

      // Setup abort controller
      abortControllerRef.current = new AbortController();

      try {
        let fullResponse = '';
        let charts: ChartConfig[] = [];
        let sources: Array<{ title: string; url?: string; snippet?: string }> = [];

        // Build conversation history, appending current presentation as context
        const history = messagesRef.current
          .filter((m: ChatMessage) => !m.isStreaming)
          .map((m: ChatMessage) => ({
            role: m.role,
            content: m.content,
          }));
        const currentPresentation = store.getState().presentation.presentations[dashboardId];
        if (currentPresentation) {
          history.push({
            role: 'system',
            content: `Current presentation state:\n${JSON.stringify(currentPresentation)}`,
          });
        }

        // Stream from agent using selected model and enabled tools
        for await (const event of agentService.searchStream({
          query: content,
          conversationHistory: history,
          llmProvider: selectedProvider,
          llmModel: selectedModel,
          enabledTools: enabledTools,
          filters: globalFilters,
        })) {
          // Check abort
          if (abortControllerRef.current?.signal.aborted) {
            break;
          }

          // Handle event
          handleStreamEvent(event, {
            onThinking: (step) => {
              dispatch(
                addThinkingStep({
                  dashboardId,
                  messageId,
                  step,
                })
              );
            },
            onResponseChar: (char) => {
              fullResponse += char;
              dispatch(
                updateMessageContent({
                  dashboardId,
                  messageId,
                  content: fullResponse,
                })
              );
            },
            onSources: (s) => {
              sources = s;
            },
            onCharts: (c) => {
              charts = fromApiStreamChartConfigs(c).map((config, index) => ({
                ...config,
                id: `chart-${Date.now()}-${index}`,
              }));
            },
            onPresentation: (presentationData) => {
              const pres = {
                ...presentationData,
                id: dashboardId,
                createdAt: new Date().toISOString(),
                updatedAt: new Date().toISOString(),
              } as unknown as import('../types/slides').Presentation;
              dispatch(setPresentation({ dashboardId, presentation: pres }));
              setActivePanel('slides');
              setIsDashboardOpen(true);
            },
            onError: (message) => {
              dispatch(
                completeMessage({
                  dashboardId,
                  messageId,
                  content: fullResponse || 'An error occurred',
                  error: message,
                })
              );
            },
          });
        }

        // If we got chart configs but no charts yet, create sample charts for demo
        if (charts.length === 0 && fullResponse.toLowerCase().includes('chart')) {
          charts = extractChartsFromResponse(fullResponse, content);
        }

        // Complete the message
        dispatch(
          completeMessage({
            dashboardId,
            messageId,
            content: fullResponse || 'I\'ve processed your request.',
            charts: charts.length > 0 ? charts : undefined,
            sources: sources.length > 0 ? sources : undefined,
          })
        );
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          dispatch(
            completeMessage({
              dashboardId,
              messageId,
              content: '',
              error: err.message || 'Failed to process request',
            })
          );
        }
      } finally {
        abortControllerRef.current = null;
        currentMessageIdRef.current = null;
      }
    },
    [activeDashboardId, isProcessing, globalFilters, selectedProvider, selectedModel, enabledTools, dispatch]
  );

  const handleCancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    dispatch(setProcessing(false));
  }, [dispatch]);

  if (isLoading) {
    return (
      <div className="chat-dashboard-page loading">
        <div className="loading-spinner"></div>
        <p>Loading dashboards...</p>
      </div>
    );
  }

  const responsiveClass = isMobile ? 'mobile' : isTablet ? 'tablet' : '';

  // ── Full View: Dashboard ─────────────────────────────────────────
  if (fullViewTarget === 'dashboard' && activeDashboard) {
    return (
      <div className={`chat-dashboard-page full-view ${responsiveClass}`} data-bg-theme={dashboardTheme}>
        <div className="fullview-dashboard">
          <div className="fullview-header">
            <button
              className="exit-fullview-btn"
              onClick={() => setFullViewTarget('none')}
              title="Exit Full View"
            >
              <ArrowLeft size={16} /> Back
            </button>
            <h1>{activeDashboard.title}</h1>
            <div className="fullview-actions">
              <span className="chart-count">{activeDashboard.dashboardCharts.length} charts</span>
            </div>
          </div>
          <DashboardView
            dashboard={activeDashboard}
            isFullView={true}
            onOpenSlides={() => {
              setActivePanel('slides');
              setFullViewTarget('slides');
            }}
          />
        </div>

        {/* Floating Chat Popup in Full View */}
        <button
          className={`chat-popup-toggle ${isChatPopupOpen ? 'open' : ''}`}
          onClick={() => setIsChatPopupOpen(!isChatPopupOpen)}
        >
          {isChatPopupOpen ? <X size={24} /> : <MessageCircle size={24} />}
        </button>

        {isChatPopupOpen && (
          <div className="chat-popup">
            <div className="chat-popup-header">
              <h3>Chat Assistant</h3>
              <button
                className="settings-btn-small"
                onClick={() => dispatch(toggleSettingsPanel())}
                title="Settings"
              >
                <Settings size={16} />
              </button>
            </div>
            <ChatMessageList
              messages={activeDashboard.messages}
              dashboardId={activeDashboard.id}
            />
            <ChatInput
              onSend={handleSendMessage}
              isProcessing={isProcessing}
              onCancel={handleCancel}
            />
          </div>
        )}

        <SettingsPanel />
      </div>
    );
  }

  // ── Full View: Chat ────────────────────────────────────────────
  if (fullViewTarget === 'chat' && activeDashboard) {
    return (
      <div className={`chat-dashboard-page full-view fullview-chat-mode ${responsiveClass}`} data-bg-theme={dashboardTheme}>
        <div className="fullview-chat-container">
          <div className="fullview-chat-header">
            <button
              className="exit-fullview-btn"
              onClick={() => setFullViewTarget('none')}
              title="Exit Full View"
            >
              <ArrowLeft size={16} /> Back
            </button>
            <h1>{activeDashboard.title}</h1>
            <div className="fullview-chat-actions">
              <button
                className="settings-btn"
                onClick={() => dispatch(toggleSettingsPanel())}
                title="Agent Settings"
              >
                <Settings size={16} className="settings-icon" />
                <span className="settings-label">
                  {selectedModelInfo?.name || selectedModel}
                </span>
                <span className="tools-badge">{enabledTools.length} tools</span>
              </button>
              {hasCharts && (
                <button
                  className="dashboard-toggle-btn"
                  onClick={() => setFullViewTarget('dashboard')}
                  title="View Dashboard"
                >
                  <LayoutDashboard size={16} />
                  <span className="dashboard-badge">{activeDashboard.dashboardCharts.length}</span>
                </button>
              )}
            </div>
          </div>

          <ChatMessageList
            messages={activeDashboard.messages}
            dashboardId={activeDashboard.id}
          />

          <ChatInput
            onSend={handleSendMessage}
            isProcessing={isProcessing}
            onCancel={handleCancel}
          />
        </div>

        <SettingsPanel />
      </div>
    );
  }

  // ── Full View: Slides ──────────────────────────────────────────
  if (fullViewTarget === 'slides' && activeDashboard) {
    return (
      <div className={`chat-dashboard-page full-view ${responsiveClass}`} data-bg-theme={dashboardTheme}>
        <div className="fullview-slides">
          <SlideViewer
            dashboardId={activeDashboard.id}
            onBack={() => setFullViewTarget('none')}
            isFullView={true}
          />
        </div>

        {/* Floating Chat Popup in Full View */}
        <button
          className={`chat-popup-toggle ${isChatPopupOpen ? 'open' : ''}`}
          onClick={() => setIsChatPopupOpen(!isChatPopupOpen)}
        >
          {isChatPopupOpen ? <X size={24} /> : <MessageCircle size={24} />}
        </button>

        {isChatPopupOpen && (
          <div className="chat-popup">
            <div className="chat-popup-header">
              <h3>Chat Assistant</h3>
              <button
                className="settings-btn-small"
                onClick={() => dispatch(toggleSettingsPanel())}
                title="Settings"
              >
                <Settings size={16} />
              </button>
            </div>
            <ChatMessageList
              messages={activeDashboard.messages}
              dashboardId={activeDashboard.id}
            />
            <ChatInput
              onSend={handleSendMessage}
              isProcessing={isProcessing}
              onCancel={handleCancel}
            />
          </div>
        )}

        <SettingsPanel />
      </div>
    );
  }

  // ── Hero Phase ──────────────────────────────────────────────────
  if (phase === 'hero') {
    return (
      <div className={`chat-dashboard-page phase-hero ${responsiveClass}`}>
        {/* Hero navbar */}
        <div className="hero-navbar">
          <div className="hero-brand">Analytics</div>
          <div className="hero-nav-actions">
            <button
              className="hero-nav-btn"
              onClick={() => setShowMobileSidebar(true)}
              title="Dashboards"
            >
              <LayoutDashboard size={18} />
            </button>
            <button
              className="hero-nav-btn"
              onClick={() => dispatch(toggleSettingsPanel())}
              title="Settings"
            >
              <Settings size={18} />
            </button>
          </div>
        </div>

        {/* Hero center content */}
        <div className="hero-content">
          <h1 className="hero-tagline">Turn questions into insights</h1>
          <p className="hero-subtitle">
            Ask anything about your data and get instant visualizations
          </p>

          <div className="hero-search">
            <ChatInput
              onSend={handleSendMessage}
              isProcessing={isProcessing}
              onCancel={handleCancel}
            />
          </div>

          <div className="hero-chips">
            {HERO_SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                className="hero-chip"
                onClick={() => handleSendMessage(suggestion)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>

        {/* Sidebar overlay (reuse mobile sidebar pattern) */}
        {showMobileSidebar && (
          <div className="mobile-sidebar-overlay" onClick={() => setShowMobileSidebar(false)}>
            <div className="mobile-sidebar-content" onClick={(e) => e.stopPropagation()}>
              <ChatSidebar />
            </div>
          </div>
        )}

        <SettingsPanel />
      </div>
    );
  }

  // ── Chat Phase ──────────────────────────────────────────────────
  if (phase === 'chat' && activeDashboard) {
    return (
      <div className={`chat-dashboard-page phase-chat ${responsiveClass}`} data-bg-theme={dashboardTheme}>
        {/* Mobile sidebar toggle */}
        {isMobile && (
          <button
            className="mobile-sidebar-toggle"
            onClick={() => setShowMobileSidebar(!showMobileSidebar)}
          >
            <Menu size={20} />
          </button>
        )}

        {/* Sidebar */}
        {!isMobile && (
          <ChatSidebar
            isCollapsed={isSidebarCollapsed || isTablet}
            onToggleCollapse={!isTablet ? handleToggleSidebar : undefined}
          />
        )}
        {isMobile && showMobileSidebar && (
          <div className="mobile-sidebar-overlay" onClick={() => setShowMobileSidebar(false)}>
            <div className="mobile-sidebar-content" onClick={(e) => e.stopPropagation()}>
              <ChatSidebar />
            </div>
          </div>
        )}

        {/* Chat main area */}
        <div className="chat-main">
          <div className="chat-header">
            <h1>{activeDashboard.title}</h1>
            <div className="header-right">
              <div className="header-stats">
                <span>{activeDashboard.messages.length} messages</span>
                <span>·</span>
                <span>{activeDashboard.dashboardCharts.length} charts</span>
              </div>
              <button
                className="settings-btn"
                onClick={() => dispatch(toggleSettingsPanel())}
                title="Agent Settings"
              >
                <Settings size={16} className="settings-icon" />
                <span className="settings-label">
                  {selectedModelInfo?.name || selectedModel}
                </span>
                <span className="tools-badge">{enabledTools.length} tools</span>
              </button>
              <button
                className="dashboard-toggle-btn"
                onClick={() => setIsDashboardOpen(!isDashboardOpen)}
                title="Toggle Dashboard"
              >
                <LayoutDashboard size={16} />
              </button>
              <button
                className="fullview-btn"
                onClick={() => setFullViewTarget('chat')}
                title="Full View Chat"
              >
                <Maximize2 size={16} />
              </button>
            </div>
          </div>

          <ChatMessageList
            messages={activeDashboard.messages}
            dashboardId={activeDashboard.id}
          />

          <ChatInput
            onSend={handleSendMessage}
            isProcessing={isProcessing}
            onCancel={handleCancel}
          />
        </div>

        {/* Slide-over dashboard (no charts yet, manual "Add Chart") */}
        {isDashboardOpen && (
          <>
            <div className="dashboard-overlay-backdrop" onClick={() => setIsDashboardOpen(false)} />
            <div className="dashboard-slide-panel open">
              <DashboardView
                dashboard={activeDashboard}
                onClose={() => setIsDashboardOpen(false)}
                isFullView={false}
              />
            </div>
          </>
        )}

        <SettingsPanel />
      </div>
    );
  }

  // ── Split Phase ─────────────────────────────────────────────────
  if (!activeDashboard) return null;
  return (
    <div className={`chat-dashboard-page phase-split ${responsiveClass}`} data-bg-theme={dashboardTheme}>
      {/* Mobile sidebar toggle */}
      {isMobile && (
        <button
          className="mobile-sidebar-toggle"
          onClick={() => setShowMobileSidebar(!showMobileSidebar)}
        >
          <Menu size={20} />
        </button>
      )}

      {/* Sidebar — collapsed by default in split, expandable via toggle */}
      {!isMobile && (
        <ChatSidebar
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={handleToggleSidebar}
        />
      )}
      {isMobile && showMobileSidebar && (
        <div className="mobile-sidebar-overlay" onClick={() => setShowMobileSidebar(false)}>
          <div className="mobile-sidebar-content" onClick={(e) => e.stopPropagation()}>
            <ChatSidebar />
          </div>
        </div>
      )}

      {/* Main content area — Dashboard or Slides */}
      {!isMobile && isDashboardOpen && activePanel === 'dashboard' && (
        <div className="dashboard-main-panel">
          <DashboardView
            dashboard={activeDashboard}
            onMaximize={() => setFullViewTarget('dashboard')}
            onOpenSlides={() => setActivePanel('slides')}
            isFullView={false}
          />
        </div>
      )}
      {!isMobile && isDashboardOpen && activePanel === 'slides' && (
        <div className="dashboard-main-panel slide-main-panel">
          <SlideViewer
            dashboardId={activeDashboard.id}
            onBack={() => setActivePanel('dashboard')}
            onMaximize={() => setFullViewTarget('slides')}
          />
        </div>
      )}

      {/* Resize handle */}
      {!isMobile && isDashboardOpen && (
        <div
          className={`resize-handle ${isResizingRef.current ? 'active' : ''}`}
          onMouseDown={handleResizeMouseDown}
        />
      )}

      {/* Chat — right side panel */}
      <div
        className={`chat-side-panel ${isResizingRef.current ? 'resizing' : ''}`}
        style={{ width: chatWidth ?? undefined }}
      >
        <div className="chat-side-header">
          <h2>{activeDashboard.title}</h2>
          <div className="chat-side-actions">
            <button
              className="settings-btn-compact"
              onClick={() => dispatch(toggleSettingsPanel())}
              title="Settings"
            >
              <Settings size={14} />
            </button>
            <button
              className="dashboard-toggle-btn-compact"
              onClick={() => setFullViewTarget('dashboard')}
              title="Maximize Dashboard"
            >
              <LayoutDashboard size={14} />
            </button>
            <button
              className="fullview-btn-compact"
              onClick={() => setFullViewTarget('chat')}
              title="Full View Chat"
            >
              <Maximize2 size={14} />
            </button>
          </div>
        </div>

        <ChatMessageList
          messages={activeDashboard.messages}
          dashboardId={activeDashboard.id}
        />

        <ChatInput
          onSend={handleSendMessage}
          isProcessing={isProcessing}
          onCancel={handleCancel}
        />
      </div>

      {/* Mobile: slide-over dashboard fallback */}
      {isMobile && isDashboardOpen && (
        <>
          <div className="dashboard-overlay-backdrop" onClick={() => setIsDashboardOpen(false)} />
          <div className="dashboard-slide-panel open">
            <DashboardView
              dashboard={activeDashboard}
              onClose={() => setIsDashboardOpen(false)}
              isFullView={false}
            />
          </div>
        </>
      )}

      <SettingsPanel />
    </div>
  );
};

// Handle stream events
function handleStreamEvent(
  event: StreamEvent,
  handlers: {
    onThinking: (step: { node: string; message: string }) => void;
    onResponseChar: (char: string) => void;
    onSources: (sources: Array<{ title: string; url?: string }>) => void;
    onCharts: (charts: Array<Record<string, unknown>>) => void;
    onPresentation: (data: Record<string, unknown>) => void;
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
      handlers.onCharts(data as Array<Record<string, unknown>>);
      break;
    case 'presentation':
      handlers.onPresentation(data as Record<string, unknown>);
      break;
    case 'error': {
      const errorData = data as { message: string };
      handlers.onError(errorData.message);
      break;
    }
  }
}

// Extract chart suggestions from response text (for demo when agent doesn't return structured charts)
function extractChartsFromResponse(response: string, query: string): ChartConfig[] {
  const charts: ChartConfig[] = [];
  const queryLower = query.toLowerCase();

  // Detect chart type from query
  let chartType: ChartConfig['type'] = 'bar';
  if (queryLower.includes('line') || queryLower.includes('trend') || queryLower.includes('over time')) {
    chartType = 'line';
  } else if (queryLower.includes('pie') || queryLower.includes('distribution') || queryLower.includes('percentage')) {
    chartType = 'pie';
  } else if (queryLower.includes('area')) {
    chartType = 'area';
  }

  // Detect field from query
  let xField = 'country';  // Default to country (valid MCP field)
  const fieldMatches = queryLower.match(/by\s+(\w+)/);
  if (fieldMatches) {
    xField = fieldMatches[1];
  }

  // Common field mappings - maps user query terms to MCP field names
  const fieldMappings: Record<string, string> = {
    'country': 'country',
    'theme': 'event_theme',
    'title': 'event_title',
    'event': 'event_theme',
    'type': 'event_theme',
    'year': 'year',
    'date': 'event_date',
    'day': 'event_date',
    'month': 'event_date',
  };

  if (fieldMappings[xField]) {
    xField = fieldMappings[xField];
  }

  // Create a chart config
  charts.push({
    id: `chart-${Date.now()}`,
    type: chartType,
    title: `${chartType.charAt(0).toUpperCase() + chartType.slice(1)} Chart: ${xField.replace('.', ' ').replace('_', ' ')}`,
    dataSource: 'analyze_all_events',  // MCP tool name
    xField,
    aggregation: 'count',
    filters: [],
  });

  return charts;
}

export default ChatDashboardPage;
