import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { DataSource } from '../../services/agentService';
import type { RootState } from '../index';

interface DataSourceState {
  sources: Record<string, DataSource>; // keyed by data source ID
  loaded: boolean;
}

const initialState: DataSourceState = {
  sources: {},
  loaded: false,
};

const dataSourceSlice = createSlice({
  name: 'dataSources',
  initialState,
  reducers: {
    setDataSources: (state, action: PayloadAction<DataSource[]>) => {
      const byId: Record<string, DataSource> = {};
      for (const source of action.payload) {
        byId[source.id] = source;
      }
      state.sources = byId;
      state.loaded = true;
    },
  },
});

export const { setDataSources } = dataSourceSlice.actions;

export const selectDataSourceFields = (state: RootState, sourceId: string) => {
  const source = state.dataSources.sources[sourceId];
  if (!source) return null;
  return new Set(source.fields.map((f: { name: string }) => f.name).concat(source.groupableFields));
};

export default dataSourceSlice.reducer;
