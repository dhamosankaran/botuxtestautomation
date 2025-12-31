/* TutorialsPanel component - Educational content with expandable sections */
import { useState } from 'react';
import {
    BookOpen,
    ChevronDown,
    ChevronRight,
    Layers,
    Cpu,
    Database,
    Terminal,
    Puzzle,
    Copy,
    Check
} from 'lucide-react';
import { cn } from '../lib/utils';

interface TutorialSection {
    id: string;
    title: string;
    icon: React.ElementType;
    content: React.ReactNode;
}

function CodeBlock({ code }: { code: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="relative group">
            <pre className="bg-slate-950 border border-slate-700/50 rounded-lg p-4 overflow-x-auto">
                <code className="text-sm text-slate-300 font-mono">{code}</code>
            </pre>
            <button
                onClick={handleCopy}
                className="absolute top-2 right-2 p-2 bg-slate-800 hover:bg-slate-700 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
            >
                {copied ? (
                    <Check className="w-4 h-4 text-emerald-400" />
                ) : (
                    <Copy className="w-4 h-4 text-slate-400" />
                )}
            </button>
        </div>
    );
}

const TUTORIAL_SECTIONS: TutorialSection[] = [
    {
        id: 'architecture',
        title: 'App Architecture',
        icon: Layers,
        content: (
            <div className="space-y-4 text-slate-300">
                <p>
                    This Chatbot QA Automation platform is built with a modern, decoupled architecture:
                </p>

                <div className="grid grid-cols-2 gap-4">
                    <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <h4 className="font-semibold text-purple-400 mb-2">🎨 Frontend</h4>
                        <ul className="text-sm space-y-1 text-slate-400">
                            <li>• React 18 + TypeScript</li>
                            <li>• Vite for fast HMR</li>
                            <li>• TanStack Query for data fetching</li>
                            <li>• Tailwind CSS styling</li>
                        </ul>
                    </div>
                    <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <h4 className="font-semibold text-cyan-400 mb-2">⚙️ Backend</h4>
                        <ul className="text-sm space-y-1 text-slate-400">
                            <li>• FastAPI (Python 3.11+)</li>
                            <li>• Playwright for automation</li>
                            <li>• SQLite for results storage</li>
                            <li>• Gemini LLM for evaluation</li>
                        </ul>
                    </div>
                </div>

                <h4 className="font-semibold text-white mt-6">Data Flow</h4>
                <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700/30 font-mono text-sm">
                    <div className="flex items-center gap-2 flex-wrap">
                        <span className="px-2 py-1 bg-purple-600/30 rounded text-purple-300">Frontend</span>
                        <span className="text-slate-500">→</span>
                        <span className="px-2 py-1 bg-cyan-600/30 rounded text-cyan-300">FastAPI</span>
                        <span className="text-slate-500">→</span>
                        <span className="px-2 py-1 bg-emerald-600/30 rounded text-emerald-300">Playwright</span>
                        <span className="text-slate-500">→</span>
                        <span className="px-2 py-1 bg-orange-600/30 rounded text-orange-300">Chatbot</span>
                    </div>
                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                        <span className="px-2 py-1 bg-orange-600/30 rounded text-orange-300">Response</span>
                        <span className="text-slate-500">→</span>
                        <span className="px-2 py-1 bg-pink-600/30 rounded text-pink-300">Gemini LLM</span>
                        <span className="text-slate-500">→</span>
                        <span className="px-2 py-1 bg-blue-600/30 rounded text-blue-300">SQLite DB</span>
                        <span className="text-slate-500">→</span>
                        <span className="px-2 py-1 bg-purple-600/30 rounded text-purple-300">Dashboard</span>
                    </div>
                </div>
            </div>
        )
    },
    {
        id: 'mcp',
        title: 'Chrome DevTools MCP',
        icon: Puzzle,
        content: (
            <div className="space-y-4 text-slate-300">
                <p>
                    <strong className="text-white">Model Context Protocol (MCP)</strong> enables AI assistants to connect to Chrome DevTools for advanced debugging.
                </p>

                <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                    <h4 className="font-semibold text-amber-400 mb-2">📋 Prerequisites</h4>
                    <ul className="text-sm space-y-1 text-slate-400">
                        <li>✅ Node.js v20.19 or newer</li>
                        <li>✅ npm (comes with Node.js)</li>
                        <li>✅ Chrome browser installed</li>
                    </ul>
                </div>

                <h4 className="font-semibold text-white">Step 1: Configure MCP</h4>
                <p className="text-sm text-slate-400">Add Chrome DevTools to your MCP config file:</p>
                <CodeBlock
                    code={`// ~/.gemini/antigravity/mcp_config.json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-chrome-devtools"]
    }
  }
}`}
                />

                <h4 className="font-semibold text-white">Step 2: Restart IDE</h4>
                <p className="text-sm text-slate-400">
                    After saving the config, restart your IDE/Gemini extension to load the MCP server.
                </p>

                <h4 className="font-semibold text-white mt-4">What MCP Enables</h4>
                <div className="grid grid-cols-2 gap-2 text-sm">
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        🔍 DOM Inspection
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        🎨 CSS Debugging
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        💻 JS Execution
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        🌐 Network Monitoring
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        📊 Performance Traces
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        📸 Screenshots
                    </div>
                </div>
            </div>
        )
    },
    {
        id: 'playwright',
        title: 'Playwright Automation',
        icon: Terminal,
        content: (
            <div className="space-y-4 text-slate-300">
                <p>
                    <strong className="text-white">Playwright</strong> powers our browser automation for chatbot testing.
                </p>

                <h4 className="font-semibold text-white">How Testing Works</h4>
                <ol className="list-decimal list-inside space-y-2 text-sm text-slate-400">
                    <li>Navigate to target URL and wait for chatbot widget</li>
                    <li>Open chat widget using configured selector</li>
                    <li>For each utterance: type message, send, wait for response</li>
                    <li>Capture bot response and any error states</li>
                    <li>Send to LLM for quality evaluation</li>
                    <li>Store results in SQLite database</li>
                </ol>

                <h4 className="font-semibold text-white mt-4">Key Configuration</h4>
                <CodeBlock
                    code={`# Backend .env configuration
PLAYWRIGHT_HEADLESS=true    # Run without visible browser
PLAYWRIGHT_SLOW_MO=100      # Delay between actions (ms)
PLAYWRIGHT_TIMEOUT=30000    # Max wait time for elements`}
                />

                <h4 className="font-semibold text-white mt-4">CSS Selectors</h4>
                <p className="text-sm text-slate-400">
                    Configure selectors in the left panel to match your chatbot's HTML structure:
                </p>
                <ul className="text-sm space-y-1 text-slate-400 mt-2">
                    <li><code className="text-purple-400">widget_selector</code> - Chat widget container</li>
                    <li><code className="text-purple-400">input_selector</code> - Message input field</li>
                    <li><code className="text-purple-400">send_selector</code> - Send button</li>
                    <li><code className="text-purple-400">response_selector</code> - Bot message elements</li>
                </ul>
            </div>
        )
    },
    {
        id: 'llm',
        title: 'LLM Evaluation',
        icon: Cpu,
        content: (
            <div className="space-y-4 text-slate-300">
                <p>
                    <strong className="text-white">Gemini LLM</strong> evaluates chatbot responses for quality and correctness.
                </p>

                <h4 className="font-semibold text-white">Evaluation Criteria</h4>
                <div className="space-y-2">
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <span className="font-medium text-emerald-400">✓ Relevance</span>
                        <p className="text-xs text-slate-500 mt-1">Does the response address the user's question?</p>
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <span className="font-medium text-emerald-400">✓ Accuracy</span>
                        <p className="text-xs text-slate-500 mt-1">Is the information factually correct?</p>
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <span className="font-medium text-emerald-400">✓ Completeness</span>
                        <p className="text-xs text-slate-500 mt-1">Does it fully answer the question?</p>
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <span className="font-medium text-emerald-400">✓ Tone</span>
                        <p className="text-xs text-slate-500 mt-1">Is the response professional and helpful?</p>
                    </div>
                </div>

                <h4 className="font-semibold text-white mt-4">Configuration</h4>
                <CodeBlock
                    code={`# Set your Gemini API key in .env
GOOGLE_API_KEY=your-api-key-here

# Optional LLM settings
LLM_MODEL_NAME=gemini-1.5-flash
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=2048`}
                />
            </div>
        )
    },
    {
        id: 'database',
        title: 'Database Schema',
        icon: Database,
        content: (
            <div className="space-y-4 text-slate-300">
                <p>
                    Test results are stored in <strong className="text-white">SQLite</strong> for persistence and analytics.
                </p>

                <h4 className="font-semibold text-white">Tables</h4>
                <div className="space-y-3">
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <code className="text-purple-400 font-mono">test_runs</code>
                        <p className="text-xs text-slate-500 mt-1">
                            Stores test execution metadata: ID, timestamp, status, target URL
                        </p>
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <code className="text-purple-400 font-mono">conversation_logs</code>
                        <p className="text-xs text-slate-500 mt-1">
                            Individual utterance results: question, response, LLM score, pass/fail
                        </p>
                    </div>
                    <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/30">
                        <code className="text-purple-400 font-mono">journey_results</code>
                        <p className="text-xs text-slate-500 mt-1">
                            Multi-turn journey test results with step-by-step logs
                        </p>
                    </div>
                </div>

                <h4 className="font-semibold text-white mt-4">Database Location</h4>
                <CodeBlock
                    code={`# Default location
backend/results.db

# View with sqlite3
sqlite3 backend/results.db
.tables
SELECT * FROM test_runs ORDER BY created_at DESC LIMIT 5;`}
                />
            </div>
        )
    }
];

export function TutorialsPanel() {
    const [expandedSections, setExpandedSections] = useState<string[]>(['architecture']);

    const toggleSection = (id: string) => {
        setExpandedSections(prev =>
            prev.includes(id)
                ? prev.filter(s => s !== id)
                : [...prev, id]
        );
    };

    const expandAll = () => {
        setExpandedSections(TUTORIAL_SECTIONS.map(s => s.id));
    };

    const collapseAll = () => {
        setExpandedSections([]);
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-xl">
                            <BookOpen className="w-6 h-6 text-white" />
                        </div>
                        Tutorials
                    </h2>
                    <p className="text-slate-400 mt-1">Learn about the platform architecture and configuration</p>
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={expandAll}
                        className="px-3 py-1.5 bg-slate-700/50 hover:bg-slate-700 border border-slate-600/50 rounded-lg text-slate-300 text-xs font-medium transition-all"
                    >
                        Expand All
                    </button>
                    <button
                        onClick={collapseAll}
                        className="px-3 py-1.5 bg-slate-700/50 hover:bg-slate-700 border border-slate-600/50 rounded-lg text-slate-300 text-xs font-medium transition-all"
                    >
                        Collapse All
                    </button>
                </div>
            </div>

            {/* Accordion Sections */}
            <div className="space-y-3">
                {TUTORIAL_SECTIONS.map((section) => {
                    const Icon = section.icon;
                    const isExpanded = expandedSections.includes(section.id);

                    return (
                        <div
                            key={section.id}
                            className="bg-slate-800/30 rounded-xl border border-slate-700/30 overflow-hidden"
                        >
                            {/* Section Header */}
                            <button
                                onClick={() => toggleSection(section.id)}
                                className="w-full p-4 flex items-center gap-3 hover:bg-slate-800/50 transition-colors"
                            >
                                {isExpanded ? (
                                    <ChevronDown className="w-5 h-5 text-slate-400" />
                                ) : (
                                    <ChevronRight className="w-5 h-5 text-slate-400" />
                                )}
                                <div className={cn(
                                    "p-2 rounded-lg",
                                    isExpanded
                                        ? "bg-gradient-to-br from-purple-600/30 to-pink-600/30"
                                        : "bg-slate-700/50"
                                )}>
                                    <Icon className={cn(
                                        "w-5 h-5",
                                        isExpanded ? "text-purple-400" : "text-slate-400"
                                    )} />
                                </div>
                                <span className={cn(
                                    "font-semibold text-lg",
                                    isExpanded ? "text-white" : "text-slate-300"
                                )}>
                                    {section.title}
                                </span>
                            </button>

                            {/* Section Content */}
                            {isExpanded && (
                                <div className="px-6 pb-6 pt-2 border-t border-slate-700/30">
                                    {section.content}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
