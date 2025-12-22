/* TanStack Query hooks for test results */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { startTest, getResults, getTestRuns, healthCheck, getUtteranceLibrary } from '../lib/api';
import type { StartTestRequest } from '../types';

export function useHealthCheck() {
    return useQuery({
        queryKey: ['health'],
        queryFn: healthCheck,
        refetchInterval: 10000, // Check every 10 seconds
    });
}

export function useTestResults(testRunId?: number, isPolling = false) {
    return useQuery({
        queryKey: ['results', testRunId],
        queryFn: () => getResults(testRunId),
        refetchInterval: isPolling ? 2000 : false, // Poll every 2 seconds when running
        enabled: true,
    });
}

export function useTestRuns(limit = 10) {
    return useQuery({
        queryKey: ['testRuns', limit],
        queryFn: () => getTestRuns(limit),
    });
}

export function useUtteranceLibrary() {
    return useQuery({
        queryKey: ['utteranceLibrary'],
        queryFn: getUtteranceLibrary,
    });
}

export function useStartTest() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: (request: StartTestRequest) => startTest(request),
        onSuccess: () => {
            // Invalidate results to trigger refresh
            queryClient.invalidateQueries({ queryKey: ['results'] });
            queryClient.invalidateQueries({ queryKey: ['testRuns'] });
        },
    });
}
