import { useCallback, useRef, useTransition } from 'react';
import { useChatContext } from '../contexts/ChatContext';
import { apiClient } from '../services/api';
import { StreamParser, readStream } from '../services/streamParser';
import { StreamMarkerType } from '../types';
import { getBackendUrl } from '../config';

/**
 * Custom hook for handling streaming search with optimized rendering
 */
export function useStreamingSearch() {
  const {
    state,
    addMessage,
    updateMessage,
    addProcessingStep,
    addSources,
    addCharts,
    clearSourcesAndCharts,
    updateStreamingContent,
    setLoading,
    setStreamingMessageId,
  } = useChatContext();

  const [isPending, startTransition] = useTransition();
  const parserRef = useRef<StreamParser | null>(null);
  const streamingContentRef = useRef<string>('');
  const animationFrameRef = useRef<number | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inMarkdownBlockRef = useRef<boolean>(false);
  const inFinalResponseRef = useRef<boolean>(false);
  const sourcesBufferRef = useRef<Map<string, any>>(new Map());

  /**
   * Perform search with streaming response
   */
  const performSearch = useCallback(
    async (query: string) => {
      if (!query.trim()) return;

      // Cancel any ongoing search
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      // Create new abort controller
      abortControllerRef.current = new AbortController();

      // Add user message
      addMessage({
        type: 'user',
        content: query,
      });

      // Create assistant message placeholder
      const assistantMessageId = addMessage({
        type: 'assistant',
        content: '',
        isStreaming: true,
        processingSteps: [],
        sources: [],
        charts: [],
      });

      setStreamingMessageId(assistantMessageId);
      setLoading(true);

      // Initialize stream parser
      parserRef.current = new StreamParser();
      streamingContentRef.current = '';
      inMarkdownBlockRef.current = false;
      inFinalResponseRef.current = false;
      sourcesBufferRef.current = new Map();

      try {
        // Determine if this is a follow-up
        const isFollowup = state.messages.length > 0;

        // Extract conversation history from existing messages (pairs of user/assistant)
        const conversationHistory: { query: string; response: string }[] = [];
        for (let i = 0; i < state.messages.length - 1; i += 2) {
          const userMsg = state.messages[i];
          const assistantMsg = state.messages[i + 1];
          if (userMsg?.type === 'user' && assistantMsg?.type === 'assistant') {
            conversationHistory.push({
              query: userMsg.content,
              response: assistantMsg.content,
            });
          }
        }

        // Make API request
        const response = await apiClient.search({
          query,
          enabled_tools: state.enabledTools,
          session_id: state.sessionId,
          is_followup: isFollowup,
          conversation_history: conversationHistory.length > 0 ? conversationHistory : undefined,
          theme: state.theme,
          llm_provider: state.selectedProvider,
          llm_model: state.selectedModel,
        });

        // Process stream
        await processStream(response, assistantMessageId);
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') {
          // Request was cancelled, no need to show error
        } else {
          // Client-side error handling with user-friendly messages
          let errorMessage = '⚠️ An unexpected error occurred while processing your request. Please try again, or raise a support ticket if the problem continues.';

          if (error instanceof Error) {
            const errorLower = error.message.toLowerCase();

            if (error.message.includes('Authentication required') ||
                error.message.includes('401') ||
                error.message.includes('403')) {
              errorMessage = '🔐 Authentication required. Please log in again.';
              // Redirect to backend login page
              setTimeout(() => {
                window.location.href = getBackendUrl('/auth/login');
              }, 2000);
            } else if (error.message.includes('Failed to fetch') ||
                       errorLower.includes('network') ||
                       errorLower.includes('connection')) {
              errorMessage = '⚠️ Unable to connect to the server. This may be a temporary network issue. Please check your connection and try again, or raise a support ticket if the problem continues.';
            } else if (errorLower.includes('timeout') || errorLower.includes('timed out')) {
              errorMessage = '⚠️ Your request took too long to process. Please try simplifying your query or using a shorter time range. If the issue persists, please raise a support ticket.';
            } else if (errorLower.includes('token') && (errorLower.includes('limit') || errorLower.includes('exceed'))) {
              errorMessage = '⚠️ Your query requires analyzing too much data. Please try using a shorter time range or being more specific in your query.';
            }
            // For other errors, use the generic message set above
          }

          updateStreamingContent(assistantMessageId, errorMessage);
        }
      } finally {
        // Mark message as no longer streaming
        updateMessage(assistantMessageId, { isStreaming: false });
        setLoading(false);
        setStreamingMessageId(null);
        parserRef.current?.reset();

        // Check tools after conversation turn - notify if connection lost
        try {
          await apiClient.refreshTools();
          const tools = await apiClient.getTools();
          if (!tools || tools.length === 0) {
            window.dispatchEvent(new CustomEvent('tools-unavailable'));
          }
        } catch {
          window.dispatchEvent(new CustomEvent('tools-unavailable'));
        }
      }
    },
    [
      state.messages.length,
      state.enabledTools,
      state.sessionId,
      state.theme,
      state.selectedProvider,
      state.selectedModel,
      addMessage,
      updateMessage,
      setStreamingMessageId,
      setLoading,
      updateStreamingContent,
      addProcessingStep,
      addSources,
      addCharts,
      clearSourcesAndCharts,
    ]
  );

  /**
   * Process the stream and update UI
   */
  const processStream = async (response: Response, messageId: string) => {
    const parser = parserRef.current;
    if (!parser) return;

    let contentBuffer = '';
    let lastRenderTime = 0;
    let charactersSinceLastRender = 0;
    const RENDER_THROTTLE_TIME = 50; // Milliseconds between renders (same as chat.html)
    const RENDER_THROTTLE_CHARS = 10; // Characters between renders (same as chat.html)

    // Function to update content
    const updateContent = () => {
      if (contentBuffer.length === 0) return;

      streamingContentRef.current += contentBuffer;
      contentBuffer = '';
      charactersSinceLastRender = 0;

      // Update immediately for streaming effect
      updateStreamingContent(messageId, streamingContentRef.current);
    };

    try {
      // Read stream chunks
      for await (const chunk of readStream(response)) {
        const parsedChunks = parser.parseChunk(chunk);

        for (const parsedChunk of parsedChunks) {
          switch (parsedChunk.type) {
            case StreamMarkerType.THINKING:
              // Node started/completed

              break;

            case StreamMarkerType.PROCESSING_STEP:
              // Add processing step
              addProcessingStep(messageId, parsedChunk.content);
              break;

            case StreamMarkerType.FINAL_RESPONSE_START:
              // Final response starting - allow content accumulation even without markdown markers

              inFinalResponseRef.current = true;
              break;

            case StreamMarkerType.MARKDOWN_START:
              // Start accumulating markdown
              streamingContentRef.current = '';
              inMarkdownBlockRef.current = true;

              break;

            case StreamMarkerType.MARKDOWN_END:
              // Flush any remaining content in buffer
              updateContent();
              // Mark markdown block as ended (but keep accumulated content)
              inMarkdownBlockRef.current = false;

              break;

            case StreamMarkerType.SOURCES:
              // Parse and add sources immediately (like chat.html)
              const sources = parser.parseSources(parsedChunk.content);
              if (sources.length > 0) {
                // Deduplicate and add immediately
                const newSources = sources.filter(source => {
                  // Skip sources without URL
                  if (!source.url) return false;
                  const normalizedUrl = source.url.toLowerCase().replace(/\/$/, '');
                  if (!sourcesBufferRef.current.has(normalizedUrl)) {
                    sourcesBufferRef.current.set(normalizedUrl, source);
                    return true;
                  }
                  return false;
                });

                if (newSources.length > 0) {

                  addSources(messageId, newSources);
                }
              }
              break;

            case StreamMarkerType.CHART_CONFIGS:
              // Parse and add charts
              const charts = parser.parseChartConfigs(parsedChunk.content);
              if (charts.length > 0) {
                addCharts(messageId, charts);
              }
              break;

            case StreamMarkerType.RETRY_RESET:
              // Retry with reduced samples - clear sources and charts
              clearSourcesAndCharts(messageId);
              sourcesBufferRef.current.clear();  // Clear deduplication buffer
              addProcessingStep(messageId, 'Retrying with reduced data...');
              break;

            case StreamMarkerType.ERROR:
              // Handle error - display user-friendly message from backend
              // Backend now sends properly formatted user-friendly messages
              updateStreamingContent(
                messageId,
                `⚠️ ${parsedChunk.content}`
              );
              break;

            case 'content':
            case 'raw':
              // Only accumulate content if we're inside a markdown block OR in final response
              if (!inMarkdownBlockRef.current && !inFinalResponseRef.current) {
                break;
              }

              // Filter out JSON tool responses (they should be in processing steps)
              const trimmedContent = parsedChunk.content.trim();

              // Check for various JSON patterns and query markers
              const isJson = (
                trimmedContent.startsWith('{') ||
                trimmedContent.startsWith('[') ||
                trimmedContent.includes('"jsonrpc"') ||  // JSON-RPC protocol
                trimmedContent.includes('Preview:') ||   // Preview marker
                trimmedContent.includes('rid_query:') || // Tool query marker
                trimmedContent.startsWith('query:') ||   // Query marker
                trimmedContent.startsWith('docid_query:') || // Document ID query marker
                trimmedContent.includes('"tool_call_id"') ||
                (trimmedContent.includes('"name":') && trimmedContent.includes('"arguments":')) ||
                (trimmedContent.includes('"result":') && trimmedContent.includes('"content":'))
              );

              if (isJson) {
                // Skip JSON tool responses - they should appear only in processing steps
                break;
              }

              // Accumulate content and render with throttling (like chat.html)
              contentBuffer += parsedChunk.content;
              charactersSinceLastRender += parsedChunk.content.length;

              // Throttled rendering: render every 10 chars OR every 50ms
              const now = Date.now();
              const timeSinceRender = now - lastRenderTime;
              const shouldRender = charactersSinceLastRender >= RENDER_THROTTLE_CHARS ||
                                  timeSinceRender >= RENDER_THROTTLE_TIME;

              if (shouldRender) {
                updateContent();
                lastRenderTime = now;
              }
              break;
          }
        }
      }

      // Final flush
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
      updateContent();

      // Sources are now added immediately as they arrive (no buffering at end)
      // Clear the deduplication buffer for next message
      sourcesBufferRef.current.clear();
    } catch (error) {

      throw error;
    }
  };

  /**
   * Cancel ongoing search
   */
  const cancelSearch = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    setLoading(false);
    setStreamingMessageId(null);
  }, [setLoading, setStreamingMessageId]);

  return {
    performSearch,
    cancelSearch,
    isSearching: state.isLoading || isPending,
  };
}
