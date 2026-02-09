/**
 * Image Service - Handles image upload and URL resolution
 */

const API_BASE = import.meta.env.VITE_AGENT_URL || 'http://localhost:8025';

class ImageService {
  /**
   * Upload an image file to the backend
   */
  async uploadImage(file: File): Promise<{ url: string; filename: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/api/images/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || 'Failed to upload image');
    }

    return response.json();
  }

  /**
   * Build full URL for a backend-stored image
   */
  getImageUrl(filenameOrPath: string): string {
    if (filenameOrPath.startsWith('http://') || filenameOrPath.startsWith('https://')) {
      return filenameOrPath;
    }
    if (filenameOrPath.startsWith('/api/images/')) {
      return `${API_BASE}${filenameOrPath}`;
    }
    return `${API_BASE}/api/images/${filenameOrPath}`;
  }
}

export const imageService = new ImageService();
