import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout';
import { AppStateProvider, ROLE_PAGES, useAppState } from './state/AppState';
import ExecutiveOverview from './pages/ExecutiveOverview';
import CustomerVoice from './pages/CustomerVoice';
import Faqs from './pages/Faqs';
import Regional from './pages/Regional';
import Sales from './pages/Sales';
import Agents from './pages/Agents';
import Actions from './pages/Actions';
import CallExplorer from './pages/CallExplorer';
import CallDetail from './pages/CallDetail';
import Alerts from './pages/Alerts';
import DataQuality from './pages/DataQuality';
import AdvancedQa from './pages/AdvancedQa';
import ReviewScenarios from './pages/ReviewScenarios';
import type { ReactNode } from 'react';

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
      <HashRouter>
        <AppShell>
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
        </AppShell>
      </HashRouter>
    </AppStateProvider>
  );
}
