import React, { useState, useMemo } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react';
import { ChartData } from '../../types';
import './ChartDataTable.css';

interface ChartDataTableProps {
  data: ChartData;
  title?: string;
}

type SortDirection = 'asc' | 'desc' | null;
type SortColumn = 'label' | number; // number represents dataset index

const ChartDataTable: React.FC<ChartDataTableProps> = ({ data, title }) => {
  const [sortColumn, setSortColumn] = useState<SortColumn | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      // Cycle through: asc -> desc -> null
      if (sortDirection === 'asc') {
        setSortDirection('desc');
      } else if (sortDirection === 'desc') {
        setSortDirection(null);
        setSortColumn(null);
      } else {
        setSortDirection('asc');
      }
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const getSortIndicator = (column: SortColumn) => {
    if (sortColumn !== column) return <span className="sort-indicator"><ArrowUpDown size={12} /></span>;
    if (sortDirection === 'asc') return <span className="sort-indicator active"><ArrowUp size={12} /></span>;
    if (sortDirection === 'desc') return <span className="sort-indicator active"><ArrowDown size={12} /></span>;
    return <span className="sort-indicator"><ArrowUpDown size={12} /></span>;
  };

  // Build table rows from chart data
  const tableRows = useMemo(() => {
    const rows: Array<{ label: string; values: (number | string)[] }> = [];

    if (data.labels && data.labels.length > 0) {
      // Standard chart data with labels
      data.labels.forEach((label, index) => {
        // Safely convert label to string in case backend returns {name,value} objects
        const safeLabel = typeof label === 'object' && label !== null && 'name' in label
          ? (label as unknown as { name: string }).name
          : String(label);
        const values = data.datasets.map((ds) => {
          const val = ds.data[index];
          if (typeof val === 'object' && val !== null && 'value' in val) {
            return val.value;
          }
          return typeof val === 'number' ? val : 0;
        });
        rows.push({ label: safeLabel, values });
      });
    } else if (data.datasets[0]?.data) {
      // Pie/funnel type data with name/value objects
      data.datasets[0].data.forEach((item) => {
        if (typeof item === 'object' && item !== null && 'name' in item && 'value' in item) {
          rows.push({ label: String(item.name), values: [item.value] });
        } else if (typeof item === 'number') {
          rows.push({ label: `Item ${rows.length + 1}`, values: [item] });
        }
      });
    }

    return rows;
  }, [data]);

  // Sort rows
  const sortedRows = useMemo(() => {
    if (!sortColumn || !sortDirection) return tableRows;

    return [...tableRows].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;

      if (sortColumn === 'label') {
        aVal = a.label;
        bVal = b.label;
      } else {
        aVal = a.values[sortColumn] ?? 0;
        bVal = b.values[sortColumn] ?? 0;
      }

      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }

      const numA = Number(aVal);
      const numB = Number(bVal);
      return sortDirection === 'asc' ? numA - numB : numB - numA;
    });
  }, [tableRows, sortColumn, sortDirection]);

  // Calculate totals for numeric columns
  const totals = useMemo(() => {
    if (data.datasets.length === 0) return [];
    return data.datasets.map((_, dsIndex) => {
      return sortedRows.reduce((sum, row) => {
        const val = row.values[dsIndex];
        return sum + (typeof val === 'number' ? val : 0);
      }, 0);
    });
  }, [sortedRows, data.datasets]);

  const formatNumber = (val: number | string): string => {
    if (typeof val === 'number') {
      return val.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    // Safely handle {name,value} objects that might slip through
    if (typeof val === 'object' && val !== null && 'value' in val) {
      return (val as unknown as { value: number }).value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }
    return String(val ?? '');
  };

  return (
    <div className="chart-data-table">
      {title && <div className="table-title">{title}</div>}
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th onClick={() => handleSort('label')} className="sortable">
                Label {getSortIndicator('label')}
              </th>
              {data.datasets.map((ds, index) => (
                <th key={index} onClick={() => handleSort(index)} className="sortable numeric">
                  {ds.name || `Value ${index + 1}`} {getSortIndicator(index)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <td>{row.label}</td>
                {row.values.map((val, valIndex) => (
                  <td key={valIndex} className="numeric">
                    {formatNumber(val)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>
                <strong>Total ({sortedRows.length} rows)</strong>
              </td>
              {totals.map((total, index) => (
                <td key={index} className="numeric">
                  <strong>{formatNumber(total)}</strong>
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
};

export default ChartDataTable;
