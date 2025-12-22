/* KPICards component - Display key metrics including LLM scores */
import { Clock, TrendingUp, CheckCircle, XCircle, Star, Brain, Target, Workflow } from 'lucide-react';
import type { Metrics } from '../types';
import { cn } from '../lib/utils';

interface KPICardsProps {
    metrics: Metrics | null;
    isLoading: boolean;
}

export function KPICards({ metrics, isLoading }: KPICardsProps) {
    const avgLatency = metrics?.avg_latency_ms ?? 0;
    const selfServiceRate = metrics?.self_service_rate ?? 0;
    const total = metrics?.total_tests ?? 0;
    const passed = metrics?.passed ?? 0;
    const failed = metrics?.failed ?? 0;
    const avgQuality = metrics?.avg_quality_score ?? 0;
    const avgHelpfulness = metrics?.avg_helpfulness_score ?? 0;
    const intentAccuracy = metrics?.intent_accuracy ?? 0;
    const flowCompletionRate = metrics?.flow_completion_rate ?? 0;

    // Color coding for response time
    const latencyColor = avgLatency === 0
        ? 'text-slate-400'
        : avgLatency < 1000
            ? 'text-emerald-400'
            : avgLatency < 3000
                ? 'text-amber-400'
                : 'text-red-400';

    const latencyBg = avgLatency === 0
        ? 'from-slate-500/10 to-slate-600/10 border-slate-500/20'
        : avgLatency < 1000
            ? 'from-emerald-500/10 to-emerald-600/10 border-emerald-500/20'
            : avgLatency < 3000
                ? 'from-amber-500/10 to-amber-600/10 border-amber-500/20'
                : 'from-red-500/10 to-red-600/10 border-red-500/20';

    // Color coding for quality score (0-10)
    const qualityColor = avgQuality === 0
        ? 'text-slate-400'
        : avgQuality >= 7
            ? 'text-emerald-400'
            : avgQuality >= 5
                ? 'text-amber-400'
                : 'text-red-400';

    const qualityBg = avgQuality === 0
        ? 'from-slate-500/10 to-slate-600/10 border-slate-500/20'
        : avgQuality >= 7
            ? 'from-emerald-500/10 to-emerald-600/10 border-emerald-500/20'
            : avgQuality >= 5
                ? 'from-amber-500/10 to-amber-600/10 border-amber-500/20'
                : 'from-red-500/10 to-red-600/10 border-red-500/20';

    // Color coding for self-service rate
    const ssrColor = selfServiceRate === 0
        ? 'text-slate-400'
        : selfServiceRate >= 80
            ? 'text-emerald-400'
            : selfServiceRate >= 50
                ? 'text-amber-400'
                : 'text-red-400';

    const ssrBg = selfServiceRate === 0
        ? 'from-slate-500/10 to-slate-600/10 border-slate-500/20'
        : selfServiceRate >= 80
            ? 'from-emerald-500/10 to-emerald-600/10 border-emerald-500/20'
            : selfServiceRate >= 50
                ? 'from-amber-500/10 to-amber-600/10 border-amber-500/20'
                : 'from-red-500/10 to-red-600/10 border-red-500/20';

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
            {/* LLM Quality Score - NEW */}
            <div className={cn(
                "relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]",
                qualityBg
            )}>
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Quality Score</span>
                        <Brain className={cn("w-5 h-5", qualityColor)} />
                    </div>
                    <div className={cn("text-3xl font-bold tracking-tight", qualityColor)}>
                        {isLoading ? (
                            <div className="h-9 w-20 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{avgQuality.toFixed(1)}</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">out of 10</p>
                </div>
            </div>

            {/* Average Response Time */}
            <div className={cn(
                "relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]",
                latencyBg
            )}>
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Avg Response</span>
                        <Clock className={cn("w-5 h-5", latencyColor)} />
                    </div>
                    <div className={cn("text-3xl font-bold tracking-tight", latencyColor)}>
                        {isLoading ? (
                            <div className="h-9 w-24 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{avgLatency.toFixed(0)}</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">milliseconds</p>
                </div>
            </div>

            {/* Self-Service Rate */}
            <div className={cn(
                "relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]",
                ssrBg
            )}>
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Self-Service</span>
                        <TrendingUp className={cn("w-5 h-5", ssrColor)} />
                    </div>
                    <div className={cn("text-3xl font-bold tracking-tight", ssrColor)}>
                        {isLoading ? (
                            <div className="h-9 w-20 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{selfServiceRate.toFixed(1)}%</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">resolved by bot</p>
                </div>
            </div>

            {/* Helpfulness Score - NEW */}
            <div className={cn(
                "relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]",
                avgHelpfulness >= 7 ? 'from-purple-500/10 to-purple-600/10 border-purple-500/20' : 'from-slate-500/10 to-slate-600/10 border-slate-500/20'
            )}>
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Helpfulness</span>
                        <Star className={cn("w-5 h-5", avgHelpfulness >= 7 ? 'text-purple-400' : 'text-slate-400')} />
                    </div>
                    <div className={cn("text-3xl font-bold tracking-tight", avgHelpfulness >= 7 ? 'text-purple-400' : 'text-slate-400')}>
                        {isLoading ? (
                            <div className="h-9 w-16 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{avgHelpfulness.toFixed(1)}</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">out of 10</p>
                </div>
            </div>

            {/* Passed Tests */}
            <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-emerald-500/10 to-emerald-600/10 border-emerald-500/20 p-5 transition-all duration-300 hover:scale-[1.02]">
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Passed</span>
                        <CheckCircle className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div className="text-3xl font-bold tracking-tight text-emerald-400">
                        {isLoading ? (
                            <div className="h-9 w-16 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{passed}</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">of {total} tests</p>
                </div>
            </div>

            {/* Failed Tests */}
            <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-red-500/10 to-red-600/10 border-red-500/20 p-5 transition-all duration-300 hover:scale-[1.02]">
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Failed</span>
                        <XCircle className="w-5 h-5 text-red-400" />
                    </div>
                    <div className="text-3xl font-bold tracking-tight text-red-400">
                        {isLoading ? (
                            <div className="h-9 w-16 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{failed}</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">of {total} tests</p>
                </div>
            </div>

            {/* Intent Accuracy */}
            <div className={cn(
                "relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]",
                intentAccuracy >= 80 ? 'from-cyan-500/10 to-cyan-600/10 border-cyan-500/20' : 'from-slate-500/10 to-slate-600/10 border-slate-500/20'
            )}>
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Intent</span>
                        <Target className={cn("w-5 h-5", intentAccuracy >= 80 ? 'text-cyan-400' : 'text-slate-400')} />
                    </div>
                    <div className={cn("text-3xl font-bold tracking-tight", intentAccuracy >= 80 ? 'text-cyan-400' : 'text-slate-400')}>
                        {isLoading ? (
                            <div className="h-9 w-16 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{intentAccuracy.toFixed(0)}%</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">accuracy</p>
                </div>
            </div>

            {/* Flow Completion */}
            <div className={cn(
                "relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 transition-all duration-300 hover:scale-[1.02]",
                flowCompletionRate >= 80 ? 'from-indigo-500/10 to-indigo-600/10 border-indigo-500/20' : 'from-slate-500/10 to-slate-600/10 border-slate-500/20'
            )}>
                <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
                <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Flows</span>
                        <Workflow className={cn("w-5 h-5", flowCompletionRate >= 80 ? 'text-indigo-400' : 'text-slate-400')} />
                    </div>
                    <div className={cn("text-3xl font-bold tracking-tight", flowCompletionRate >= 80 ? 'text-indigo-400' : 'text-slate-400')}>
                        {isLoading ? (
                            <div className="h-9 w-16 bg-slate-700/50 rounded animate-pulse" />
                        ) : (
                            <span className="tabular-nums">{flowCompletionRate.toFixed(0)}%</span>
                        )}
                    </div>
                    <p className="text-sm text-slate-500 mt-1">completed</p>
                </div>
            </div>
        </div>
    );
}

