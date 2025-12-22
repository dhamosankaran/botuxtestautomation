/* API client functions */
import axios from 'axios';
import type {
    StartTestRequest,
    StartTestResponse,
    TestResultsResponse,
    HealthResponse,
    TestRun,
    UtteranceLibraryResponse,
} from '../types';

const API_BASE = '/api';

export async function healthCheck(): Promise<HealthResponse> {
    const response = await axios.get<HealthResponse>(`${API_BASE}/health`);
    return response.data;
}

export async function startTest(request: StartTestRequest): Promise<StartTestResponse> {
    const response = await axios.post<StartTestResponse>(`${API_BASE}/start-test`, request);
    return response.data;
}

export async function getResults(testRunId?: number): Promise<TestResultsResponse> {
    const params = testRunId ? { test_run_id: testRunId } : {};
    const response = await axios.get<TestResultsResponse>(`${API_BASE}/results`, { params });
    return response.data;
}

export async function getTestRuns(limit = 10): Promise<TestRun[]> {
    const response = await axios.get<TestRun[]>(`${API_BASE}/test-runs`, {
        params: { limit },
    });
    return response.data;
}

export async function getUtteranceLibrary(): Promise<UtteranceLibraryResponse> {
    const response = await axios.get<UtteranceLibraryResponse>(`${API_BASE}/utterances`);
    return response.data;
}

export async function getUtterancesByCategory(category: string): Promise<string[]> {
    const response = await axios.get<string[]>(`${API_BASE}/utterances/${category}`);
    return response.data;
}
