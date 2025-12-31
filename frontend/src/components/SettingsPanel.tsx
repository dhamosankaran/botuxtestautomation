/* SettingsPanel component - App configuration settings */
import { useState } from 'react';
import {
    Settings,
    Globe,
    Cpu,
    Clock,
    Eye,
    Save,
    RotateCcw,
    CheckCircle2
} from 'lucide-react';
import { cn } from '../lib/utils';

interface SettingsSection {
    id: string;
    title: string;
    icon: React.ElementType;
    description: string;
}

const SETTINGS_SECTIONS: SettingsSection[] = [
    {
        id: 'backend',
        title: 'Backend Configuration',
        icon: Globe,
        description: 'API endpoint and connection settings'
    },
    {
        id: 'playwright',
        title: 'Playwright Settings',
        icon: Eye,
        description: 'Browser automation configuration'
    },
    {
        id: 'llm',
        title: 'LLM Configuration',
        icon: Cpu,
        description: 'AI model settings for evaluation'
    }
];

export function SettingsPanel() {
    const [activeSection, setActiveSection] = useState('backend');
    const [saved, setSaved] = useState(false);

    // Settings state
    const [settings, setSettings] = useState({
        backendUrl: 'http://localhost:8000',
        playwrightHeadless: true,
        playwrightSlowMo: 100,
        playwrightTimeout: 30000,
        llmModel: 'gemini-1.5-flash',
        llmTemperature: 0.3,
        llmMaxTokens: 2048
    });

    const handleSave = () => {
        // In a real app, this would save to backend/localStorage
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleReset = () => {
        setSettings({
            backendUrl: 'http://localhost:8000',
            playwrightHeadless: true,
            playwrightSlowMo: 100,
            playwrightTimeout: 30000,
            llmModel: 'gemini-1.5-flash',
            llmTemperature: 0.3,
            llmMaxTokens: 2048
        });
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                        <div className="p-2 bg-gradient-to-br from-slate-600 to-slate-700 rounded-xl">
                            <Settings className="w-6 h-6 text-slate-300" />
                        </div>
                        Settings
                    </h2>
                    <p className="text-slate-400 mt-1">Configure application behavior and preferences</p>
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={handleReset}
                        className="px-4 py-2 bg-slate-700/50 hover:bg-slate-700 border border-slate-600/50 rounded-lg text-slate-300 text-sm font-medium transition-all flex items-center gap-2"
                    >
                        <RotateCcw className="w-4 h-4" />
                        Reset
                    </button>
                    <button
                        onClick={handleSave}
                        className={cn(
                            "px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2",
                            saved
                                ? "bg-emerald-600/30 text-emerald-400 border border-emerald-500/30"
                                : "bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white"
                        )}
                    >
                        {saved ? (
                            <>
                                <CheckCircle2 className="w-4 h-4" />
                                Saved!
                            </>
                        ) : (
                            <>
                                <Save className="w-4 h-4" />
                                Save Changes
                            </>
                        )}
                    </button>
                </div>
            </div>

            <div className="flex gap-6">
                {/* Sidebar Navigation */}
                <div className="w-64 space-y-2">
                    {SETTINGS_SECTIONS.map((section) => {
                        const Icon = section.icon;
                        const isActive = activeSection === section.id;

                        return (
                            <button
                                key={section.id}
                                onClick={() => setActiveSection(section.id)}
                                className={cn(
                                    "w-full p-3 rounded-xl text-left transition-all",
                                    isActive
                                        ? "bg-gradient-to-r from-purple-600/20 to-pink-600/20 border border-purple-500/30"
                                        : "bg-slate-800/30 border border-slate-700/30 hover:bg-slate-800/50"
                                )}
                            >
                                <div className="flex items-center gap-3">
                                    <Icon className={cn(
                                        "w-5 h-5",
                                        isActive ? "text-purple-400" : "text-slate-400"
                                    )} />
                                    <div>
                                        <div className={cn(
                                            "font-medium",
                                            isActive ? "text-white" : "text-slate-300"
                                        )}>
                                            {section.title}
                                        </div>
                                        <div className="text-xs text-slate-500">{section.description}</div>
                                    </div>
                                </div>
                            </button>
                        );
                    })}
                </div>

                {/* Settings Content */}
                <div className="flex-1 bg-slate-800/30 rounded-xl border border-slate-700/30 p-6">
                    {/* Backend Configuration */}
                    {activeSection === 'backend' && (
                        <div className="space-y-6">
                            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                                <Globe className="w-5 h-5 text-purple-400" />
                                Backend Configuration
                            </h3>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                        API Base URL
                                    </label>
                                    <input
                                        type="url"
                                        value={settings.backendUrl}
                                        onChange={(e) => setSettings(s => ({ ...s, backendUrl: e.target.value }))}
                                        className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600/50 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 transition-all"
                                        placeholder="http://localhost:8000"
                                    />
                                    <p className="text-xs text-slate-500 mt-1">
                                        The URL where your FastAPI backend is running
                                    </p>
                                </div>

                                <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                                    <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium">
                                        <CheckCircle2 className="w-4 h-4" />
                                        Backend Status: Connected
                                    </div>
                                    <p className="text-xs text-slate-400 mt-1">
                                        LLM evaluation is enabled with Gemini 1.5 Flash
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Playwright Settings */}
                    {activeSection === 'playwright' && (
                        <div className="space-y-6">
                            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                                <Eye className="w-5 h-5 text-purple-400" />
                                Playwright Settings
                            </h3>

                            <div className="space-y-4">
                                <div className="flex items-center justify-between p-4 bg-slate-900/30 rounded-lg border border-slate-700/30">
                                    <div>
                                        <div className="font-medium text-slate-200">Headless Mode</div>
                                        <div className="text-xs text-slate-500">Run browser without visible window</div>
                                    </div>
                                    <button
                                        onClick={() => setSettings(s => ({ ...s, playwrightHeadless: !s.playwrightHeadless }))}
                                        className={cn(
                                            "w-12 h-6 rounded-full transition-colors relative",
                                            settings.playwrightHeadless ? "bg-purple-600" : "bg-slate-600"
                                        )}
                                    >
                                        <span className={cn(
                                            "absolute top-1 w-4 h-4 bg-white rounded-full transition-transform",
                                            settings.playwrightHeadless ? "translate-x-7" : "translate-x-1"
                                        )} />
                                    </button>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                        <Clock className="w-4 h-4 inline mr-2" />
                                        Slow Motion (ms)
                                    </label>
                                    <input
                                        type="number"
                                        value={settings.playwrightSlowMo}
                                        onChange={(e) => setSettings(s => ({ ...s, playwrightSlowMo: parseInt(e.target.value) || 0 }))}
                                        className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600/50 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                                        min="0"
                                        max="5000"
                                    />
                                    <p className="text-xs text-slate-500 mt-1">
                                        Delay between actions for debugging (0 = no delay)
                                    </p>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                        Timeout (ms)
                                    </label>
                                    <input
                                        type="number"
                                        value={settings.playwrightTimeout}
                                        onChange={(e) => setSettings(s => ({ ...s, playwrightTimeout: parseInt(e.target.value) || 30000 }))}
                                        className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600/50 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                                        min="5000"
                                        max="120000"
                                    />
                                    <p className="text-xs text-slate-500 mt-1">
                                        Maximum wait time for elements (default: 30000ms)
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* LLM Configuration */}
                    {activeSection === 'llm' && (
                        <div className="space-y-6">
                            <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                                <Cpu className="w-5 h-5 text-purple-400" />
                                LLM Configuration
                            </h3>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                        Model Name
                                    </label>
                                    <select
                                        value={settings.llmModel}
                                        onChange={(e) => setSettings(s => ({ ...s, llmModel: e.target.value }))}
                                        className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600/50 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                                    >
                                        <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
                                        <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                                        <option value="gemini-2.0-flash-exp">Gemini 2.0 Flash (Experimental)</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                        Temperature: {settings.llmTemperature}
                                    </label>
                                    <input
                                        type="range"
                                        value={settings.llmTemperature}
                                        onChange={(e) => setSettings(s => ({ ...s, llmTemperature: parseFloat(e.target.value) }))}
                                        className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500"
                                        min="0"
                                        max="1"
                                        step="0.1"
                                    />
                                    <div className="flex justify-between text-xs text-slate-500 mt-1">
                                        <span>Precise (0)</span>
                                        <span>Creative (1)</span>
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-slate-300 mb-2">
                                        Max Tokens
                                    </label>
                                    <input
                                        type="number"
                                        value={settings.llmMaxTokens}
                                        onChange={(e) => setSettings(s => ({ ...s, llmMaxTokens: parseInt(e.target.value) || 2048 }))}
                                        className="w-full px-4 py-3 bg-slate-900/50 border border-slate-600/50 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-purple-500/50"
                                        min="256"
                                        max="8192"
                                    />
                                    <p className="text-xs text-slate-500 mt-1">
                                        Maximum response length from the LLM
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
