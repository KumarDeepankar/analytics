import axios, { AxiosInstance } from 'axios';
import { Filter, ChartConfig, ChartData, OpenSearchQuery, OpenSearchResponse } from '../types';

class OpenSearchService {
  private client: AxiosInstance;

  constructor() {
    // Use proxy in development to avoid CORS issues
    const baseURL = import.meta.env.DEV ? '/opensearch' : (import.meta.env.VITE_OPENSEARCH_URL || 'http://localhost:9200');
    this.client = axios.create({
      baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  private buildFilterQuery(filters: Filter[]): unknown[] {
    return filters.map((filter) => {
      switch (filter.operator) {
        case 'eq':
          return { term: { [filter.field]: filter.value } };
        case 'neq':
          return { bool: { must_not: { term: { [filter.field]: filter.value } } } };
        case 'gt':
          return { range: { [filter.field]: { gt: filter.value } } };
        case 'gte':
          return { range: { [filter.field]: { gte: filter.value } } };
        case 'lt':
          return { range: { [filter.field]: { lt: filter.value } } };
        case 'lte':
          return { range: { [filter.field]: { lte: filter.value } } };
        case 'in':
          return { terms: { [filter.field]: filter.value } };
        case 'contains':
          return { wildcard: { [filter.field]: `*${filter.value}*` } };
        default:
          return { term: { [filter.field]: filter.value } };
      }
    });
  }

  private buildAggregation(chartConfig: ChartConfig): Record<string, unknown> {
    const { type, xField, yField, aggregation = 'sum' } = chartConfig;

    if (!xField) return {};

    const aggField = yField || xField;

    const metricAgg =
      aggregation === 'count'
        ? { value_count: { field: aggField } }
        : { [aggregation]: { field: aggField } };

    switch (type) {
      case 'pie':
      case 'funnel':
        return {
          categories: {
            terms: { field: xField, size: 20 },
            aggs: { metric: metricAgg },
          },
        };

      case 'bar':
      case 'line':
      case 'area':
        return {
          categories: {
            terms: { field: xField, size: 50, order: { _key: 'asc' } },
            aggs: { metric: metricAgg },
          },
        };

      case 'scatter':
        return {
          x_values: {
            histogram: { field: xField, interval: 10 },
            aggs: {
              y_values: {
                avg: { field: yField },
              },
            },
          },
        };

      case 'heatmap':
        return {
          x_axis: {
            terms: { field: xField, size: 20 },
            aggs: {
              y_axis: {
                terms: { field: chartConfig.seriesField || yField, size: 20 },
                aggs: { metric: metricAgg },
              },
            },
          },
        };

      default:
        return {
          categories: {
            terms: { field: xField, size: 20 },
            aggs: { metric: metricAgg },
          },
        };
    }
  }

  async fetchChartData(chartConfig: ChartConfig, filters: Filter[]): Promise<ChartData> {
    const query: OpenSearchQuery = {
      index: chartConfig.dataSource,
      query: {
        bool: {
          filter: this.buildFilterQuery(filters),
        },
      },
      aggs: this.buildAggregation(chartConfig),
      size: 0,
    };

    const response = await this.executeQuery<unknown>(query);
    return this.transformToChartData(response, chartConfig);
  }

  async executeQuery<T>(query: OpenSearchQuery): Promise<OpenSearchResponse<T>> {
    const { index, ...body } = query;
    const response = await this.client.post<OpenSearchResponse<T>>(`/${index}/_search`, body);
    return response.data;
  }

  private transformToChartData(
    response: OpenSearchResponse<unknown>,
    chartConfig: ChartConfig
  ): ChartData {
    const aggs = response.aggregations;
    if (!aggs) {
      return { labels: [], datasets: [] };
    }

    const categoriesAgg = aggs.categories as {
      buckets: Array<{ key: string; metric: { value: number } }>;
    };

    if (categoriesAgg?.buckets) {
      const labels = categoriesAgg.buckets.map((b) => String(b.key));
      const data = categoriesAgg.buckets.map((b) => b.metric?.value ?? 0);

      return {
        labels,
        datasets: [
          {
            name: chartConfig.title,
            data:
              chartConfig.type === 'pie'
                ? labels.map((label, i) => ({ name: label, value: data[i] }))
                : data,
          },
        ],
      };
    }

    return { labels: [], datasets: [] };
  }

  async search(index: string, queryString: string, filters: Filter[] = []): Promise<unknown[]> {
    const query: OpenSearchQuery = {
      index,
      query: {
        bool: {
          must: [{ query_string: { query: queryString } }],
          filter: this.buildFilterQuery(filters),
        },
      },
      size: 100,
    };

    const response = await this.executeQuery(query);
    return response.hits.hits.map((hit) => hit._source);
  }

  async getFieldValues(index: string, field: string, size = 100): Promise<string[]> {
    const query: OpenSearchQuery = {
      index,
      query: { match_all: {} },
      aggs: {
        values: {
          terms: { field, size },
        },
      },
      size: 0,
    };

    const response = await this.executeQuery(query);
    const valuesAgg = response.aggregations?.values as {
      buckets: Array<{ key: string }>;
    };

    return valuesAgg?.buckets?.map((b) => b.key) || [];
  }
}

export const openSearchService = new OpenSearchService();
