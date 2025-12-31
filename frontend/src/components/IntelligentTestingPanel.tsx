/* Intelligent Testing Panel - Edge cases, dynamic generation, custom suites */
import { useState } from 'react';

interface GeneratedQuestion {
    question: string;
    category: string;
    source: string;
}

const EDGE_CASE_CATEGORIES = [
    { id: 'typos', label: '✏️ Typos', description: 'Spelling mistakes' },
    { id: 'slang_informal', label: '💬 Slang', description: 'Casual language' },
    { id: 'emoji', label: '😀 Emoji', description: 'With emojis' },
    { id: 'minimal', label: '📝 Minimal', description: 'Very short' },
    { id: 'multilingual', label: '🌍 Multilingual', description: 'Other languages' },
    { id: 'questions', label: '❓ Questions', description: 'Question format' },
    { id: 'commands', label: '📢 Commands', description: 'Direct commands' },
];

interface IntelligentTestingPanelProps {
    onAddQuestions?: (questions: string[]) => void;
}

export function IntelligentTestingPanel({ onAddQuestions }: IntelligentTestingPanelProps) {
    const [activeTab, setActiveTab] = useState<'edge' | 'generate' | 'suite'>('edge');
    const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
    const [edgeCaseQuestions, setEdgeCaseQuestions] = useState<GeneratedQuestion[]>([]);
    const [isLoading, setIsLoading] = useState(false);

    // For dynamic generation
    const [botResponse, setBotResponse] = useState('');
    const [originalQuestion, setOriginalQuestion] = useState('');
    const [generatedQuestions, setGeneratedQuestions] = useState<string[]>([]);

    const toggleCategory = (id: string) => {
        setSelectedCategories(prev =>
            prev.includes(id)
                ? prev.filter(c => c !== id)
                : [...prev, id]
        );
    };

    const fetchEdgeCases = async () => {
        setIsLoading(true);
        try {
            const params = selectedCategories.length > 0
                ? `?categories=${selectedCategories.join(',')}`
                : '';
            const response = await fetch(`http://localhost:8000/api/intelligent/edge-cases${params}`);
            if (response.ok) {
                const data = await response.json();
                setEdgeCaseQuestions(data.questions || []);
            }
        } catch (error) {
            console.error('Failed to fetch edge cases:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const generateDynamicQuestions = async () => {
        if (!botResponse.trim()) return;

        setIsLoading(true);
        try {
            const response = await fetch('http://localhost:8000/api/intelligent/generate-questions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bot_response: botResponse,
                    original_question: originalQuestion || 'General inquiry',
                    category: 'general',
                    count: 5
                })
            });

            if (response.ok) {
                const data = await response.json();
                setGeneratedQuestions(data.questions || []);
            }
        } catch (error) {
            console.error('Failed to generate questions:', error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleAddToTest = (questions: string[]) => {
        if (onAddQuestions) {
            onAddQuestions(questions);
        }
    };

    return (
        <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700/50 rounded-xl overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-3">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                    🤖 Intelligent Testing
                </h3>
                <div className="flex gap-1">
                    <button
                        onClick={() => setActiveTab('edge')}
                        className={`px-3 py-1 rounded-lg text-sm transition-all ${activeTab === 'edge'
                                ? 'bg-orange-600/30 text-orange-400'
                                : 'text-gray-400 hover:text-white'
                            }`}
                    >
                        Edge Cases
                    </button>
                    <button
                        onClick={() => setActiveTab('generate')}
                        className={`px-3 py-1 rounded-lg text-sm transition-all ${activeTab === 'generate'
                                ? 'bg-orange-600/30 text-orange-400'
                                : 'text-gray-400 hover:text-white'
                            }`}
                    >
                        Generate
                    </button>
                </div>
            </div>

            <div className="p-4">
                {/* Edge Cases Tab */}
                {activeTab === 'edge' && (
                    <div className="space-y-4">
                        <p className="text-sm text-gray-400">
                            Select edge case categories to test bot robustness
                        </p>

                        {/* Category Grid */}
                        <div className="grid grid-cols-2 gap-2">
                            {EDGE_CASE_CATEGORIES.map(cat => (
                                <button
                                    key={cat.id}
                                    onClick={() => toggleCategory(cat.id)}
                                    className={`p-2 rounded-lg border text-left transition-all ${selectedCategories.includes(cat.id)
                                            ? 'bg-orange-600/20 border-orange-500/50 text-orange-400'
                                            : 'bg-slate-900/50 border-slate-700/30 text-gray-400 hover:border-slate-600'
                                        }`}
                                >
                                    <div className="text-sm font-medium">{cat.label}</div>
                                    <div className="text-xs opacity-70">{cat.description}</div>
                                </button>
                            ))}
                        </div>

                        {/* Fetch Button */}
                        <button
                            onClick={fetchEdgeCases}
                            disabled={isLoading}
                            className="w-full py-2 bg-orange-600/20 hover:bg-orange-600/30 border border-orange-500/30 rounded-lg text-orange-400 text-sm transition-all disabled:opacity-50"
                        >
                            {isLoading ? 'Loading...' : `Load Edge Cases (${selectedCategories.length || 'all'} categories)`}
                        </button>

                        {/* Results */}
                        {edgeCaseQuestions.length > 0 && (
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-400">
                                        {edgeCaseQuestions.length} questions found
                                    </span>
                                    <button
                                        onClick={() => handleAddToTest(edgeCaseQuestions.map(q => q.question))}
                                        className="text-xs text-cyan-400 hover:text-cyan-300"
                                    >
                                        Add All to Test
                                    </button>
                                </div>
                                <div className="max-h-48 overflow-y-auto space-y-1">
                                    {edgeCaseQuestions.slice(0, 10).map((q, i) => (
                                        <div
                                            key={i}
                                            className="flex items-center justify-between p-2 bg-slate-900/50 rounded text-sm"
                                        >
                                            <span className="text-white truncate flex-1">{q.question}</span>
                                            <span className="text-xs text-gray-500 ml-2">{q.category}</span>
                                        </div>
                                    ))}
                                    {edgeCaseQuestions.length > 10 && (
                                        <div className="text-xs text-gray-500 text-center py-1">
                                            +{edgeCaseQuestions.length - 10} more...
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Generate Tab */}
                {activeTab === 'generate' && (
                    <div className="space-y-4">
                        <p className="text-sm text-gray-400">
                            Generate follow-up questions based on bot response
                        </p>

                        <div className="space-y-3">
                            <div>
                                <label className="block text-xs text-gray-500 mb-1">Original Question</label>
                                <input
                                    type="text"
                                    value={originalQuestion}
                                    onChange={(e) => setOriginalQuestion(e.target.value)}
                                    placeholder="What is my balance?"
                                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-700/50 rounded-lg text-white text-sm focus:border-orange-500/50 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs text-gray-500 mb-1">Bot Response</label>
                                <textarea
                                    value={botResponse}
                                    onChange={(e) => setBotResponse(e.target.value)}
                                    placeholder="Paste the bot's response here..."
                                    rows={3}
                                    className="w-full px-3 py-2 bg-slate-900/50 border border-slate-700/50 rounded-lg text-white text-sm focus:border-orange-500/50 focus:outline-none resize-none"
                                />
                            </div>

                            <button
                                onClick={generateDynamicQuestions}
                                disabled={isLoading || !botResponse.trim()}
                                className="w-full py-2 bg-orange-600/20 hover:bg-orange-600/30 border border-orange-500/30 rounded-lg text-orange-400 text-sm transition-all disabled:opacity-50"
                            >
                                {isLoading ? 'Generating...' : '🤖 Generate Follow-up Questions'}
                            </button>
                        </div>

                        {/* Generated Results */}
                        {generatedQuestions.length > 0 && (
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-400">
                                        Generated {generatedQuestions.length} questions
                                    </span>
                                    <button
                                        onClick={() => handleAddToTest(generatedQuestions)}
                                        className="text-xs text-cyan-400 hover:text-cyan-300"
                                    >
                                        Add All to Test
                                    </button>
                                </div>
                                <div className="space-y-1">
                                    {generatedQuestions.map((q, i) => (
                                        <div
                                            key={i}
                                            className="flex items-center justify-between p-2 bg-slate-900/50 rounded text-sm"
                                        >
                                            <span className="text-white">{q}</span>
                                            <button
                                                onClick={() => handleAddToTest([q])}
                                                className="text-xs text-cyan-400 hover:text-cyan-300 ml-2"
                                            >
                                                Add
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
