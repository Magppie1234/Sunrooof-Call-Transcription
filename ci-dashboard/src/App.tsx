import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout';
import { AppStateProvider, ROLE_PAGES, useAppState } from './state/AppState';
import { CorpusMetaProvider } from './state/CorpusMetaProvider';
import { lazy, Suspense, type ReactNode } from 'react';
import { Loading } from './components/ui';

/**
 * Routes are lazy so a page's data does not load for someone who never opens it.
 * The static imports these replaced put every page — and therefore every page's
 * JSON — into one chunk: the built bundle was a single 105 MB JavaScript file,
 * which every visitor downloaded and parsed to see the Overview.
 *
 * Advanced QA is the clearest case. It reaches qa_audits.slim.json (10 MB), and
 * Review Sets reaches review_scenarios.json; neither belongs in the first paint
 * of a dashboard whose landing page is the Executive Overview.
 */
const ExecutiveOverview = lazy(() => import('./pages/ExecutiveOverview'));
const CustomerVoice = lazy(() => import('./pages/CustomerVoice'));
const Faqs = lazy(() => import('./pages/Faqs'));
const Regional = lazy(() => import('./pages/Regional'));
const Sales = lazy(() => import('./pages/Sales'));
const Agents = lazy(() => import('./pages/Agents'));
const Actions = lazy(() => import('./pages/Actions'));
const CallExplorer = lazy(() => import('./pages/CallExplorer'));
const CallDetail = lazy(() => import('./pages/CallDetail'));
const Alerts = lazy(() => import('./pages/Alerts'));
const DataQuality = lazy(() => import('./pages/DataQuality'));
const AdvancedQa = lazy(() => import('./pages/AdvancedQa'));
const ReviewScenarios = lazy(() => import('./pages/ReviewScenarios'));

/** Blocks pages outside the current role's allowed set (docs/10-rbac.md). */
function Guard({ path, children }: { path: string; children: ReactNode }) {
  const { role } = useAppState();
  const allowed = ROLE_PAGES[role];
  if (allowed !== 'all' && !allowed.includes(path)) {
    return <Navigate to={allowed[0]} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <AppStateProvider>
      {/* Outside AppShell, because the shell's own filter bar and banner read
          the corpus totals and date bounds this resolves. */}
      <CorpusMetaProvider>
      <HashRouter>
        <AppShell>
          {/* One boundary around the whole switch: navigating between pages
              swaps chunks, and without it React throws on the first suspend. */}
          <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Guard path="/"><ExecutiveOverview /></Guard>} />
            <Route path="/voice" element={<Guard path="/voice"><CustomerVoice /></Guard>} />
            <Route path="/faqs" element={<Guard path="/faqs"><Faqs /></Guard>} />
            <Route path="/regions" element={<Guard path="/regions"><Regional /></Guard>} />
            <Route path="/sales" element={<Guard path="/sales"><Sales /></Guard>} />
            <Route path="/agents" element={<Guard path="/agents"><Agents /></Guard>} />
            <Route path="/actions" element={<Guard path="/actions"><Actions /></Guard>} />
            <Route path="/calls" element={<Guard path="/calls"><CallExplorer /></Guard>} />
            <Route path="/calls/:id" element={<Guard path="/calls"><CallDetail /></Guard>} />
            <Route path="/alerts" element={<Guard path="/alerts"><Alerts /></Guard>} />
            <Route path="/review-sets" element={<Guard path="/review-sets"><ReviewScenarios /></Guard>} />
            <Route path="/advanced-qa" element={<Guard path="/advanced-qa"><AdvancedQa /></Guard>} />
            <Route path="/data" element={<Guard path="/data"><DataQuality /></Guard>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </AppShell>
      </HashRouter>
      </CorpusMetaProvider>
    </AppStateProvider>
  );
}
