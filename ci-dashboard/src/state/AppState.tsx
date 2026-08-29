import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { DEFAULT_FILTERS, type FilterState } from '../lib/filters';

export type Role = 'Management' | 'Sales Manager' | 'Service Manager' | 'Quality Team' | 'Agent';

/** Pages visible per role — see docs/10-rbac.md. */
export const ROLE_PAGES: Record<Role, string[] | 'all'> = {
  Management: 'all',
  'Sales Manager': ['/', '/voice', '/faqs', '/regions', '/sales', '/agents', '/actions', '/calls', '/advanced-qa', '/review-sets', '/alerts'],
  'Service Manager': ['/', '/voice', '/faqs', '/agents', '/actions', '/calls', '/alerts'],
  'Quality Team': ['/voice', '/faqs', '/agents', '/calls', '/advanced-qa', '/review-sets', '/alerts', '/data'],
  Agent: ['/voice', '/faqs', '/actions', '/calls'],
};

/** Demo mapping: the Agent role sees only their own calls. */
export const AGENT_SELF_ID = 'E02';

export interface SavedView { name: string; filters: FilterState }

interface AppStateValue {
  filters: FilterState;
  setFilters: (patch: Partial<FilterState>) => void;
  resetFilters: () => void;
  role: Role;
  setRole: (r: Role) => void;
  savedViews: SavedView[];
  saveView: (name: string) => void;
  applyView: (name: string) => void;
  deleteView: (name: string) => void;
  exploreMode: boolean;
  setExploreMode: (enabled: boolean) => void;
}

const Ctx = createContext<AppStateValue | null>(null);

const VIEWS_KEY = 'ci-saved-views-v1';

function loadViews(): SavedView[] {
  try {
    const raw = localStorage.getItem(VIEWS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedView[];
    return parsed.map((v) => ({ name: v.name, filters: { ...DEFAULT_FILTERS, ...v.filters } }));
  } catch {
    return [];
  }
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [filters, setFiltersState] = useState<FilterState>(DEFAULT_FILTERS);
  const [role, setRoleState] = useState<Role>('Management');
  const [savedViews, setSavedViews] = useState<SavedView[]>(loadViews);
  const [exploreMode, setExploreMode] = useState(false);

  const setFilters = useCallback((patch: Partial<FilterState>) => {
    setFiltersState((f) => ({ ...f, ...patch }));
  }, []);

  const resetFilters = useCallback(() => {
    setFiltersState((f) => ({ ...DEFAULT_FILTERS, preset: f.preset, ...(role === 'Agent' ? { employee: AGENT_SELF_ID } : {}) }));
  }, [role]);

  const setRole = useCallback((r: Role) => {
    setRoleState(r);
    // Agents are scoped to their own calls; leaving Agent role releases the lock.
    setFiltersState((f) => ({ ...f, employee: r === 'Agent' ? AGENT_SELF_ID : f.employee === AGENT_SELF_ID ? '' : f.employee }));
  }, []);

  const persist = (views: SavedView[]) => {
    setSavedViews(views);
    try { localStorage.setItem(VIEWS_KEY, JSON.stringify(views)); } catch { /* storage unavailable */ }
  };

  const saveView = useCallback((name: string) => {
    persist([...savedViews.filter((v) => v.name !== name), { name, filters }]);
  }, [savedViews, filters]);

  const applyView = useCallback((name: string) => {
    const v = savedViews.find((x) => x.name === name);
    if (v) setFiltersState(v.filters);
  }, [savedViews]);

  const deleteView = useCallback((name: string) => {
    persist(savedViews.filter((v) => v.name !== name));
  }, [savedViews]);

  const value = useMemo(() => ({ filters, setFilters, resetFilters, role, setRole, savedViews, saveView, applyView, deleteView, exploreMode, setExploreMode }),
    [filters, setFilters, resetFilters, role, setRole, savedViews, saveView, applyView, deleteView, exploreMode]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAppState outside provider');
  return v;
}
