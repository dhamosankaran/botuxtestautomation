/* Export Buttons Component - Download CSV and Markdown reports */
import { useState } from 'react';

interface ExportButtonsProps {
    testRunId: number | undefined;
}

export function ExportButtons({ testRunId }: ExportButtonsProps) {
    const [isDownloading, setIsDownloading] = useState<string | null>(null);

    const handleDownload = async (format: 'csv' | 'markdown') => {
        if (!testRunId) return;

        setIsDownloading(format);

        try {
            const endpoint = format === 'csv'
                ? `/api/reports/csv/${testRunId}`
                : `/api/reports/markdown/${testRunId}`;

            const response = await fetch(`http://localhost:8000${endpoint}`);

            if (!response.ok) {
                throw new Error('Download failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = format === 'csv'
                ? `test_run_${testRunId}.csv`
                : `test_run_${testRunId}_report.md`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download report');
        } finally {
            setIsDownloading(null);
        }
    };

    if (!testRunId) return null;

    return (
        <div className="flex gap-2">
            <button
                onClick={() => handleDownload('csv')}
                disabled={isDownloading !== null}
                className="flex items-center gap-2 px-3 py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 rounded-lg text-emerald-400 text-sm transition-all disabled:opacity-50"
            >
                {isDownloading === 'csv' ? (
                    <span className="animate-spin">⏳</span>
                ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                )}
                CSV
            </button>

            <button
                onClick={() => handleDownload('markdown')}
                disabled={isDownloading !== null}
                className="flex items-center gap-2 px-3 py-1.5 bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/30 rounded-lg text-purple-400 text-sm transition-all disabled:opacity-50"
            >
                {isDownloading === 'markdown' ? (
                    <span className="animate-spin">⏳</span>
                ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                )}
                Report
            </button>
        </div>
    );
}
