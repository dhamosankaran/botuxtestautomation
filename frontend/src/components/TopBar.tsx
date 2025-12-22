/* TopBar component - App header with status indicator */
import { useHealthCheck } from '../hooks/useTestResults';
import { Bot, Wifi, WifiOff } from 'lucide-react';

interface TopBarProps {
    testStatus: 'idle' | 'running' | 'completed' | 'failed';
}

export function TopBar({ testStatus }: TopBarProps) {
    const { data: health } = useHealthCheck();
    const isConnected = health?.status === 'healthy';

    return (
        <header className="h-16 bg-gradient-to-r from-slate-900 via-purple-900 to-slate-900 border-b border-purple-500/20 flex items-center justify-between px-6 shadow-lg">
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/30">
                    <Bot className="w-6 h-6 text-white" />
                </div>
                <div>
                    <h1 className="text-xl font-bold text-white tracking-tight">Chatbot QA Pilot</h1>
                    <p className="text-xs text-purple-300/70">Automated Testing Platform</p>
                </div>
            </div>

            <div className="flex items-center gap-4">
                {/* Test Status Badge */}
                <div className={`px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-2 ${testStatus === 'running'
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                        : testStatus === 'completed'
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : testStatus === 'failed'
                                ? 'bg-red-500/20 text-red-300 border border-red-500/30'
                                : 'bg-slate-700/50 text-slate-400 border border-slate-600/30'
                    }`}>
                    {testStatus === 'running' && (
                        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                    )}
                    {testStatus === 'completed' && (
                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    )}
                    {testStatus === 'failed' && (
                        <span className="w-2 h-2 rounded-full bg-red-400" />
                    )}
                    {testStatus === 'idle' && (
                        <span className="w-2 h-2 rounded-full bg-slate-500" />
                    )}
                    <span className="capitalize">{testStatus}</span>
                </div>

                {/* Connection Status */}
                <div className={`flex items-center gap-2 text-xs ${isConnected ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                    {isConnected ? (
                        <Wifi className="w-4 h-4" />
                    ) : (
                        <WifiOff className="w-4 h-4" />
                    )}
                    <span>{isConnected ? 'API Connected' : 'Disconnected'}</span>
                </div>
            </div>
        </header>
    );
}
