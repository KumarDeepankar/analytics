import { useState, useEffect, useRef } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { useTheme } from '../contexts/ThemeContext';

interface MarkdownRendererProps {
  content: string;
  isStreaming?: boolean;
}

/**
 * Optimized markdown renderer using marked library (same as chat.html)
 * With character-by-character reveal animation
 */
export const MarkdownRenderer = ({ content, isStreaming = false }: MarkdownRendererProps) => {
  const { themeColors } = useTheme();
  const [displayedContent, setDisplayedContent] = useState('');
  const prevContentRef = useRef('');

  // Configure marked for GFM (GitHub Flavored Markdown)
  marked.setOptions({
    gfm: true,
    breaks: true,
    headerIds: false,
    mangle: false
  });

  // Character reveal animation for streaming content
  useEffect(() => {
    if (!isStreaming) {
      // If not streaming, show full content immediately
      setDisplayedContent(content);
      prevContentRef.current = content;
      return;
    }

    // Check if content has actually changed
    if (content === prevContentRef.current) {
      return;
    }

    // New content - reveal it character by character
    const prevLength = prevContentRef.current.length;
    const newLength = content.length;

    if (newLength > prevLength) {
      // Content was added - show it immediately (streaming from server)
      setDisplayedContent(content);
      prevContentRef.current = content;
    } else {
      // Content was replaced
      setDisplayedContent(content);
      prevContentRef.current = content;
    }
  }, [content, isStreaming]);

  // Parse and sanitize markdown
  const rawHtml = marked.parse(displayedContent || 'Thinking...') as string;
  const htmlContent = DOMPurify.sanitize(rawHtml);

  return (
    <>
      <style>
        {`
          .markdown-content {
            max-width: 100%;
            word-wrap: break-word;
            overflow-wrap: break-word;
          }

          .markdown-content > :first-child {
            margin-top: 0 !important;
          }

          .markdown-content h1,
          .markdown-content h2,
          .markdown-content h3,
          .markdown-content h4,
          .markdown-content h5,
          .markdown-content h6 {
            margin-top: 16px;
            margin-bottom: 8px;
            font-weight: 600;
            line-height: 1.3;
          }

          .markdown-content h1 {
            font-size: 1.4em;
            border-bottom: 1px solid ${themeColors.accent};
            padding-bottom: 6px;
            margin-bottom: 12px;
            opacity: 0.9;
          }

          .markdown-content h2 {
            font-size: 1.2em;
            border-bottom: 1px solid ${themeColors.border};
            padding-bottom: 4px;
            margin-bottom: 8px;
            opacity: 0.85;
          }

          .markdown-content h3 {
            font-size: 1.1em;
          }

          .markdown-content h4 {
            font-size: 1.0em;
            font-weight: 600;
          }

          .markdown-content p {
            margin: 0 0 12px 0;
            line-height: 1.6;
          }

          .markdown-content strong {
            font-weight: 700;
          }

          .markdown-content em {
            font-style: italic;
          }

          .markdown-content ul,
          .markdown-content ol {
            margin: 8px 0 12px 0;
            padding-left: 20px;
          }

          .markdown-content li {
            margin: 4px 0;
            line-height: 1.5;
          }

          .markdown-content li > p {
            margin: 0;
          }

          .markdown-content li > ul,
          .markdown-content li > ol {
            margin: 0;
          }

          .markdown-content blockquote {
            margin: 12px 0;
            padding: 10px 14px;
            border-left: 2px solid ${themeColors.accent};
            background: ${themeColors.surface}40;
            border-radius: 4px;
            opacity: 0.9;
          }

          .markdown-content blockquote p {
            margin: 0;
          }

          .markdown-content blockquote strong {
            color: ${themeColors.accent};
          }

          .markdown-content pre {
            margin: 12px 0;
            padding: 12px;
            background: ${themeColors.surface}dd;
            border: 1px solid ${themeColors.border};
            border-radius: 4px;
            overflow-x: auto;
          }

          .markdown-content pre code {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
            font-size: 0.9em;
            color: ${themeColors.text};
            background: none;
            padding: 0;
          }

          .markdown-content code {
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
            font-size: 0.9em;
            padding: 2px 4px;
            background: ${themeColors.surface}cc;
            border: 1px solid ${themeColors.border};
            border-radius: 3px;
            color: ${themeColors.accent};
          }

          .markdown-content table {
            width: 100%;
            margin: 12px 0;
            border-collapse: collapse;
            border: 1px solid ${themeColors.border};
            border-radius: 4px;
            overflow: hidden;
          }

          .markdown-content thead {
            background: ${themeColors.surface}60;
          }

          .markdown-content th {
            padding: 6px 10px;
            text-align: left;
            font-weight: 600;
            color: ${themeColors.text};
            border-bottom: 1px solid ${themeColors.accent};
          }

          .markdown-content tbody tr {
            border-bottom: 1px solid ${themeColors.border};
          }

          .markdown-content tbody tr:last-child {
            border-bottom: none;
          }

          .markdown-content tbody tr:hover {
            background: ${themeColors.surface}20;
          }

          .markdown-content td {
            padding: 6px 10px;
          }

          .markdown-content a {
            color: ${themeColors.accent};
            text-decoration: none;
            font-weight: 500;
          }

          .markdown-content a:hover {
            text-decoration: underline;
          }

          .markdown-content hr {
            margin: 12px 0;
            border: none;
            border-top: 1px solid ${themeColors.border};
          }

          .markdown-content img {
            max-width: 100%;
            height: auto;
            border-radius: 4px;
            margin: 8px 0;
          }
        `}
      </style>
      <div
        className="markdown-content"
        dangerouslySetInnerHTML={{ __html: htmlContent }}
      />
      <style>{`
        @keyframes cursorBlink {
          0%, 49% { opacity: 1; }
          50%, 100% { opacity: 0; }
        }
      `}</style>
      {isStreaming && (
        <span
          className="cursor"
          style={{
            display: 'inline-block',
            width: '8px',
            height: '16px',
            backgroundColor: themeColors.accent,
            marginLeft: '2px',
            animation: 'cursorBlink 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
            willChange: 'opacity',
          }}
        />
      )}
    </>
  );
};
