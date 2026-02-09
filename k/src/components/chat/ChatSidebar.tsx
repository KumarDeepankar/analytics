/**
 * Chat Sidebar - Shows dashboard history and allows creating new ones
 */

import React, { useState } from 'react';
import { BarChart3, MessageCircle, Pencil, Trash2, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { useAppSelector, useAppDispatch } from '../../store';
import {
  createChatDashboard,
  setActiveDashboard,
  deleteChatDashboard,
  deleteDashboardFromBackend,
  renameDashboard,
  saveDashboardToBackend,
} from '../../store/slices/chatSlice';
import type { ChatDashboard } from '../../types/chat';
import './ChatSidebar.css';

interface ChatSidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

const ChatSidebar: React.FC<ChatSidebarProps> = ({ isCollapsed = false, onToggleCollapse }) => {
  const dispatch = useAppDispatch();
  const { dashboards, activeDashboardId } = useAppSelector((state) => state.chat);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [showNewInput, setShowNewInput] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const handleCreateNew = () => {
    setNewTitle('');
    setShowNewInput(true);
  };

  const handleConfirmCreate = () => {
    const title = newTitle.trim() || `Dashboard ${dashboards.length + 1}`;
    dispatch(createChatDashboard({ title }));
    setShowNewInput(false);
    setNewTitle('');
  };

  const handleCancelCreate = () => {
    setShowNewInput(false);
    setNewTitle('');
  };

  const handleNewKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleConfirmCreate();
    } else if (e.key === 'Escape') {
      handleCancelCreate();
    }
  };

  const handleSelect = (id: string) => {
    dispatch(setActiveDashboard(id));
  };

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Delete this dashboard?')) {
      dispatch(deleteChatDashboard(id));
      dispatch(deleteDashboardFromBackend(id));
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
      // Persist to backend
      const dashboard = dashboards.find((d: ChatDashboard) => d.id === id);
      if (dashboard) {
        dispatch(saveDashboardToBackend({ ...dashboard, title: editTitle.trim() }));
      }
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
    <div className={`chat-sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        {!isCollapsed && <h2>Dashboards</h2>}
        <div className="sidebar-header-actions">
          {!isCollapsed && (
            <button className="new-dashboard-btn" onClick={handleCreateNew} title="New Dashboard">
              +
            </button>
          )}
          {onToggleCollapse && (
            <button
              className="sidebar-collapse-btn"
              onClick={onToggleCollapse}
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {isCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          )}
        </div>
      </div>

      <div className="dashboard-list">
        {isCollapsed ? (
          <>
            <button
              className="sidebar-collapsed-add"
              onClick={() => dispatch(createChatDashboard({ title: `Dashboard ${dashboards.length + 1}` }))}
              title="New Dashboard"
            >
              +
            </button>
            {dashboards.map((dashboard: ChatDashboard) => (
              <div
                key={dashboard.id}
                className={`dashboard-item ${dashboard.id === activeDashboardId ? 'active' : ''}`}
                onClick={() => handleSelect(dashboard.id)}
                title={dashboard.title}
              >
                <div className="dashboard-icon">
                  {dashboard.dashboardCharts.length > 0 ? <BarChart3 size={20} /> : <MessageCircle size={20} />}
                </div>
              </div>
            ))}
          </>
        ) : (
          <>
            {showNewInput && (
              <div className="new-dashboard-modal-overlay" onClick={handleCancelCreate}>
                <div className="new-dashboard-modal" onClick={(e) => e.stopPropagation()}>
                  <h3>New Dashboard</h3>
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    onKeyDown={handleNewKeyDown}
                    placeholder="Enter dashboard name..."
                    autoFocus
                    className="new-dashboard-modal-input"
                  />
                  <div className="new-dashboard-modal-actions">
                    <button className="modal-btn cancel" onClick={handleCancelCreate}>Cancel</button>
                    <button className="modal-btn create" onClick={handleConfirmCreate}>Create</button>
                  </div>
                </div>
              </div>
            )}
            {dashboards.length === 0 && !showNewInput ? (
              <div className="empty-state">
                <p>No dashboards yet</p>
                <button onClick={handleCreateNew}>Create your first dashboard</button>
              </div>
            ) : (
              dashboards.map((dashboard: ChatDashboard) => (
                <div
                  key={dashboard.id}
                  className={`dashboard-item ${dashboard.id === activeDashboardId ? 'active' : ''}`}
                  onClick={() => handleSelect(dashboard.id)}
                >
                  <div className="dashboard-icon">
                    {dashboard.dashboardCharts.length > 0 ? <BarChart3 size={20} /> : <MessageCircle size={20} />}
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
                      <Pencil size={14} />
                    </button>
                    <button
                      className="action-btn delete"
                      onClick={(e) => handleDelete(e, dashboard.id)}
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default React.memo(ChatSidebar);
export type { ChatSidebarProps };
