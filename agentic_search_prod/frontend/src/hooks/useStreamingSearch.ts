import { useCallback, useRef, useTransition } from 'react';
import { useChatContext } from '../contexts/ChatContext';
import { apiClient } from '../services/api';
import { StreamParser, readStream } from '../services/streamParser';
import { StreamMarkerType } from '../types';
import type { SearchMode } from '../types';
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
    setSearchMode,
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

        // Make API request based on search mode
        let response: Response;
        if (state.searchMode === 'research') {
          // Deep research mode
          response = await apiClient.research({
            query,
            session_id: state.sessionId,
            enabled_tools: state.enabledTools,
            llm_provider: state.selectedProvider,
            llm_model: state.selectedModel,
          });
        } else {
          // Quick search mode (default)
          response = await apiClient.search({
            query,
            enabled_tools: state.enabledTools,
            session_id: state.sessionId,
            is_followup: isFollowup,
            conversation_history: conversationHistory.length > 0 ? conversationHistory : undefined,
            theme: state.theme,
            llm_provider: state.selectedProvider,
            llm_model: state.selectedModel,
          });
        }

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
                error.message.includes('403') ||
                errorLower.includes('unauthorized')) {
              errorMessage = '🔐 Session expired. Redirecting to login...';
              // Redirect to backend login page
              setTimeout(() => {
                window.location.href = getBackendUrl('/auth/login');
              }, 1500);
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

        // Trigger conversation save after each response (so feedback can be submitted)
        window.dispatchEvent(new CustomEvent('save-conversation'));

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
      state.searchMode,
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
    const STREAM_INACTIVITY_TIMEOUT = 120000; // 2 minutes of no data = timeout

    // Inactivity timeout - abort if no data received for too long
    let inactivityTimer: ReturnType<typeof setTimeout> | null = null;
    const resetInactivityTimer = () => {
      if (inactivityTimer) clearTimeout(inactivityTimer);
      inactivityTimer = setTimeout(() => {
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }
      }, STREAM_INACTIVITY_TIMEOUT);
    };
    const clearInactivityTimer = () => {
      if (inactivityTimer) {
        clearTimeout(inactivityTimer);
        inactivityTimer = null;
      }
    };

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
      // Start inactivity timer
      resetInactivityTimer();

      // Read stream chunks
      for await (const chunk of readStream(response)) {
        // Reset inactivity timer on each chunk
        resetInactivityTimer();
        const parsedChunks = parser.parseChunk(chunk);

        for (const parsedChunk of parsedChunks) {
          switch (parsedChunk.type) {
            case StreamMarkerType.THINKING:
              // Thinking/processing step from research agent
              if (parsedChunk.content.trim()) {
                addProcessingStep(messageId, parsedChunk.content);
              }
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
                  // Handle url being an array (take first element) or string
                  const urlValue = Array.isArray(source.url) ? source.url[0] : source.url;
                  if (!urlValue || typeof urlValue !== 'string') return false;
                  const normalizedUrl = urlValue.toLowerCase().replace(/\/$/, '');
                  if (!sourcesBufferRef.current.has(normalizedUrl)) {
                    // Normalize the source object to have string url
                    source.url = urlValue;
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

            // Deep Research markers
            case StreamMarkerType.RESEARCH_START:
              addProcessingStep(messageId, '🔬 Starting deep research...');
              break;

            case StreamMarkerType.PHASE:
              // Phase changes (planning, aggregating, sampling, extracting, validating, synthesizing)
              const phaseLabels: Record<string, string> = {
                'planning': '📋 Planning research strategy',
                'aggregating': '📊 Computing dataset statistics',
                'sampling': '🎯 Sampling documents',
                'extracting': '📝 Extracting findings',
                'validating': '✓ Validating findings',
                'synthesizing': '📄 Synthesizing report',
              };
              const phaseLabel = phaseLabels[parsedChunk.content] || `Phase: ${parsedChunk.content}`;
              addProcessingStep(messageId, phaseLabel);
              break;

            case StreamMarkerType.PROGRESS:
              // Progress percentage - could be used for a progress bar
              addProcessingStep(messageId, `Progress: ${parsedChunk.content}%`);
              break;

            case StreamMarkerType.FINDING:
              // New finding discovered
              try {
                const finding = JSON.parse(parsedChunk.content);
                if (finding.claim) {
                  addProcessingStep(messageId, `📌 Finding: ${finding.claim}`);
                }
              } catch {
                // If not JSON, show as-is
                addProcessingStep(messageId, `📌 ${parsedChunk.content}`);
              }
              break;

            case StreamMarkerType.INTERIM_INSIGHT:
              // Intermediate insight
              addProcessingStep(messageId, `💡 ${parsedChunk.content}`);
              break;

            // Note: Research agent now uses MARKDOWN_CONTENT_START/END and FINAL_RESPONSE_START
            // for the final report, same as quick search agent

            case StreamMarkerType.KEY_FINDINGS:
              // Key findings summary - could show in UI
              try {
                const keyFindings = JSON.parse(parsedChunk.content);
                if (Array.isArray(keyFindings) && keyFindings.length > 0) {
                  addProcessingStep(messageId, `🔑 ${keyFindings.length} key findings identified`);
                }
              } catch {
                // Ignore parse errors
              }
              break;

            case StreamMarkerType.RESEARCH_COMPLETE:
              // Research complete with stats
              try {
                const stats = JSON.parse(parsedChunk.content);
                addProcessingStep(messageId,
                  `✅ Research complete: ${stats.findings_count || 0} findings from ${stats.docs_processed || 0} documents`
                );
              } catch {
                addProcessingStep(messageId, '✅ Research complete');
              }
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
    } finally {
      // Always clear inactivity timer
      clearInactivityTimer();
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
    searchMode: state.searchMode,
    setSearchMode,
  };
}
