import React from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown, Clock, Layers } from 'lucide-react';

interface StrategyProps {
    strategy: {
        id: string;
        name: string;
        balance: number;
        equity: number;
        pnl: number;
        roi: number;
        active_ops: number;
        total_ops: number;
        paused: boolean;
    };
    onAction: (id: string, action: string) => void;
}

export const StrategyCard: React.FC<StrategyProps> = ({ strategy, onAction }) => {
    const isProfit = strategy.pnl >= 0;

    return (
        <motion.div
            whileHover={{ y: -5 }}
            className="glass p-6 rounded-3xl border-white/5 flex flex-col gap-6 relative overflow-hidden group"
        >
            <div className="flex items-start justify-between">
                <div>
                    <h3 className="text-lg font-bold tracking-tight uppercase group-hover:text-accent transition-colors">
                        {strategy.name}
                    </h3>
                    <div className="flex items-center gap-2 mt-1">
                        <div className={`w-1.5 h-1.5 rounded-full ${strategy.paused ? 'bg-orange-500' : 'bg-green-500'}`} />
                        <span className="text-[10px] text-white/40 uppercase tracking-widest">
                            {strategy.paused ? 'Pausado' : 'Ejecutando'}
                        </span>
                    </div>
                </div>

                <div className="text-right">
                    <p className={`text-xl font-mono font-bold ${isProfit ? 'text-green-500' : 'text-red-500'}`}>
                        {isProfit ? '+' : ''}{strategy.pnl.toFixed(2)} €
                    </p>
                    <p className="text-[10px] text-white/40 uppercase tracking-widest">{strategy.roi.toFixed(1)}% ROI</p>
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="bg-white/5 p-4 rounded-2xl">
                    <div className="flex items-center gap-2 mb-1 text-white/30">
                        <Layers className="w-3 h-3" />
                        <span className="text-[9px] uppercase tracking-wider font-bold">Operativas</span>
                    </div>
                    <p className="text-lg font-mono font-bold">{strategy.active_ops}</p>
                </div>
                <div className="bg-white/5 p-4 rounded-xl">
                    <div className="flex items-center gap-2 mb-1 text-white/30">
                        <Clock className="w-3 h-3" />
                        <span className="text-[9px] uppercase tracking-wider font-bold">Total Ops</span>
                    </div>
                    <p className="text-lg font-mono font-bold">{strategy.total_ops}</p>
                </div>
            </div>

            <div className="flex items-center gap-3 mt-2">
                <button
                    onClick={() => onAction(strategy.id, strategy.paused ? 'resume' : 'pause')}
                    className={`flex-1 py-3 rounded-xl font-bold uppercase tracking-widest text-[10px] transition-all ${strategy.paused
                            ? 'bg-accent/10 text-accent border border-accent/30 hover:bg-accent/20'
                            : 'bg-white/5 text-white/60 border border-white/10 hover:bg-white/10'
                        }`}
                >
                    {strategy.paused ? 'Reanudar' : 'Pausar'}
                </button>
            </div>

            {/* Decorative Glow */}
            <div className={`absolute top-0 right-0 w-32 h-32 blur-[80px] -mr-16 -mt-16 transition-opacity duration-500 opacity-20 ${isProfit ? 'bg-green-500' : 'bg-red-500'}`} />
        </motion.div>
    );
};
