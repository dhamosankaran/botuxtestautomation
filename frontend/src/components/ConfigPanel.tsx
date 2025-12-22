/* ConfigPanel component - Left sidebar with test configuration */
import { useState } from 'react';
import { Play, ChevronDown, ChevronUp, Settings, Globe, User, Lock, MessageSquare, Library, Brain } from 'lucide-react';
import { cn } from '../lib/utils';
import { useUtteranceLibrary, useHealthCheck } from '../hooks/useTestResults';
import type { StartTestRequest, ChatbotConfig } from '../types';

interface ConfigPanelProps {
    onStartTest: (request: StartTestRequest) => void;
    isRunning: boolean;
}

export function ConfigPanel({ onStartTest, isRunning }: ConfigPanelProps) {
    const [targetUrl, setTargetUrl] = useState('https://www.citi.com');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [utterances, setUtterances] = useState('');
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [useLibrary, setUseLibrary] = useState(false);
    const [selectedCategories, setSelectedCategories] = useState<string[]>([]);

    const { data: library } = useUtteranceLibrary();
    const { data: health } = useHealthCheck();

    const [chatbotConfig, setChatbotConfig] = useState<ChatbotConfig>({
        widget_selector: "[class*='chat']",
        input_selector: "input[placeholder*='message'], textarea",
        send_selector: "button[type='submit']",
        response_selector: "[class*='bot-message']:last-child",
    });

    const toggleCategory = (category: string) => {
        setSelectedCategories(prev =>
            prev.includes(category)
                ? prev.filter(c => c !== category)
                : [...prev, category]
        );
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();

        const utteranceList = utterances
            .split('\n')
            .map(u => u.trim())
            .filter(u => u.length > 0);

        if (!useLibrary && utteranceList.length === 0) {
            alert('Please enter at least one test question or use the utterance library');
            return;
        }

        const request: StartTestRequest = {
            target_url: targetUrl,
            utterances: utteranceList,
            chatbot_config: chatbotConfig,
            use_library: useLibrary,
            utterance_categories: useLibrary ? selectedCategories : undefined,
        };

        if (username && password) {
            request.credentials = { username, password };
        }

        onStartTest(request);
    };

    const totalSelectedUtterances = useLibrary
        ? (selectedCategories.length > 0
            ? library?.categories.filter(c => selectedCategories.includes(c.name)).reduce((sum, c) => sum + c.count, 0) || 0
            : library?.total_utterances || 0)
        : utterances.split('\n').filter(u => u.trim()).length;

    return (
        <aside className="w-80 min-w-80 bg-slate-900/50 border-r border-slate-700/50 flex flex-col h-full">
            <div className="p-4 border-b border-slate-700/50">
                <h2 className="text-sm font-semibold text-purple-300 uppercase tracking-wider flex items-center gap-2">
                    <Settings className="w-4 h-4" />
                    Test Configuration
                </h2>
                {health?.llm_available && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-emerald-400">
                        <Brain className="w-3 h-3" />
                        LLM Evaluation Enabled
                    </div>
                )}
            </div>

            <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-4 space-y-4">
                {/* Target URL */}
                <div className="space-y-2">
                    <label className="flex items-center gap-2 text-sm font-medium text-slate-300">
                        <Globe className="w-4 h-4 text-purple-400" />
                        Target URL
                    </label>
                    <input
                        type="url"
                        value={targetUrl}
                        onChange={(e) => setTargetUrl(e.target.value)}
                        placeholder="https://www.citi.com"
                        className="w-full px-3 py-2 bg-slate-800/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                        required
                    />
                </div>

                {/* Credentials */}
                <div className="space-y-3">
                    <label className="flex items-center gap-2 text-sm font-medium text-slate-300">
                        <User className="w-4 h-4 text-purple-400" />
                        Citi Credentials
                    </label>
                    <div className="space-y-2">
                        <input
                            type="text"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            placeholder="User ID"
                            className="w-full px-3 py-2 bg-slate-800/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                        />
                        <div className="relative">
                            <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="Password"
                                className="w-full pl-10 pr-3 py-2 bg-slate-800/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                            />
                        </div>
                    </div>
                </div>

                {/* Use Library Toggle */}
                <div className="flex items-center justify-between p-3 bg-slate-800/30 rounded-lg border border-slate-700/30">
                    <div className="flex items-center gap-2">
                        <Library className="w-4 h-4 text-purple-400" />
                        <span className="text-sm text-slate-300">Use Banking Utterance Library</span>
                    </div>
                    <button
                        type="button"
                        onClick={() => setUseLibrary(!useLibrary)}
                        className={cn(
                            "w-11 h-6 rounded-full transition-colors relative",
                            useLibrary ? "bg-purple-600" : "bg-slate-600"
                        )}
                    >
                        <span className={cn(
                            "absolute top-1 w-4 h-4 bg-white rounded-full transition-transform",
                            useLibrary ? "translate-x-6" : "translate-x-1"
                        )} />
                    </button>
                </div>

                {/* Category Selection (when using library) */}
                {useLibrary && library && (
                    <div className="space-y-2">
                        <label className="text-sm font-medium text-slate-300">Select Categories ({selectedCategories.length || 'All'})</label>
                        <div className="grid grid-cols-2 gap-1.5 max-h-40 overflow-y-auto">
                            {library.categories.map(cat => (
                                <button
                                    key={cat.name}
                                    type="button"
                                    onClick={() => toggleCategory(cat.name)}
                                    className={cn(
                                        "text-left px-2 py-1.5 rounded text-xs transition-colors",
                                        selectedCategories.includes(cat.name)
                                            ? "bg-purple-600/30 text-purple-300 border border-purple-500/30"
                                            : "bg-slate-800/50 text-slate-400 border border-slate-700/30 hover:bg-slate-700/50"
                                    )}
                                >
                                    <div className="capitalize truncate">{cat.name.replace('_', ' ')}</div>
                                    <div className="text-xs opacity-60">{cat.count} Q's</div>
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Custom Test Questions (when not using library) */}
                {!useLibrary && (
                    <div className="space-y-2">
                        <label className="flex items-center gap-2 text-sm font-medium text-slate-300">
                            <MessageSquare className="w-4 h-4 text-purple-400" />
                            Test Questions
                        </label>
                        <textarea
                            value={utterances}
                            onChange={(e) => setUtterances(e.target.value)}
                            placeholder="Enter one question per line...&#10;&#10;What is my balance?&#10;How do I pay my bill?&#10;I need to speak to someone"
                            rows={5}
                            className="w-full px-3 py-2 bg-slate-800/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all resize-none font-mono text-sm"
                        />
                        <p className="text-xs text-slate-500">One question per line</p>
                    </div>
                )}

                {/* Advanced Settings Toggle */}
                <button
                    type="button"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                    className="w-full flex items-center justify-between px-3 py-2 bg-slate-800/30 border border-slate-700/50 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/50 transition-all"
                >
                    <span className="text-sm">Advanced CSS Selectors</span>
                    {showAdvanced ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>

                {/* Advanced Settings */}
                {showAdvanced && (
                    <div className="space-y-3 p-3 bg-slate-800/30 rounded-lg border border-slate-700/30">
                        <div className="space-y-1">
                            <label className="text-xs text-slate-400">Chat Widget</label>
                            <input
                                type="text"
                                value={chatbotConfig.widget_selector}
                                onChange={(e) => setChatbotConfig(prev => ({ ...prev, widget_selector: e.target.value }))}
                                className="w-full px-2 py-1.5 bg-slate-900/50 border border-slate-600/50 rounded text-sm text-white font-mono focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs text-slate-400">Input Field</label>
                            <input
                                type="text"
                                value={chatbotConfig.input_selector}
                                onChange={(e) => setChatbotConfig(prev => ({ ...prev, input_selector: e.target.value }))}
                                className="w-full px-2 py-1.5 bg-slate-900/50 border border-slate-600/50 rounded text-sm text-white font-mono focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs text-slate-400">Send Button</label>
                            <input
                                type="text"
                                value={chatbotConfig.send_selector}
                                onChange={(e) => setChatbotConfig(prev => ({ ...prev, send_selector: e.target.value }))}
                                className="w-full px-2 py-1.5 bg-slate-900/50 border border-slate-600/50 rounded text-sm text-white font-mono focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                            />
                        </div>
                        <div className="space-y-1">
                            <label className="text-xs text-slate-400">Bot Response</label>
                            <input
                                type="text"
                                value={chatbotConfig.response_selector}
                                onChange={(e) => setChatbotConfig(prev => ({ ...prev, response_selector: e.target.value }))}
                                className="w-full px-2 py-1.5 bg-slate-900/50 border border-slate-600/50 rounded text-sm text-white font-mono focus:outline-none focus:ring-1 focus:ring-purple-500/50"
                            />
                        </div>
                    </div>
                )}

                {/* Utterance Count */}
                <div className="text-center text-sm text-slate-400">
                    {totalSelectedUtterances} test question{totalSelectedUtterances !== 1 ? 's' : ''} ready
                </div>

                {/* Run Test Button */}
                <button
                    type="submit"
                    disabled={isRunning}
                    className={cn(
                        "w-full py-3 rounded-xl font-semibold text-white flex items-center justify-center gap-2 transition-all duration-300",
                        isRunning
                            ? "bg-slate-600 cursor-not-allowed"
                            : "bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50 hover:scale-[1.02]"
                    )}
                >
                    {isRunning ? (
                        <>
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            Running Test...
                        </>
                    ) : (
                        <>
                            <Play className="w-5 h-5" />
                            RUN TEST
                        </>
                    )}
                </button>
            </form>
        </aside>
    );
}
