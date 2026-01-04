import { StreamMarkerType } from '../types';
import type { StreamChunk, Source, ChartConfig } from '../types';

export class StreamParser {
  private buffer: string = '';
  private inMarkdownBlock: boolean = false;

  /**
   * Parse incoming stream chunk and extract structured data
   * CRITICAL: Process chunks immediately, NOT line-by-line (matches chat.html)
   */
  parseChunk(chunk: string): StreamChunk[] {
    this.buffer += chunk;
    const results: StreamChunk[] = [];

    // Check for markers in the buffer (don't wait for complete lines)
    while (true) {
      let markerFound = false;

      // Check for MARKDOWN_CONTENT_START
      if (this.buffer.includes(StreamMarkerType.MARKDOWN_START)) {
        const startMarkerIndex = this.buffer.indexOf(StreamMarkerType.MARKDOWN_START);
        const contentStart = startMarkerIndex + StreamMarkerType.MARKDOWN_START.length;

        // Emit any content before the marker as raw
        if (startMarkerIndex > 0) {
          const beforeMarker = this.buffer.substring(0, startMarkerIndex);
          if (beforeMarker.trim()) {
            results.push({
              type: 'raw',
              content: beforeMarker,
              timestamp: Date.now(),
            });
          }
        }

        this.buffer = this.buffer.substring(contentStart);
        this.inMarkdownBlock = true;

        results.push({
          type: StreamMarkerType.MARKDOWN_START,
          content: '',
          timestamp: Date.now(),
        });

        markerFound = true;
        continue;
      }

      // Check for MARKDOWN_CONTENT_END
      if (this.buffer.includes(StreamMarkerType.MARKDOWN_END)) {
        const endMarkerIndex = this.buffer.indexOf(StreamMarkerType.MARKDOWN_END);
        const markdownContent = this.buffer.substring(0, endMarkerIndex);

        // Emit final markdown content chunk
        if (markdownContent) {
          results.push({
            type: 'content',
            content: markdownContent,
            timestamp: Date.now(),
          });
        }

        this.buffer = this.buffer.substring(endMarkerIndex + StreamMarkerType.MARKDOWN_END.length);
        this.inMarkdownBlock = false;

        results.push({
          type: StreamMarkerType.MARKDOWN_END,
          content: '',
          timestamp: Date.now(),
        });

        markerFound = true;
        continue;
      }

      // Check for FINAL_RESPONSE_START
      if (this.buffer.includes(StreamMarkerType.FINAL_RESPONSE_START)) {
        const markerIndex = this.buffer.indexOf(StreamMarkerType.FINAL_RESPONSE_START);

        // Emit any content before the marker
        if (markerIndex > 0) {
          const beforeMarker = this.buffer.substring(0, markerIndex);
          if (beforeMarker.trim()) {
            results.push({
              type: 'raw',
              content: beforeMarker,
              timestamp: Date.now(),
            });
          }
        }

        this.buffer = this.buffer.substring(markerIndex + StreamMarkerType.FINAL_RESPONSE_START.length);

        results.push({
          type: StreamMarkerType.FINAL_RESPONSE_START,
          content: '',
          timestamp: Date.now(),
        });

        markerFound = true;
        continue;
      }

      // Check for line-based markers (THINKING, PROCESSING_STEP, SOURCES, etc.)
      const lineEnd = this.buffer.indexOf('\n');
      if (lineEnd !== -1) {
        const lineRaw = this.buffer.substring(0, lineEnd);
        const line = lineRaw.trim(); // Trim only for marker checking
        this.buffer = this.buffer.substring(lineEnd + 1);

        // Check for line-based markers (only if line has content after trimming)
        if (line && line.startsWith(StreamMarkerType.THINKING)) {
          results.push({
            type: StreamMarkerType.THINKING,
            content: line.substring(StreamMarkerType.THINKING.length).trim(),
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (line && line.startsWith(StreamMarkerType.PROCESSING_STEP)) {
          results.push({
            type: StreamMarkerType.PROCESSING_STEP,
            content: line.substring(StreamMarkerType.PROCESSING_STEP.length).trim(),
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (line && line.startsWith(StreamMarkerType.SOURCES)) {
          const sourcesJson = line.substring(StreamMarkerType.SOURCES.length).trim();
          results.push({
            type: StreamMarkerType.SOURCES,
            content: sourcesJson,
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (line && line.startsWith(StreamMarkerType.CHART_CONFIGS)) {
          const chartsJson = line.substring(StreamMarkerType.CHART_CONFIGS.length).trim();
          results.push({
            type: StreamMarkerType.CHART_CONFIGS,
            content: chartsJson,
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (line && line.startsWith(StreamMarkerType.ERROR)) {
          results.push({
            type: StreamMarkerType.ERROR,
            content: line.substring(StreamMarkerType.ERROR.length).trim(),
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (line && line.startsWith(StreamMarkerType.RETRY_RESET)) {
          // Retry with reduced samples - clear sources and charts
          results.push({
            type: StreamMarkerType.RETRY_RESET,
            content: '',
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (!this.inMarkdownBlock && line) {
          // Raw content line (only if not in markdown block and has content)
          results.push({
            type: 'raw',
            content: line,
            timestamp: Date.now(),
          });
          markerFound = true;
        } else if (this.inMarkdownBlock) {
          // In markdown block - always emit lines (including blank lines)
          // Use lineRaw to preserve exact formatting for tables
          results.push({
            type: 'content',
            content: lineRaw + '\n',
            timestamp: Date.now(),
          });
          markerFound = true;
        }

        if (markerFound) continue;
      }

      // Progressive rendering: emit buffer content when in markdown mode
      if (this.inMarkdownBlock && this.buffer.length > 0 && !markerFound) {
        if (this.buffer.length >= 5) {
          results.push({
            type: 'content',
            content: this.buffer,
            timestamp: Date.now(),
          });
          this.buffer = '';
          break;
        }
      }

      // No more markers found, exit
      break;
    }

    return results;
  }

  /**
   * Parse sources JSON safely
   */
  parseSources(sourcesJson: string): Source[] {
    try {
      const parsed = JSON.parse(sourcesJson);
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {

      return [];
    }
  }

  /**
   * Parse chart configs JSON safely
   */
  parseChartConfigs(chartsJson: string): ChartConfig[] {
    try {
      const parsed = JSON.parse(chartsJson);
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {

      return [];
    }
  }

  /**
   * Reset parser state
   */
  reset() {
    this.buffer = '';
    this.inMarkdownBlock = false;
  }

  /**
   * Get remaining buffer content
   */
  getBuffer(): string {
    return this.buffer;
  }
}

/**
 * Stream reader utility that processes ReadableStream
 */
export async function* readStream(
  response: Response
): AsyncGenerator<string, void, unknown> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('Response body is not readable');
  }

  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      yield chunk;
    }
  } finally {
    reader.releaseLock();
  }
}
