import { useState, useCallback } from 'react';
import { openSearchService } from '../services/openSearchService';
import { Filter, ChartConfig, ChartData, OpenSearchQuery } from '../types';

export const useOpenSearch = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchChartData = useCallback(
    async (chartConfig: ChartConfig, filters: Filter[]): Promise<ChartData | null> => {
      setIsLoading(true);
      setError(null);

      try {
        const data = await openSearchService.fetchChartData(chartConfig, filters);
        return data;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to fetch chart data';
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const executeQuery = useCallback(async <T>(query: OpenSearchQuery): Promise<T[] | null> => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await openSearchService.executeQuery<T>(query);
      return response.hits.hits.map((hit) => hit._source);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to execute query';
      setError(message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const search = useCallback(
    async (index: string, queryString: string, filters: Filter[] = []): Promise<unknown[]> => {
      setIsLoading(true);
      setError(null);

      try {
        const results = await openSearchService.search(index, queryString, filters);
        return results;
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Search failed';
        setError(message);
        return [];
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const getFieldValues = useCallback(
    async (index: string, field: string): Promise<string[]> => {
      try {
        return await openSearchService.getFieldValues(index, field);
      } catch (err) {
        console.error('Failed to get field values:', err);
        return [];
      }
    },
    []
  );

  return {
    fetchChartData,
    executeQuery,
    search,
    getFieldValues,
    isLoading,
    error,
    clearError: () => setError(null),
  };
};
