/* JourneyTestPanel - Journey-based testing with sequential utterance processing */
import { useState, useEffect } from 'react';
import { Play, CheckCircle, XCircle, Clock, ChevronDown, ChevronRight, MessageSquare, RefreshCw } from 'lucide-react';
import { cn } from '../lib/utils';

interface Journey {
    name: string;
    display_name: string;
    utterance_count: number;
    expected_intent: string;
    is_card_journey: boolean;
    group: string;
}

interface UtteranceProgress {
    utterance: string;
    status: 'pending' | 'testing' | 'pass' | 'fail';
    turns: number;
    score: number;
    reason: string;
}



export function JourneyTestPanel() {
    const [journeys, setJourneys] = useState<Journey[]>([]);
    const [selectedJourney, setSelectedJourney] = useState<string>('');
    const [isLoading, setIsLoading] = useState(true);
    const [isRunning, setIsRunning] = useState(false);
    const [testRunId, setTestRunId] = useState<number | null>(null);
    const [expandedGroups, setExpandedGroups] = useState<string[]>(['Cards']);
    const [utteranceResults, setUtteranceResults] = useState<UtteranceProgress[]>([]);


    // Fetch available journeys
    useEffect(() => {
        async function fetchJourneys() {
            try {
                const res = await fetch('http://localhost:8000/api/journey/list');
                if (res.ok) {
                    const data = await res.json();
                    setJourneys(data.journeys || []);
                }
            } catch (error) {
                console.error('Failed to fetch journeys:', error);
            } finally {
                setIsLoading(false);
            }
        }
        fetchJourneys();
    }, []);

    // Poll for results while running
    useEffect(() => {
        if (isRunning && testRunId) {
            const interval = setInterval(async () => {
                try {
                    const res = await fetch(`http://localhost:8000/api/results?test_run_id=${testRunId}`);
                    if (res.ok) {
                        const data = await res.json();

                        // Update utterance results
                        if (data.conversations) {
                            const results: UtteranceProgress[] = data.conversations.map((c: any) => ({
                                utterance: c.utterance,
                                status: c.status as 'pass' | 'fail',
                                turns: c.turns || 1,
                                score: c.overall_score || 0,
                                reason: c.llm_feedback || ''
                            }));
                            setUtteranceResults(results);
                        }

                        // Check if completed
                        if (data.test_run?.status === 'completed' || data.test_run?.status === 'failed') {
                            setIsRunning(false);
                        }
                    }
                } catch (error) {
                    console.error('Polling error:', error);
                }
            }, 3000);

            return () => clearInterval(interval);
        }
    }, [isRunning, testRunId]);


    const startJourneyTest = async () => {
        if (!selectedJourney) return;

        setIsRunning(true);
        setUtteranceResults([]);

        try {
            const res = await fetch('http://localhost:8000/api/journey/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    journey_name: selectedJourney,
                    target_url: 'https://www.citi.com'
                })
            });

            if (res.ok) {
                const data = await res.json();
                setTestRunId(data.test_run_id);

                // Initialize pending utterances
                const journey = journeys.find(j => j.name === selectedJourney);
                if (journey) {
                    // We don't know the actual utterances until they start, so just show count
                    console.log(`Started journey test with ${journey.utterance_count} utterances`);
                }
            } else {
                setIsRunning(false);
                alert('Failed to start journey test');
            }
        } catch (error) {
            setIsRunning(false);
            console.error('Failed to start test:', error);
        }
    };

    const toggleGroup = (group: string) => {
        setExpandedGroups(prev =>
            prev.includes(group)
                ? prev.filter(g => g !== group)
                : [...prev, group]
        );
    };

    // Group journeys
    const groupedJourneys = journeys.reduce((acc, j) => {
        const group = j.is_card_journey ? 'Cards' : 'Other';
        if (!acc[group]) acc[group] = [];
        acc[group].push(j);
        return acc;
    }, {} as Record<string, Journey[]>);

    const selectedJourneyInfo = journeys.find(j => j.name === selectedJourney);
    const passCount = utteranceResults.filter(u => u.status === 'pass').length;
    const failCount = utteranceResults.filter(u => u.status === 'fail').length;

    if (isLoading) {
        return (
            <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl p-6">
                <div className="animate-pulse space-y-4">
                    <div className="h-6 bg-slate-700 rounded w-1/3"></div>
                    <div className="h-32 bg-slate-700 rounded"></div>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="px-4 py-3 border-b border-slate-700/50">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    🎯 Journey-Based Testing
                </h3>
                <p className="text-sm text-gray-400 mt-1">
                    Select a journey to test each utterance as a complete conversation
                </p>
            </div>

            <div className="p-4 space-y-4">
                {/* Journey Selector */}
                <div className="space-y-2">
                    <label className="text-sm font-medium text-slate-300">Select Journey</label>

                    {Object.entries(groupedJourneys).map(([group, groupJourneys]) => (
                        <div key={group} className="bg-slate-900/50 rounded-lg border border-slate-700/30">
                            {/* Group Header */}
                            <button
                                onClick={() => toggleGroup(group)}
                                className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-800/50 rounded-t-lg transition-colors"
                            >
                                <span className="font-medium text-white flex items-center gap-2">
                                    {expandedGroups.includes(group) ? (
                                        <ChevronDown className="w-4 h-4" />
                                    ) : (
                                        <ChevronRight className="w-4 h-4" />
                                    )}
                                    {group === 'Cards' ? '💳' : '📄'} {group} Services
                                    <span className="text-xs text-gray-500">({groupJourneys.length})</span>
                                </span>
                            </button>

                            {/* Journey List */}
                            {expandedGroups.includes(group) && (
                                <div className="px-2 pb-2 space-y-1">
                                    {groupJourneys.map(journey => (
                                        <button
                                            key={journey.name}
                                            onClick={() => setSelectedJourney(journey.name)}
                                            disabled={isRunning}
                                            className={cn(
                                                "w-full text-left px-3 py-2 rounded-lg transition-colors",
                                                selectedJourney === journey.name
                                                    ? "bg-purple-600/30 border border-purple-500/50 text-white"
                                                    : "bg-slate-800/50 border border-slate-700/30 text-gray-300 hover:bg-slate-700/50",
                                                isRunning && "opacity-50 cursor-not-allowed"
                                            )}
                                        >
                                            <div className="flex justify-between items-center">
                                                <span className="font-medium">{journey.display_name}</span>
                                                <span className="text-xs text-gray-500">{journey.utterance_count} utterances</span>
                                            </div>
                                            <p className="text-xs text-gray-500 mt-1 truncate">
                                                {journey.expected_intent}
                                            </p>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ))}
                </div>

                {/* Selected Journey Info */}
                {selectedJourneyInfo && (
                    <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <span className="font-medium text-purple-300">
                                    {selectedJourneyInfo.display_name}
                                </span>
                                <p className="text-xs text-gray-400 mt-0.5">
                                    {selectedJourneyInfo.utterance_count} utterances will be tested sequentially
                                </p>
                            </div>
                            <div className="text-2xl font-bold text-purple-400">
                                {selectedJourneyInfo.utterance_count}
                            </div>
                        </div>
                    </div>
                )}

                {/* Run Button */}
                <button
                    onClick={startJourneyTest}
                    disabled={!selectedJourney || isRunning}
                    className={cn(
                        "w-full py-3 rounded-xl font-semibold text-white flex items-center justify-center gap-2 transition-all",
                        isRunning
                            ? "bg-slate-600 cursor-not-allowed"
                            : !selectedJourney
                                ? "bg-slate-700 cursor-not-allowed opacity-50"
                                : "bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 shadow-lg shadow-purple-500/30"
                    )}
                >
                    {isRunning ? (
                        <>
                            <RefreshCw className="w-5 h-5 animate-spin" />
                            Running Journey Test...
                        </>
                    ) : (
                        <>
                            <Play className="w-5 h-5" />
                            Run Journey Test
                        </>
                    )}
                </button>

                {/* Progress / Results */}
                {(isRunning || utteranceResults.length > 0) && (
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <h4 className="text-sm font-medium text-white flex items-center gap-2">
                                <MessageSquare className="w-4 h-4" />
                                Utterance Results
                            </h4>
                            {utteranceResults.length > 0 && (
                                <div className="flex items-center gap-3 text-sm">
                                    <span className="text-green-400 flex items-center gap-1">
                                        <CheckCircle className="w-4 h-4" /> {passCount}
                                    </span>
                                    <span className="text-red-400 flex items-center gap-1">
                                        <XCircle className="w-4 h-4" /> {failCount}
                                    </span>
                                </div>
                            )}
                        </div>

                        <div className="space-y-2 max-h-64 overflow-y-auto">
                            {utteranceResults.map((result, idx) => (
                                <div
                                    key={idx}
                                    className={cn(
                                        "p-3 rounded-lg border",
                                        result.status === 'pass'
                                            ? "bg-green-900/20 border-green-500/30"
                                            : result.status === 'fail'
                                                ? "bg-red-900/20 border-red-500/30"
                                                : "bg-slate-900/50 border-slate-700/30"
                                    )}
                                >
                                    <div className="flex items-start justify-between gap-2">
                                        <div className="flex-1">
                                            <p className="text-sm text-white font-medium">
                                                "{result.utterance}"
                                            </p>
                                            {result.reason && (
                                                <p className="text-xs text-gray-400 mt-1">
                                                    {result.reason}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs text-gray-500">
                                                {result.turns} turns
                                            </span>
                                            {result.status === 'pass' ? (
                                                <CheckCircle className="w-5 h-5 text-green-400" />
                                            ) : result.status === 'fail' ? (
                                                <XCircle className="w-5 h-5 text-red-400" />
                                            ) : (
                                                <Clock className="w-5 h-5 text-yellow-400 animate-pulse" />
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}

                            {isRunning && utteranceResults.length === 0 && (
                                <div className="text-center py-8 text-gray-500">
                                    <RefreshCw className="w-8 h-8 mx-auto mb-2 animate-spin" />
                                    <p>Waiting for first utterance to complete...</p>
                                    <p className="text-xs mt-1">Each utterance runs as a multi-turn conversation</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
