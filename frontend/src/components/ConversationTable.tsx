/* ConversationTable component - Display conversation logs with LLM evaluation */
import { MessageSquare, Bot, CheckCircle, XCircle, Clock, Star, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import type { ConversationLog } from '../types';
import { cn } from '../lib/utils';

interface ConversationTableProps {
    conversations: ConversationLog[];
    isLoading: boolean;
}

export function ConversationTable({ conversations, isLoading }: ConversationTableProps) {
    const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

    const toggleRow = (id: number) => {
        const newExpanded = new Set(expandedRows);
        if (newExpanded.has(id)) {
            newExpanded.delete(id);
        } else {
            newExpanded.add(id);
        }
        setExpandedRows(newExpanded);
    };

    if (isLoading) {
        return (
            <div className="bg-slate-900/30 rounded-2xl border border-slate-700/50 p-6">
                <div className="space-y-4">
                    {[1, 2, 3].map((i) => (
                        <div key={i} className="animate-pulse">
                            <div className="h-4 bg-slate-700/50 rounded w-3/4 mb-2" />
                            <div className="h-4 bg-slate-700/50 rounded w-1/2" />
                        </div>
                    ))}
                </div>
            </div>
        );
    }

    if (conversations.length === 0) {
        return (
            <div className="bg-slate-900/30 rounded-2xl border border-slate-700/50 p-12 text-center">
                <div className="w-16 h-16 bg-slate-800/50 rounded-full flex items-center justify-center mx-auto mb-4">
                    <MessageSquare className="w-8 h-8 text-slate-500" />
                </div>
                <h3 className="text-lg font-medium text-slate-300 mb-2">No conversations yet</h3>
                <p className="text-sm text-slate-500">Run a test to see the conversation logs here</p>
            </div>
        );
    }

    return (
        <div className="bg-slate-900/30 rounded-2xl border border-slate-700/50 overflow-hidden">
            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-700/50 bg-slate-800/30">
                <h3 className="text-sm font-semibold text-purple-300 uppercase tracking-wider flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    Conversation Log ({conversations.length} tests)
                </h3>
            </div>

            {/* Table */}
            <div className="overflow-x-auto">
                <table className="w-full">
                    <thead className="bg-slate-800/50">
                        <tr>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-10">#</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-24">Category</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">User Question</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Bot Response</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-16">Turns</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-16">Intent</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-16">Flow</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-20">Quality</th>
                            <th className="px-3 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider w-24">Status</th>
                            <th className="px-3 py-3 w-10"></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-700/30">
                        {conversations.map((conv, index) => (
                            <>
                                <tr
                                    key={conv.id}
                                    className="hover:bg-slate-800/30 transition-colors cursor-pointer"
                                    onClick={() => toggleRow(conv.id)}
                                >
                                    <td className="px-3 py-3 text-sm text-slate-500 font-mono">{index + 1}</td>
                                    <td className="px-3 py-3">
                                        <span className="text-xs px-2 py-1 rounded-full bg-slate-700/50 text-slate-300 capitalize">
                                            {conv.category?.replace('_', ' ') || 'unknown'}
                                        </span>
                                    </td>
                                    <td className="px-3 py-3">
                                        <div className="flex items-start gap-2 max-w-xs">
                                            <MessageSquare className="w-4 h-4 text-purple-400 mt-0.5 shrink-0" />
                                            <span className="text-sm text-slate-300 truncate">{conv.utterance}</span>
                                        </div>
                                    </td>
                                    <td className="px-3 py-3">
                                        <div className="flex items-start gap-2 max-w-sm">
                                            <Bot className="w-4 h-4 text-emerald-400 mt-0.5 shrink-0" />
                                            <span className="text-sm text-slate-400 truncate">
                                                {conv.bot_response || <span className="italic text-slate-500">No response</span>}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-3 py-3">
                                        <span className="text-sm font-mono tabular-nums text-slate-300">
                                            {conv.turns || 1}
                                        </span>
                                    </td>
                                    <td className="px-3 py-3">
                                        {conv.intent_identified ? (
                                            <CheckCircle className="w-4 h-4 text-emerald-400" />
                                        ) : (
                                            <XCircle className="w-4 h-4 text-red-400" />
                                        )}
                                    </td>
                                    <td className="px-3 py-3">
                                        {conv.flow_completed ? (
                                            <CheckCircle className="w-4 h-4 text-emerald-400" />
                                        ) : (
                                            <XCircle className="w-4 h-4 text-red-400" />
                                        )}
                                    </td>
                                    <td className="px-3 py-3">
                                        {conv.overall_score ? (
                                            <div className="flex items-center gap-1">
                                                <Star className={cn(
                                                    "w-3 h-3",
                                                    conv.overall_score >= 7 ? 'text-emerald-400' : conv.overall_score >= 5 ? 'text-amber-400' : 'text-red-400'
                                                )} />
                                                <span className={cn(
                                                    "text-sm font-mono tabular-nums",
                                                    conv.overall_score >= 7 ? 'text-emerald-400' : conv.overall_score >= 5 ? 'text-amber-400' : 'text-red-400'
                                                )}>
                                                    {conv.overall_score.toFixed(1)}
                                                </span>
                                            </div>
                                        ) : (
                                            <span className="text-sm text-slate-500">-</span>
                                        )}
                                    </td>
                                    <td className="px-3 py-3">
                                        <StatusBadge status={conv.status} />
                                    </td>
                                    <td className="px-3 py-3">
                                        {expandedRows.has(conv.id) ? (
                                            <ChevronUp className="w-4 h-4 text-slate-400" />
                                        ) : (
                                            <ChevronDown className="w-4 h-4 text-slate-400" />
                                        )}
                                    </td>
                                </tr>

                                {/* Expanded Details Row */}
                                {expandedRows.has(conv.id) && (
                                    <tr key={`${conv.id}-details`} className="bg-slate-800/20">
                                        <td colSpan={8} className="px-6 py-4">
                                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                                {/* Full Response */}
                                                <div className="space-y-2">
                                                    <h4 className="text-xs font-medium text-slate-400 uppercase">Full Bot Response</h4>
                                                    <p className="text-sm text-slate-300 bg-slate-900/50 p-3 rounded-lg">
                                                        {conv.bot_response || 'No response received'}
                                                    </p>
                                                </div>

                                                {/* LLM Evaluation */}
                                                <div className="space-y-2">
                                                    <h4 className="text-xs font-medium text-slate-400 uppercase">LLM Evaluation</h4>
                                                    <div className="bg-slate-900/50 p-3 rounded-lg space-y-2">
                                                        <div className="grid grid-cols-2 gap-2 text-sm">
                                                            <div className="flex justify-between">
                                                                <span className="text-slate-500">Relevance:</span>
                                                                <span className={cn(
                                                                    conv.relevance_score && conv.relevance_score >= 7 ? 'text-emerald-400' : 'text-slate-300'
                                                                )}>{conv.relevance_score?.toFixed(1) ?? '-'}</span>
                                                            </div>
                                                            <div className="flex justify-between">
                                                                <span className="text-slate-500">Helpfulness:</span>
                                                                <span className={cn(
                                                                    conv.helpfulness_score && conv.helpfulness_score >= 7 ? 'text-emerald-400' : 'text-slate-300'
                                                                )}>{conv.helpfulness_score?.toFixed(1) ?? '-'}</span>
                                                            </div>
                                                            <div className="flex justify-between">
                                                                <span className="text-slate-500">Clarity:</span>
                                                                <span className={cn(
                                                                    conv.clarity_score && conv.clarity_score >= 7 ? 'text-emerald-400' : 'text-slate-300'
                                                                )}>{conv.clarity_score?.toFixed(1) ?? '-'}</span>
                                                            </div>
                                                            <div className="flex justify-between">
                                                                <span className="text-slate-500">Accuracy:</span>
                                                                <span className={cn(
                                                                    conv.accuracy_score && conv.accuracy_score >= 7 ? 'text-emerald-400' : 'text-slate-300'
                                                                )}>{conv.accuracy_score?.toFixed(1) ?? '-'}</span>
                                                            </div>
                                                        </div>
                                                        {conv.llm_feedback && (
                                                            <div className="pt-2 border-t border-slate-700/50">
                                                                <span className="text-slate-500 text-xs">Suggestion: </span>
                                                                <span className="text-slate-300 text-sm">{conv.llm_feedback}</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                )}
                            </>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function StatusBadge({ status }: { status: string }) {
    switch (status) {
        case 'pass':
            return (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <CheckCircle className="w-3 h-3" />
                    Pass
                </span>
            );
        case 'fail':
            return (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                    <XCircle className="w-3 h-3" />
                    Failed
                </span>
            );
        case 'error':
            return (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                    <XCircle className="w-3 h-3" />
                    Error
                </span>
            );
        default:
            return (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">
                    <Clock className="w-3 h-3" />
                    Pending
                </span>
            );
    }
}
