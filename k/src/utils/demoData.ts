import { Dashboard, ChartConfig, DashboardLayout } from '../types';
import { v4 as uuidv4 } from 'uuid';

export const createDemoDashboard = (): Dashboard => {
  const chart1Id = uuidv4();
  const chart2Id = uuidv4();

  const charts: ChartConfig[] = [
    {
      id: chart1Id,
      type: 'bar',
      title: 'Event Count by Country',
      dataSource: 'events_analytics_v4',
      xField: 'country',
      yField: 'event_count',
      aggregation: 'sum',
    },
    {
      id: chart2Id,
      type: 'pie',
      title: 'Events by Theme',
      dataSource: 'events_analytics_v4',
      xField: 'event_theme',
      yField: 'event_count',
      aggregation: 'sum',
    },
  ];

  const layout: DashboardLayout[] = [
    {
      i: chart1Id,
      x: 0,
      y: 0,
      w: 6,
      h: 4,
      minW: 3,
      minH: 2,
    },
    {
      i: chart2Id,
      x: 6,
      y: 0,
      w: 6,
      h: 4,
      minW: 3,
      minH: 2,
    },
  ];

  return {
    id: uuidv4(),
    name: 'Events Analytics Dashboard',
    description: 'Dashboard for events_analytics_v4 index',
    charts,
    layout,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
};
