/**
 * Chat Input - Input field for sending messages to the agent
 */

import React, { useState, useRef, useEffect } from 'react';
import './ChatInput.css';

interface ChatInputProps {
  onSend: (message: string) => void;
  isProcessing: boolean;
  onCancel: () => void;
}

const ChatInput: React.FC<ChatInputProps> = ({ onSend, isProcessing, onCancel }) => {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [message]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isProcessing) {
      onSend(message.trim());
      setMessage('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <form className="chat-input-container" onSubmit={handleSubmit}>
      <div className="input-wrapper">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask me to create charts... (Enter to send, Shift+Enter for new line)"
          disabled={isProcessing}
          rows={1}
          className="chat-textarea"
        />
        <div className="input-actions">
          {isProcessing ? (
            <button type="button" className="cancel-btn" onClick={onCancel}>
              <span className="btn-icon">⏹</span>
              Cancel
            </button>
          ) : (
            <button
              type="submit"
              className="send-btn"
              disabled={!message.trim()}
            >
              <span className="btn-icon">→</span>
              Send
            </button>
          )}
        </div>
      </div>
      <div className="input-hint">
        <span>💡 Try: "Create a bar chart showing events by device type"</span>
      </div>
    </form>
  );
};

export default ChatInput;
