/**
 * Loads the corpus metadata once, before anything else renders.
 *
 * This is what lets the app shell stop importing the dataset. layout.tsx read
 * DATA_ANCHOR, DATASET_CALL_COUNT, DATASET_MIN_DATE and DATASET_MAX_DATE
 * straight out of realService, and data/taxonomy.ts read the employee and
 * dropdown lists straight out of dataset.slim.json — both static edges from the
 * always-loaded chunk into 21.5 MB of call records. Now the service supplies
 * them, so the shell is indifferent to whether they came from the snapshot, the
 * mock generator, or GET /api/meta.
 *
 * IT GATES RENDERING ON PURPOSE
 * data/taxonomy.ts hands out live bindings that installTaxonomy() fills in, and
 * the filter bar, applyFilters and half the metrics read them. Rendering the
 * app before they are populated would not throw — it would show a dashboard
 * with no employees and no regions, which looks like a data problem rather than
 * a load-order one. So children mount only after the metadata is in place.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { service } from './useData';
import { deriveCorpus, type Corpus } from '../data/corpusMeta';
import { installTaxonomy } from '../data/taxonomy';
import { Loading } from '../components/ui';

const Ctx = createContext<Corpus | null>(null);

/**
 * The corpus totals and date bounds. Safe to call from any component: the
 * provider does not render its children until the value exists, so this never
 * returns null in practice and callers need no null checks.
 */
export function useCorpus(): Corpus {
  const corpus = useContext(Ctx);
  if (!corpus) {
    throw new Error('useCorpus() outside CorpusMetaProvider — wrap the tree in it.');
  }
  return corpus;
}

export function CorpusMetaProvider({ children }: { children: ReactNode }) {
  const [corpus, setCorpus] = useState<Corpus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    service.getMeta()
      .then((meta) => {
        if (cancelled) return;
        // Before setCorpus, not after: the state update renders the children,
        // and they read the taxonomy bindings during that render.
        installTaxonomy(meta);
        setCorpus(deriveCorpus(meta));
      })
      .catch((e: unknown) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, []);

  if (error) {
    // Loud and specific. Every page depends on this, so a silent empty
    // dashboard would send someone looking at the data rather than at the API.
    return (
      <div style={{ padding: 32, maxWidth: 640 }}>
        <h1 style={{ fontSize: 18, marginBottom: 8 }}>Could not load the dataset metadata</h1>
        <p style={{ fontSize: 13, color: 'var(--ink-2)', marginBottom: 12 }}>
          The dashboard needs the corpus totals, date bounds and filter lists before it can
          render any page. Nothing below this point has loaded.
        </p>
        <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', color: 'var(--ink-2)' }}>{error}</pre>
      </div>
    );
  }
  if (!corpus) return <Loading />;

  return <Ctx.Provider value={corpus}>{children}</Ctx.Provider>;
}
