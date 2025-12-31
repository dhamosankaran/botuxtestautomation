/* Main App component */
import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopBar } from './components/TopBar';
import { ConfigPanel } from './components/ConfigPanel';
import { KPICards } from './components/KPICards';
import { ConversationTable } from './components/ConversationTable';
import { ExportButtons } from './components/ExportButtons';
import { AnalyticsDashboard } from './components/AnalyticsDashboard';
import { IntelligentTestingPanel } from './components/IntelligentTestingPanel';
import { JourneyTestPanel } from './components/JourneyTestPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { TutorialsPanel } from './components/TutorialsPanel';
import { useTestResults, useStartTest } from './hooks/useTestResults';
import type { StartTestRequest } from './types';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

type TabType = 'results' | 'analytics' | 'intelligent' | 'journey' | 'settings' | 'tutorials';

function Dashboard() {
  const [testRunId, setTestRunId] = useState<number | undefined>();
  const [isPolling, setIsPolling] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('journey');  // Default to journey tab

  const { data: results, isLoading } = useTestResults(testRunId, isPolling);
  const startTestMutation = useStartTest();

  // Determine test status
  const testStatus = !results?.test_run
    ? 'idle'
    : results.test_run.status === 'running'
      ? 'running'
      : results.test_run.status === 'completed'
        ? 'completed'
        : 'failed';

  // Start/stop polling based on test status
  useEffect(() => {
    if (testStatus === 'running') {
      setIsPolling(true);
    } else if (testStatus === 'completed' || testStatus === 'failed') {
      setIsPolling(false);
    }
  }, [testStatus]);

  const handleStartTest = async (request: StartTestRequest) => {
    try {
      const response = await startTestMutation.mutateAsync(request);
      setTestRunId(response.test_run_id);
      setIsPolling(true);
      setActiveTab('results');  // Switch to results tab when test starts
    } catch (error) {
      console.error('Failed to start test:', error);
      alert('Failed to start test. Is the backend running on port 8000?');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white flex flex-col">
      <TopBar testStatus={testStatus} />

      <div className="flex flex-1 overflow-hidden">
        <ConfigPanel
          onStartTest={handleStartTest}
          isRunning={testStatus === 'running' || startTestMutation.isPending}
        />

        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Tab Navigation */}
          <div className="flex items-center justify-between">
            <div className="flex gap-1 bg-slate-800/50 rounded-lg p-1">
              <button
                onClick={() => setActiveTab('journey')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'journey'
                  ? 'bg-purple-600/30 text-purple-400'
                  : 'text-gray-400 hover:text-white'
                  }`}
              >
                🎯 Journey
              </button>
              <button
                onClick={() => setActiveTab('results')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'results'
                  ? 'bg-cyan-600/30 text-cyan-400'
                  : 'text-gray-400 hover:text-white'
                  }`}
              >
                📊 Results
              </button>
              <button
                onClick={() => setActiveTab('analytics')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'analytics'
                  ? 'bg-cyan-600/30 text-cyan-400'
                  : 'text-gray-400 hover:text-white'
                  }`}
              >
                📈 Analytics
              </button>
              <button
                onClick={() => setActiveTab('intelligent')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'intelligent'
                  ? 'bg-cyan-600/30 text-cyan-400'
                  : 'text-gray-400 hover:text-white'
                  }`}
              >
                🤖 Intelligent
              </button>
              <button
                onClick={() => setActiveTab('settings')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'settings'
                  ? 'bg-slate-600/30 text-slate-300'
                  : 'text-gray-400 hover:text-white'
                  }`}
              >
                ⚙️ Settings
              </button>
              <button
                onClick={() => setActiveTab('tutorials')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === 'tutorials'
                  ? 'bg-indigo-600/30 text-indigo-400'
                  : 'text-gray-400 hover:text-white'
                  }`}
              >
                📚 Tutorials
              </button>
            </div>

            {/* Export Buttons - show on results tab */}
            {activeTab === 'results' && results?.test_run?.id && (
              <ExportButtons testRunId={results.test_run.id} />
            )}
          </div>

          {/* Journey Tab */}
          {activeTab === 'journey' && (
            <JourneyTestPanel />
          )}

          {/* Results Tab */}
          {activeTab === 'results' && (
            <>
              <KPICards
                metrics={results?.metrics ?? null}
                isLoading={isLoading}
              />

              <ConversationTable
                conversations={results?.conversations ?? []}
                isLoading={isLoading && !results}
              />
            </>
          )}

          {/* Analytics Tab */}
          {activeTab === 'analytics' && (
            <AnalyticsDashboard />
          )}

          {/* Intelligent Testing Tab */}
          {activeTab === 'intelligent' && (
            <IntelligentTestingPanel />
          )}

          {/* Settings Tab */}
          {activeTab === 'settings' && (
            <SettingsPanel />
          )}

          {/* Tutorials Tab */}
          {activeTab === 'tutorials' && (
            <TutorialsPanel />
          )}
        </main>
      </div>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}

export default App;

