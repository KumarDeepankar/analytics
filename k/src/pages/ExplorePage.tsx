import React, { useState } from 'react';
import { Search } from 'lucide-react';
import AISearchBar from '../components/common/AISearchBar';
import FilterPanel from '../components/filters/FilterPanel';
import './ExplorePage.css';

const ExplorePage: React.FC = () => {
  const [queryResult, setQueryResult] = useState<Record<string, unknown> | null>(null);
  const [rawData, setRawData] = useState<unknown[]>([]);

  const handleQueryResult = (result: unknown) => {
    setQueryResult(result as Record<string, unknown>);
    // Extract data from result if available
    const res = result as { data?: unknown[] };
    if (res.data) {
      setRawData(res.data);
    }
  };

  return (
    <div className="explore-page">
      <div className="explore-header">
        <h1>Data Explorer</h1>
        <p>Use natural language to explore your data</p>
      </div>

      <AISearchBar
        onQueryResult={handleQueryResult}
        placeholder="Ask anything... e.g., 'Show me top 10 customers by revenue last month'"
      />

      <FilterPanel />

      {queryResult && (
        <div className="query-result-panel">
          <div className="result-header">
            <h3>Query Result</h3>
          </div>
          <div className="result-content">
            <pre>{JSON.stringify(queryResult, null, 2)}</pre>
          </div>
        </div>
      )}

      {rawData.length > 0 && (
        <div className="data-table-panel">
          <div className="table-header">
            <h3>Data Preview</h3>
            <span className="record-count">{rawData.length} records</span>
          </div>
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  {Object.keys(rawData[0] as object).map((key) => (
                    <th key={key}>{key}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rawData.slice(0, 100).map((row, idx) => (
                  <tr key={idx}>
                    {Object.values(row as object).map((val, colIdx) => (
                      <td key={colIdx}>{String(val)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!queryResult && rawData.length === 0 && (
        <div className="explore-empty">
          <div className="empty-icon"><Search size={48} /></div>
          <h2>Start Exploring</h2>
          <p>Type a question in natural language to search and analyze your data</p>
          <div className="example-queries">
            <h4>Try these examples:</h4>
            <ul>
              <li>"Show me sales by region for last quarter"</li>
              <li>"What are the top 5 products by revenue?"</li>
              <li>"Compare monthly active users year over year"</li>
              <li>"Find customers with orders over $1000"</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};

export default ExplorePage;
