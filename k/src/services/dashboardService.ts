/**
 * Dashboard Service - Handles persistence of dashboards to the backend
 */

import type { ChartConfig, ImageConfig, Filter } from '../types';
import type { ChatDashboard } from '../types/chat';
import type { Presentation } from '../types/slides';
import {
  fromApiDashboard,
  fromApiDashboards,
  fromApiPublishResponse,
  toApiDashboardCreate,
} from './api';
import type { ApiDashboardData, ApiPublishResponse } from './api/apiTypes';

const API_BASE = import.meta.env.VITE_AGENT_URL || 'http://localhost:8025';

class DashboardService {
  /**
   * Get all dashboards
   */
  async getAllDashboards(): Promise<ChatDashboard[]> {
    const response = await fetch(`${API_BASE}/api/dashboards`);
    if (!response.ok) {
      throw new Error(`Failed to fetch dashboards: ${response.statusText}`);
    }
    const data: ApiDashboardData[] = await response.json();
    return fromApiDashboards(data);
  }

  /**
   * Get a dashboard by ID
   */
  async getDashboard(id: string): Promise<ChatDashboard> {
    const response = await fetch(`${API_BASE}/api/dashboards/${id}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch dashboard: ${response.statusText}`);
    }
    const data: ApiDashboardData = await response.json();
    return fromApiDashboard(data);
  }

  /**
   * Create a new dashboard
   */
  async createDashboard(dashboard: ChatDashboard, filters?: Filter[]): Promise<ChatDashboard> {
    const response = await fetch(`${API_BASE}/api/dashboards`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(toApiDashboardCreate(dashboard, filters)),
    });
    if (!response.ok) {
      throw new Error(`Failed to create dashboard: ${response.statusText}`);
    }
    const data: ApiDashboardData = await response.json();
    return fromApiDashboard(data);
  }

  /**
   * Update an existing dashboard
   */
  async updateDashboard(
    id: string,
    updates: Partial<{
      title: string;
      charts: ChartConfig[];
      images: ImageConfig[];
      layout: Array<{ i: string; x: number; y: number; w: number; h: number }>;
      messages: Array<unknown>;
      filters: Filter[];
      dashboard_theme: string;
    }>
  ): Promise<ChatDashboard> {
    const response = await fetch(`${API_BASE}/api/dashboards/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(updates),
    });
    if (!response.ok) {
      throw new Error(`Failed to update dashboard: ${response.statusText}`);
    }
    const data: ApiDashboardData = await response.json();
    return fromApiDashboard(data);
  }

  /**
   * Delete a dashboard
   */
  async deleteDashboard(id: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/dashboards/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error(`Failed to delete dashboard: ${response.statusText}`);
    }
  }

  /**
   * Publish a dashboard (make it shareable)
   */
  async publishDashboard(id: string): Promise<{ shareId: string; shareUrl: string }> {
    const response = await fetch(`${API_BASE}/api/dashboards/${id}/publish`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Failed to publish dashboard: ${response.statusText}`);
    }
    const data: ApiPublishResponse = await response.json();
    return fromApiPublishResponse(data);
  }

  /**
   * Unpublish a dashboard
   */
  async unpublishDashboard(id: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/dashboards/${id}/unpublish`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Failed to unpublish dashboard: ${response.statusText}`);
    }
  }

  /**
   * Get a shared/published dashboard
   */
  async getSharedDashboard(shareId: string): Promise<ChatDashboard> {
    const response = await fetch(`${API_BASE}/api/shared/${shareId}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch shared dashboard: ${response.statusText}`);
    }
    const data: ApiDashboardData = await response.json();
    return fromApiDashboard(data);
  }

  /**
   * Export dashboard as JSON
   */
  async exportDashboard(id: string): Promise<ChatDashboard> {
    const response = await fetch(`${API_BASE}/api/dashboards/${id}/export`, {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error(`Failed to export dashboard: ${response.statusText}`);
    }
    const data: ApiDashboardData = await response.json();
    return fromApiDashboard(data);
  }

  /**
   * Download dashboard as JSON file
   */
  downloadDashboardAsFile(dashboard: ChatDashboard): void {
    const dataStr = JSON.stringify(dashboard, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `dashboard-${dashboard.title.replace(/\s+/g, '-').toLowerCase()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * Export a presentation as PPTX (triggers download)
   */
  async exportPptx(presentation: Presentation): Promise<void> {
    const response = await fetch(`${API_BASE}/api/presentations/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(presentation),
    });
    if (!response.ok) {
      throw new Error(`Export failed: ${response.statusText}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${presentation.title.replace(/\s+/g, '_')}.pptx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  /**
   * Save dashboard to backend (create or update)
   */
  async saveDashboard(dashboard: ChatDashboard, filters?: Filter[]): Promise<ChatDashboard> {
    try {
      // Try to update first
      return await this.updateDashboard(dashboard.id, {
        title: dashboard.title,
        charts: dashboard.dashboardCharts,
        images: dashboard.dashboardImages || [],
        layout: dashboard.layout,
        messages: dashboard.messages,
        filters: filters || dashboard.filters || [],
        dashboard_theme: dashboard.dashboardTheme || 'light',
      });
    } catch {
      // If update fails (404), create new
      return await this.createDashboard(dashboard, filters);
    }
  }
}

export const dashboardService = new DashboardService();
