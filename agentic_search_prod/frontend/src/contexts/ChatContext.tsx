import { createContext, useContext, useReducer, type ReactNode } from 'react';
import type { ChatState, ChatAction, Message, ProcessingStep, Source, ChartConfig, SearchMode, Tool } from '../types';

// Initial state
const initialState: ChatState = {
  messages: [],
  isLoading: false,
  currentStreamingMessageId: null,
  sessionId: `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
  enabledTools: [],
  availableTools: [],
  toolsLoading: true,   // Start as true - tools need to be fetched
  toolsError: false,
  selectedProvider: '',
  selectedModel: '',
  theme: 'minimal',
  user: null,
  searchMode: 'quick',
  isSharedConversation: false,
};

// Reducer function
function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'ADD_MESSAGE':
      return {
        ...state,
        messages: [...state.messages, action.payload],
      };

    case 'UPDATE_MESSAGE': {
      const { id, updates } = action.payload;
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === id ? { ...msg, ...updates } : msg
        ),
      };
    }

    case 'ADD_PROCESSING_STEP': {
      const { messageId, step } = action.payload;
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === messageId
            ? {
                ...msg,
                processingSteps: [...(msg.processingSteps || []), step],
              }
            : msg
        ),
      };
    }

    case 'ADD_SOURCES': {
      const { messageId, sources } = action.payload;
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === messageId
            ? {
                ...msg,
                sources: (() => {
                  const existingSources = msg.sources || [];
                  // Normalize URLs to handle trailing slashes, case differences, etc.
                  const normalizeUrl = (url: string | undefined) => {
                    if (!url) return '';
                    try {
                      const parsed = new URL(url);
                      // Remove trailing slash and convert to lowercase for comparison
                      return parsed.href.toLowerCase().replace(/\/$/, '');
                    } catch {
                      return url.toLowerCase().replace(/\/$/, '');
                    }
                  };

                  const existingUrlsMap = new Map(
                    existingSources.filter(s => s.url).map(s => [normalizeUrl(s.url), s])
                  );

                  // Only add sources that don't already exist (deduplicate by normalized URL)
                  const newSources = sources.filter(s => {
                    if (!s.url) return false;
                    const normalized = normalizeUrl(s.url);
                    const isDuplicate = existingUrlsMap.has(normalized);
                    if (isDuplicate) {

                    }
                    return !isDuplicate;
                  });

                  const finalSources = [...existingSources, ...newSources];
                  return finalSources;
                })(),
              }
            : msg
        ),
      };
    }

    case 'ADD_CHARTS': {
      const { messageId, charts } = action.payload;
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === messageId
            ? {
                ...msg,
                charts: [...(msg.charts || []), ...charts],
              }
            : msg
        ),
      };
    }

    case 'CLEAR_SOURCES_AND_CHARTS': {
      // Clear sources and charts for retry with reduced data
      const { messageId } = action.payload;
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === messageId
            ? {
                ...msg,
                sources: [],
                charts: [],
              }
            : msg
        ),
      };
    }

    case 'SET_LOADING':
      return {
        ...state,
        isLoading: action.payload,
      };

    case 'SET_STREAMING_MESSAGE_ID':
      return {
        ...state,
        currentStreamingMessageId: action.payload,
      };

    case 'UPDATE_STREAMING_CONTENT': {
      const { messageId, content } = action.payload;
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === messageId ? { ...msg, content } : msg
        ),
      };
    }

    case 'SET_ENABLED_TOOLS':
      return {
        ...state,
        enabledTools: action.payload,
      };

    case 'SET_AVAILABLE_TOOLS':
      return {
        ...state,
        availableTools: action.payload,
        toolsError: false,  // Clear error on successful load
      };

    case 'SET_TOOLS_LOADING':
      return {
        ...state,
        toolsLoading: action.payload,
      };

    case 'SET_TOOLS_ERROR':
      return {
        ...state,
        toolsError: action.payload,
      };

    case 'SET_LLM_PROVIDER':
      return {
        ...state,
        selectedProvider: action.payload,
      };

    case 'SET_LLM_MODEL':
      return {
        ...state,
        selectedModel: action.payload,
      };

    case 'SET_THEME':
      return {
        ...state,
        theme: action.payload,
      };

    case 'SET_USER':
      return {
        ...state,
        user: action.payload,
      };

    case 'SET_SEARCH_MODE':
      return {
        ...state,
        searchMode: action.payload,
      };

    case 'RESET_CHAT':
      return {
        ...initialState,
        sessionId: `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
        enabledTools: state.enabledTools,
        availableTools: state.availableTools,
        toolsLoading: state.toolsLoading,
        toolsError: state.toolsError,
        selectedProvider: state.selectedProvider,
        selectedModel: state.selectedModel,
        theme: state.theme,
        user: state.user,
        searchMode: state.searchMode,
        isSharedConversation: false,
      };

    case 'LOAD_CONVERSATION':
      return {
        ...state,
        sessionId: action.payload.sessionId,
        // Reset isStreaming for all loaded messages (historical messages are never streaming)
        messages: action.payload.messages.map((msg: Message) => ({
          ...msg,
          isStreaming: false,
        })),
        isLoading: false,
        currentStreamingMessageId: null,
        isSharedConversation: action.payload.isShared || false,
      };

    default:
      return state;
  }
}

// Context type
interface ChatContextType {
  state: ChatState;
  dispatch: React.Dispatch<ChatAction>;
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => string;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  addProcessingStep: (messageId: string, content: string) => void;
  addSources: (messageId: string, sources: Source[]) => void;
  addCharts: (messageId: string, charts: ChartConfig[]) => void;
  clearSourcesAndCharts: (messageId: string) => void;  // For retry with reduced data
  updateStreamingContent: (messageId: string, content: string) => void;
  setLoading: (loading: boolean) => void;
  setStreamingMessageId: (id: string | null) => void;
  setSearchMode: (mode: SearchMode) => void;
  setAvailableTools: (tools: Tool[]) => void;
  setToolsLoading: (loading: boolean) => void;
  setToolsError: (error: boolean) => void;
  resetChat: () => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

// Provider component
export function ChatProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(chatReducer, initialState);

  // Helper functions
  const addMessage = (message: Omit<Message, 'id' | 'timestamp'>): string => {
    const id = `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    const fullMessage: Message = {
      ...message,
      id,
      timestamp: Date.now(),
    };
    dispatch({ type: 'ADD_MESSAGE', payload: fullMessage });
    return id;
  };

  const updateMessage = (id: string, updates: Partial<Message>) => {
    dispatch({ type: 'UPDATE_MESSAGE', payload: { id, updates } });
  };

  const addProcessingStep = (messageId: string, content: string) => {
    const step: ProcessingStep = {
      id: `step_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      content,
      timestamp: Date.now(),
    };
    dispatch({ type: 'ADD_PROCESSING_STEP', payload: { messageId, step } });
  };

  const addSources = (messageId: string, sources: Source[]) => {
    dispatch({ type: 'ADD_SOURCES', payload: { messageId, sources } });
  };

  const addCharts = (messageId: string, charts: ChartConfig[]) => {
    dispatch({ type: 'ADD_CHARTS', payload: { messageId, charts } });
  };

  const clearSourcesAndCharts = (messageId: string) => {
    dispatch({ type: 'CLEAR_SOURCES_AND_CHARTS', payload: { messageId } });
  };

  const updateStreamingContent = (messageId: string, content: string) => {
    dispatch({ type: 'UPDATE_STREAMING_CONTENT', payload: { messageId, content } });
  };

  const setLoading = (loading: boolean) => {
    dispatch({ type: 'SET_LOADING', payload: loading });
  };

  const setStreamingMessageId = (id: string | null) => {
    dispatch({ type: 'SET_STREAMING_MESSAGE_ID', payload: id });
  };

  const resetChat = () => {
    dispatch({ type: 'RESET_CHAT' });
  };

  const setSearchMode = (mode: SearchMode) => {
    dispatch({ type: 'SET_SEARCH_MODE', payload: mode });
  };

  const setAvailableTools = (tools: Tool[]) => {
    dispatch({ type: 'SET_AVAILABLE_TOOLS', payload: tools });
  };

  const setToolsLoading = (loading: boolean) => {
    dispatch({ type: 'SET_TOOLS_LOADING', payload: loading });
  };

  const setToolsError = (error: boolean) => {
    dispatch({ type: 'SET_TOOLS_ERROR', payload: error });
  };

  const value: ChatContextType = {
    state,
    dispatch,
    addMessage,
    updateMessage,
    addProcessingStep,
    addSources,
    addCharts,
    clearSourcesAndCharts,
    updateStreamingContent,
    setLoading,
    setStreamingMessageId,
    setSearchMode,
    setAvailableTools,
    setToolsLoading,
    setToolsError,
    resetChat,
  };

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

// Hook to use chat context
export function useChatContext() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChatContext must be used within a ChatProvider');
  }
  return context;
}
