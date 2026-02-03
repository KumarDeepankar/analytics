/**
 * Chat Sidebar - Shows dashboard history and allows creating new ones
 */

import React, { useState } from 'react';
import { useAppSelector, useAppDispatch } from '../../store';
import {
  createChatDashboard,
  setActiveDashboard,
  deleteChatDashboard,
  renameDashboard,
} from '../../store/slices/chatSlice';
import './ChatSidebar.css';

const ChatSidebar: React.FC = () => {
  const dispatch = useAppDispatch();
  const { dashboards, activeDashboardId } = useAppSelector((state) => state.chat);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const handleCreateNew = () => {
    dispatch(createChatDashboard({}));
  };

  const handleSelect = (id: string) => {
    dispatch(setActiveDashboard(id));
  };

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Delete this dashboard?')) {
      dispatch(deleteChatDashboard(id));
    }
  };

  const handleStartEdit = (e: React.MouseEvent, id: string, title: string) => {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(title);
  };

  const handleSaveEdit = (id: string) => {
    if (editTitle.trim()) {
      dispatch(renameDashboard({ id, title: editTitle.trim() }));
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleKeyDown = (e: React.KeyboardEvent, id: string) => {
    if (e.key === 'Enter') {
      handleSaveEdit(id);
    } else if (e.key === 'Escape') {
      setEditingId(null);
      setEditTitle('');
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="chat-sidebar">
      <div className="sidebar-header">
        <h2>Dashboards</h2>
        <button className="new-dashboard-btn" onClick={handleCreateNew} title="New Dashboard">
          +
        </button>
      </div>

      <div className="dashboard-list">
        {dashboards.length === 0 ? (
          <div className="empty-state">
            <p>No dashboards yet</p>
            <button onClick={handleCreateNew}>Create your first dashboard</button>
          </div>
        ) : (
          dashboards.map((dashboard) => (
            <div
              key={dashboard.id}
              className={`dashboard-item ${dashboard.id === activeDashboardId ? 'active' : ''}`}
              onClick={() => handleSelect(dashboard.id)}
            >
              <div className="dashboard-icon">
                {dashboard.dashboardCharts.length > 0 ? '📊' : '💬'}
              </div>
              <div className="dashboard-info">
                {editingId === dashboard.id ? (
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    onBlur={() => handleSaveEdit(dashboard.id)}
                    onKeyDown={(e) => handleKeyDown(e, dashboard.id)}
                    autoFocus
                    className="edit-title-input"
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <span className="dashboard-title">{dashboard.title}</span>
                    <span className="dashboard-meta">
                      {dashboard.messages.length} messages · {dashboard.dashboardCharts.length} charts
                    </span>
                    <span className="dashboard-time">{formatDate(dashboard.updatedAt)}</span>
                  </>
                )}
              </div>
              <div className="dashboard-actions">
                <button
                  className="action-btn"
                  onClick={(e) => handleStartEdit(e, dashboard.id, dashboard.title)}
                  title="Rename"
                >
                  ✏️
                </button>
                <button
                  className="action-btn delete"
                  onClick={(e) => handleDelete(e, dashboard.id)}
                  title="Delete"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default ChatSidebar;
