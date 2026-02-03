import axios, { AxiosInstance } from 'axios';
import { AIQuery, AIQueryResponse, ChartConfig, Filter } from '../types';

class AIService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: import.meta.env.VITE_AI_SERVICE_URL || 'http://localhost:8000',
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  async processNaturalLanguageQuery(query: AIQuery): Promise<AIQueryResponse> {
    const response = await this.client.post<AIQueryResponse>('/api/ai/query', query);
    return response.data;
  }

  async suggestChartType(dataDescription: string): Promise<ChartConfig['type']> {
    const response = await this.client.post<{ chartType: ChartConfig['type'] }>(
      '/api/ai/suggest-chart',
      { dataDescription }
    );
    return response.data.chartType;
  }

  async generateInsights(chartData: unknown, filters: Filter[]): Promise<string[]> {
    const response = await this.client.post<{ insights: string[] }>('/api/ai/insights', {
      chartData,
      filters,
    });
    return response.data.insights;
  }

  async translateToOpenSearch(naturalLanguage: string, schema: unknown): Promise<unknown> {
    const response = await this.client.post('/api/ai/translate', {
      query: naturalLanguage,
      schema,
    });
    return response.data.openSearchQuery;
  }
}

export const aiService = new AIService();
