/* Main App component */
import { useState, useEffect } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopBar } from './components/TopBar';
import { ConfigPanel } from './components/ConfigPanel';
import { KPICards } from './components/KPICards';
import { ConversationTable } from './components/ConversationTable';
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

function Dashboard() {
  const [testRunId, setTestRunId] = useState<number | undefined>();
  const [isPolling, setIsPolling] = useState(false);

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
          <KPICards
            metrics={results?.metrics ?? null}
            isLoading={isLoading}
          />

          <ConversationTable
            conversations={results?.conversations ?? []}
            isLoading={isLoading && !results}
          />
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
