/* TypeScript types for the Citi Bot QA Platform */

export interface Credentials {
    username: string;
    password: string;
}

export interface LoginSelectors {
    username: string;
    password: string;
    submit: string;
}

export interface ChatbotConfig {
    widget_selector: string;
    input_selector: string;
    send_selector: string;
    response_selector: string;
    login_selectors?: LoginSelectors;
}

export interface StartTestRequest {
    target_url: string;
    credentials?: Credentials;
    utterances: string[];
    utterance_categories?: string[];
    chatbot_config?: ChatbotConfig;
    use_library?: boolean;
}

export interface TestRun {
    id: number;
    target_url: string;
    started_at: string;
    completed_at: string | null;
    status: 'running' | 'completed' | 'failed';
    total_utterances: number;
    avg_latency_ms: number | null;
    self_service_rate: number | null;
    error_message: string | null;
    // LLM metrics
    avg_quality_score: number | null;
    avg_relevance_score: number | null;
    avg_helpfulness_score: number | null;
}

export interface ConversationLog {
    id: number;
    test_run_id: number;
    utterance: string;
    bot_response: string;
    latency_ms: number;
    status: 'pass' | 'fail' | 'error' | 'pending';
    timestamp: string;
    category: string;
    // LLM evaluation
    relevance_score: number | null;
    helpfulness_score: number | null;
    clarity_score: number | null;
    accuracy_score: number | null;
    overall_score: number | null;
    sentiment: string | null;
    llm_feedback: string | null;
    // Adaptive testing fields
    turns: number;
    menu_clicks: string;
    intent_identified: boolean;
    flow_completed: boolean;
    action_history: string;
}

export interface Metrics {
    avg_latency_ms: number;
    self_service_rate: number;
    total_tests: number;
    passed: number;
    failed: number;
    // LLM metrics
    avg_quality_score: number;
    avg_relevance_score: number;
    avg_helpfulness_score: number;
    // Adaptive testing metrics
    intent_accuracy: number;
    flow_completion_rate: number;
    avg_turns: number;
}

export interface TestResultsResponse {
    test_run: TestRun | null;
    conversations: ConversationLog[];
    metrics: Metrics;
}

export interface StartTestResponse {
    test_run_id: number;
    status: string;
}

export interface HealthResponse {
    status: string;
    timestamp: string;
    llm_available: boolean;
}

export interface UtteranceCategory {
    name: string;
    count: number;
    description: string;
}

export interface UtteranceLibraryResponse {
    categories: UtteranceCategory[];
    total_utterances: number;
}
