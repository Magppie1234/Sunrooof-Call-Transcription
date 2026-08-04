import { useEffect, useState } from 'react';
import { getService } from '../services';
import type { FilteredData } from '../lib/filters';
import type { AlertItem } from '../types/domain';
import { useAppState } from './AppState';

export const service = getService();

interface AsyncState<T> { data: T | null; loading: boolean; error: string | null }

/** Filtered call data for the current global filters. */
export function useFilteredData(): AsyncState<FilteredData> & { refresh: () => void } {
  const { filters } = useAppState();
  const [state, setState] = useState<AsyncState<FilteredData>>({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    service.getFiltered(filters)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((e: unknown) => { if (!cancelled) setState({ data: null, loading: false, error: String(e) }); });
    return () => { cancelled = true; };
  }, [filters, tick]);

  return { ...state, refresh: () => setTick((t) => t + 1) };
}

export function useAlerts(): AsyncState<AlertItem[]> & { refresh: () => void } {
  const { filters } = useAppState();
  const [state, setState] = useState<AsyncState<AlertItem[]>>({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    service.getAlerts(filters)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: null }); })
      .catch((e: unknown) => { if (!cancelled) setState({ data: null, loading: false, error: String(e) }); });
    return () => { cancelled = true; };
  }, [filters, tick]);

  return { ...state, refresh: () => setTick((t) => t + 1) };
}
