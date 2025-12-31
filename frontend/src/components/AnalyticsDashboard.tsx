/* Analytics Dashboard Component - Enhanced with per-feature pass rates */
import { useState, useEffect } from 'react';
import { ArrowUpDown, TrendingUp, TrendingDown, Minus, Filter } from 'lucide-react';
import { cn } from '../lib/utils';

interface TrendData {
    period_days: number;
    current_pass_rate: number;
    previous_pass_rate: number;
    pass_rate_change: number;
    current_avg_score: number;
    previous_avg_score: number;
    score_change: number;
    trend: 'improving' | 'declining' | 'stable';
    insights: string[];
}

interface CategoryData {
    category: string;
    total_tests: number;
    pass_count: number;
    pass_rate: number;
    avg_score: number;
    common_issues: string[];
}

interface QualityStats {
    all_time: {
        total_tests: number;
        total_runs: number;
        pass_rate: number;
        avg_score: number;
        avg_latency_ms: number;
    };
    last_7_days: TrendData;
    categories: number;
}

// Category group mapping for filtering
const CATEGORY_GROUPS: Record<string, string[]> = {
    'All': [],
    'Cards': ['card_issues', 'cards_dispute', 'cards_balance_transfer', 'cards_replacement', 'cards_update_contact', 'credit_card'],
    'Account': ['account_balance', 'transactions', 'payments', 'transfers', 'account_management'],
    'Security': ['login_security', 'escalation_test'],
    'Rewards': ['rewards', 'rewards_benefits', 'travel_benefits'],
    'Other': ['statements_documents', 'fees_charges', 'loans_offers'],
};

type SortField = 'category' | 'pass_rate' | 'total_tests' | 'avg_score';
type SortDirection = 'asc' | 'desc';

export function AnalyticsDashboard() {
    const [trends, setTrends] = useState<TrendData | null>(null);
    const [categories, setCategories] = useState<CategoryData[]>([]);
    const [quality, setQuality] = useState<QualityStats | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [activeTab, setActiveTab] = useState<'overview' | 'categories'>('overview');

    // Sorting & filtering state
    const [sortField, setSortField] = useState<SortField>('pass_rate');
    const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
    const [groupFilter, setGroupFilter] = useState<string>('All');

    useEffect(() => {
        async function fetchAnalytics() {
            setIsLoading(true);
            try {
                const [trendsRes, categoriesRes, qualityRes] = await Promise.all([
                    fetch('http://localhost:8000/api/analytics/trends'),
                    fetch('http://localhost:8000/api/analytics/categories'),
                    fetch('http://localhost:8000/api/analytics/quality'),
                ]);

                if (trendsRes.ok) setTrends(await trendsRes.json());
                if (categoriesRes.ok) {
                    const data = await categoriesRes.json();
                    setCategories(data.categories || []);
                }
                if (qualityRes.ok) setQuality(await qualityRes.json());
            } catch (error) {
                console.error('Failed to fetch analytics:', error);
            } finally {
                setIsLoading(false);
            }
        }

        fetchAnalytics();
    }, []);

    const getTrendIcon = (trend: string) => {
        switch (trend) {
            case 'improving': return <TrendingUp className="w-5 h-5 text-green-400" />;
            case 'declining': return <TrendingDown className="w-5 h-5 text-red-400" />;
            default: return <Minus className="w-5 h-5 text-yellow-400" />;
        }
    };

    const getTrendColor = (change: number) => {
        if (change > 0) return 'text-green-400';
        if (change < 0) return 'text-red-400';
        return 'text-gray-400';
    };

    const getPassRateColor = (rate: number) => {
        if (rate >= 80) return 'bg-green-500';
        if (rate >= 60) return 'bg-yellow-500';
        if (rate >= 40) return 'bg-orange-500';
        return 'bg-red-500';
    };


    const handleSort = (field: SortField) => {
        if (sortField === field) {
            setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDirection(field === 'category' ? 'asc' : 'desc');
        }
    };

    const filteredAndSortedCategories = [...categories]
        .filter(cat => {
            if (groupFilter === 'All') return true;
            const groupCategories = CATEGORY_GROUPS[groupFilter];
            return groupCategories.includes(cat.category);
        })
        .sort((a, b) => {
            let comparison = 0;
            switch (sortField) {
                case 'category':
                    comparison = a.category.localeCompare(b.category);
                    break;
                case 'pass_rate':
                    comparison = a.pass_rate - b.pass_rate;
                    break;
                case 'total_tests':
                    comparison = a.total_tests - b.total_tests;
                    break;
                case 'avg_score':
                    comparison = a.avg_score - b.avg_score;
                    break;
            }
            return sortDirection === 'asc' ? comparison : -comparison;
        });

    // Summary statistics
    const lowestPassRate = categories.length > 0
        ? categories.reduce((min, cat) => cat.pass_rate < min.pass_rate ? cat : min)
        : null;
    const highestPassRate = categories.length > 0
        ? categories.reduce((max, cat) => cat.pass_rate > max.pass_rate ? cat : max)
        : null;
    const needsAttention = categories.filter(cat => cat.pass_rate < 70);

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
            {/* Header with tabs */}
            <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-3">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    📊 Analytics Dashboard
                </h3>
                <div className="flex gap-1">
                    <button
                        onClick={() => setActiveTab('overview')}
                        className={`px-3 py-1 rounded-lg text-sm transition-all ${activeTab === 'overview'
                            ? 'bg-cyan-600/30 text-cyan-400'
                            : 'text-gray-400 hover:text-white'
                            }`}
                    >
                        Overview
                    </button>
                    <button
                        onClick={() => setActiveTab('categories')}
                        className={`px-3 py-1 rounded-lg text-sm transition-all ${activeTab === 'categories'
                            ? 'bg-cyan-600/30 text-cyan-400'
                            : 'text-gray-400 hover:text-white'
                            }`}
                    >
                        Per-Feature
                    </button>
                </div>
            </div>

            <div className="p-4">
                {activeTab === 'overview' && trends && (
                    <div className="space-y-4">
                        {/* Trend Summary */}
                        <div className="grid grid-cols-3 gap-4">
                            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
                                <div className="text-sm text-gray-400 mb-1">7-Day Trend</div>
                                <div className="flex items-center gap-2">
                                    {getTrendIcon(trends.trend)}
                                    <span className="text-xl font-bold capitalize">{trends.trend}</span>
                                </div>
                            </div>

                            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
                                <div className="text-sm text-gray-400 mb-1">Pass Rate Change</div>
                                <div className={`text-xl font-bold ${getTrendColor(trends.pass_rate_change)}`}>
                                    {trends.pass_rate_change > 0 ? '+' : ''}{trends.pass_rate_change}%
                                </div>
                                <div className="text-xs text-gray-500">
                                    {trends.previous_pass_rate}% → {trends.current_pass_rate}%
                                </div>
                            </div>

                            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
                                <div className="text-sm text-gray-400 mb-1">Avg Score Change</div>
                                <div className={`text-xl font-bold ${getTrendColor(trends.score_change)}`}>
                                    {trends.score_change > 0 ? '+' : ''}{trends.score_change.toFixed(2)}
                                </div>
                                <div className="text-xs text-gray-500">
                                    {trends.previous_avg_score.toFixed(1)} → {trends.current_avg_score.toFixed(1)}
                                </div>
                            </div>
                        </div>

                        {/* Insights */}
                        {trends.insights.length > 0 && (
                            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
                                <div className="text-sm text-gray-400 mb-2">Insights</div>
                                <ul className="space-y-1">
                                    {trends.insights.map((insight, i) => (
                                        <li key={i} className="text-sm text-white flex items-start gap-2">
                                            <span className="text-cyan-400">•</span>
                                            {insight}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {/* All-time stats */}
                        {quality && (
                            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30">
                                <div className="text-sm text-gray-400 mb-2">All-Time Statistics</div>
                                <div className="grid grid-cols-4 gap-4 text-center">
                                    <div>
                                        <div className="text-2xl font-bold text-white">{quality.all_time.total_tests}</div>
                                        <div className="text-xs text-gray-500">Total Tests</div>
                                    </div>
                                    <div>
                                        <div className="text-2xl font-bold text-white">{quality.all_time.total_runs}</div>
                                        <div className="text-xs text-gray-500">Test Runs</div>
                                    </div>
                                    <div>
                                        <div className="text-2xl font-bold text-green-400">{quality.all_time.pass_rate}%</div>
                                        <div className="text-xs text-gray-500">Pass Rate</div>
                                    </div>
                                    <div>
                                        <div className="text-2xl font-bold text-cyan-400">{quality.all_time.avg_score.toFixed(1)}</div>
                                        <div className="text-xs text-gray-500">Avg Score</div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {activeTab === 'categories' && (
                    <div className="space-y-4">
                        {/* Summary Cards */}
                        {categories.length > 0 && (
                            <div className="grid grid-cols-3 gap-3">
                                {highestPassRate && (
                                    <div className="bg-slate-900/50 rounded-lg p-3 border border-green-500/30">
                                        <div className="text-xs text-gray-400 mb-1">🏆 Best Performing</div>
                                        <div className="text-sm font-medium text-white capitalize truncate">
                                            {highestPassRate.category.replace(/_/g, ' ')}
                                        </div>
                                        <div className="text-lg font-bold text-green-400">{highestPassRate.pass_rate}%</div>
                                    </div>
                                )}
                                {lowestPassRate && (
                                    <div className="bg-slate-900/50 rounded-lg p-3 border border-red-500/30">
                                        <div className="text-xs text-gray-400 mb-1">⚠️ Needs Improvement</div>
                                        <div className="text-sm font-medium text-white capitalize truncate">
                                            {lowestPassRate.category.replace(/_/g, ' ')}
                                        </div>
                                        <div className="text-lg font-bold text-red-400">{lowestPassRate.pass_rate}%</div>
                                    </div>
                                )}
                                <div className="bg-slate-900/50 rounded-lg p-3 border border-orange-500/30">
                                    <div className="text-xs text-gray-400 mb-1">🔔 Attention Needed</div>
                                    <div className="text-lg font-bold text-orange-400">{needsAttention.length} features</div>
                                    <div className="text-xs text-gray-500">&lt; 70% pass rate</div>
                                </div>
                            </div>
                        )}

                        {/* Filters and Sorting Controls */}
                        <div className="flex items-center justify-between gap-4">
                            <div className="flex items-center gap-2">
                                <Filter className="w-4 h-4 text-gray-400" />
                                <select
                                    value={groupFilter}
                                    onChange={(e) => setGroupFilter(e.target.value)}
                                    className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-purple-500"
                                >
                                    {Object.keys(CATEGORY_GROUPS).map(group => (
                                        <option key={group} value={group}>{group}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex items-center gap-1 text-xs text-gray-400">
                                <span>Sort by:</span>
                                {(['pass_rate', 'total_tests', 'avg_score'] as SortField[]).map(field => (
                                    <button
                                        key={field}
                                        onClick={() => handleSort(field)}
                                        className={cn(
                                            "px-2 py-1 rounded transition-colors flex items-center gap-1",
                                            sortField === field
                                                ? "bg-purple-600/30 text-purple-300"
                                                : "hover:bg-slate-700"
                                        )}
                                    >
                                        {field === 'pass_rate' ? 'Pass Rate' : field === 'total_tests' ? 'Tests' : 'Score'}
                                        {sortField === field && (
                                            <ArrowUpDown className="w-3 h-3" />
                                        )}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Category List */}
                        <div className="space-y-2">
                            {filteredAndSortedCategories.length === 0 ? (
                                <div className="text-center text-gray-500 py-8">
                                    No category data available yet
                                </div>
                            ) : (
                                filteredAndSortedCategories.map((cat) => (
                                    <div
                                        key={cat.category}
                                        className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/30 hover:border-slate-600/50 transition-colors"
                                    >
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="font-medium text-white capitalize">
                                                {cat.category.replace(/_/g, ' ')}
                                            </span>
                                            <div className="flex items-center gap-3">
                                                <span className="text-xs text-gray-500">{cat.total_tests} tests</span>
                                                <span className="text-xs text-gray-500">Score: {cat.avg_score.toFixed(1)}</span>
                                                <span className={cn(
                                                    "text-sm font-bold px-2 py-0.5 rounded",
                                                    cat.pass_rate >= 80 ? 'bg-green-500/20 text-green-400' :
                                                        cat.pass_rate >= 60 ? 'bg-yellow-500/20 text-yellow-400' :
                                                            cat.pass_rate >= 40 ? 'bg-orange-500/20 text-orange-400' :
                                                                'bg-red-500/20 text-red-400'
                                                )}>
                                                    {cat.pass_rate}%
                                                </span>
                                            </div>
                                        </div>

                                        {/* Progress bar with gradient */}
                                        <div className="h-2.5 bg-slate-700 rounded-full overflow-hidden">
                                            <div
                                                className={cn(
                                                    "h-full rounded-full transition-all duration-500",
                                                    getPassRateColor(cat.pass_rate)
                                                )}
                                                style={{ width: `${cat.pass_rate}%` }}
                                            />
                                        </div>

                                        {/* Pass/Fail breakdown */}
                                        <div className="mt-2 flex items-center gap-4 text-xs">
                                            <span className="text-green-400">✓ {cat.pass_count} passed</span>
                                            <span className="text-red-400">✗ {cat.total_tests - cat.pass_count} failed</span>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
