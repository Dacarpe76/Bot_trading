import React, { useState, useEffect, useRef } from 'react';
import {
  Zap, Activity, TrendingUp, History, Clock, BarChart3,
  Terminal, LayoutDashboard, Database, ArrowUpRight,
  ArrowDownRight, Wallet, Percent, Timer,
  Play, Pause, XCircle, RefreshCw, Filter
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

// --- Types ---
interface Strategy {
  id: string;
  name: string;
  equity: number;
  balance: number;
  pnl: number;
  roi: number;
  daily_roi: number;
  avg_duration: number;
  active_ops: number;
  total_ops: number;
  paused: boolean;
  wins: number;
  losses: number;
  win_rate: number;
  start_time: number;
  active_wins: number;
  active_losses: number;
}

interface Operation {
  id: string;
  strategy_id: string;
  symbol: string;
  side: string;
  size: number;
  quantity?: number;
  entry_price: number;
  avg_price?: number;
  current_price: number;
  invested: number;
  pnl: number;
  pnl_pct: number;
  open_time: number;
  dca: number;
  avg: number;
  margin: number;
  ts_price: number;
  ts_status: string;
}

interface HistoryItem {
  id: string;
  strategy_id: string;
  symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  final_pnl: number;
  close_time: number;
  entry_time: number;
}

interface BotState {
  global_equity: number;
  strategies: Strategy[];
  operations: Operation[];
  history: HistoryItem[];
  logs: string[];
  market_trend?: string;
  market?: any[];
}

// --- Constants ---
const LEVERAGED_STRATEGIES = ['SentinelTurbo', 'SaintGrialProX3', 'VectorFlujo_V1'];

// --- Components ---

const StatCard = ({ title, value, icon: Icon, color, subValue }: any) => {
  const colorMap: any = {
    green: { bg: 'bg-green-500/20', text: 'text-green-400', border: 'border-green-500/30' },
    red: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/30' },
    blue: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/30' },
    cyan: { bg: 'bg-cyan-500/20', text: 'text-cyan-400', border: 'border-cyan-500/30' },
    yellow: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/30' }
  };

  const current = colorMap[color] || colorMap.cyan;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`glass p-5 rounded-3xl border-2 ${current.border} flex items-center gap-4 transition-colors duration-500`}
    >
      <div className={`p-3 rounded-2xl ${current.bg}`}>
        <Icon className={`w-6 h-6 ${current.text}`} />
      </div>
      <div>
        <p className="text-[10px] uppercase tracking-widest text-white/40 font-bold">{title}</p>
        <p className={`text-xl font-mono font-bold ${current.text}`}>{value}</p>
        {subValue && <p className="text-[10px] text-white/20 mt-0.5">{subValue}</p>}
      </div>
    </motion.div>
  );
};

const Sidebar = ({ activeTab, setActiveTab, role, onLogin }: any) => {
  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'operations', label: 'Operaciones', icon: TrendingUp },
    { id: 'logs', label: 'Consola', icon: Terminal },
    { id: 'history', label: 'Historial', icon: History },
  ];

  return (
    <div className="w-20 md:w-64 border-r border-white/5 flex flex-col items-center md:items-stretch h-screen sticky top-0 bg-black/50 backdrop-blur-xl">
      <div className="p-6 mb-8 flex items-center gap-3">
        <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shadow-lg ${role === 'admin' ? 'bg-gradient-to-br from-yellow-400 to-orange-600 shadow-orange-500/20' : 'bg-gradient-to-br from-cyan-400 to-blue-600 shadow-cyan-500/20'}`}>
          <Zap className="w-6 h-6 text-white" fill="currentColor" />
        </div>
        <span className="hidden md:block font-bold text-xl tracking-tight">TRH <span className={role === 'admin' ? 'text-yellow-400' : 'text-cyan-400'}>BOT</span> {role === 'admin' && <span className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-white/40 ml-1">ADM</span>}</span>
      </div>

      <nav className="flex-1 px-3 space-y-2">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`w-full flex items-center gap-4 px-4 py-4 rounded-2xl transition-all duration-300 ${activeTab === tab.id
              ? 'bg-cyan-500/10 text-cyan-400 shadow-inner'
              : 'text-white/40 hover:text-white hover:bg-white/5'
              }`}
          >
            <tab.icon className="w-5 h-5" />
            <span className="hidden md:block font-bold text-sm tracking-wide uppercase">{tab.label}</span>
          </button>
        ))}
      </nav>

      <div className="p-6 text-[10px] text-white/20 font-mono hidden md:block">
        <button
          onClick={onLogin}
          className="text-left hover:text-white/40 transition-colors"
        >
          v2.4.0-STABLE <br />
          CORE: ONLINE
        </button>
      </div>
    </div>
  );
};

// --- Main Views ---

const DashboardView = ({ state, role, filterSince, setFilterSince }: { state: BotState; role: string; filterSince: string; setFilterSince: (v: string) => void }) => {
  const filterTime = filterSince ? new Date(filterSince).getTime() : 0;

  // Filtrar el historial por fecha
  const filteredHistory = filterSince
    ? state.history.filter(h => h.close_time * 1000 >= filterTime)
    : state.history;

  // NO filtrar las operaciones activas por fecha, deben verse todas las actuales
  const filteredOperations = state.operations;

  // Calculamos las estadísticas por bot respetando el filtro
  const getFilteredStratStats = (stratId: string) => {
    const stratHistory = filteredHistory.filter(h => h.strategy_id === stratId);
    const stratActiveOps = filteredOperations.filter(op => op.strategy_id === stratId);

    const wins = stratHistory.filter(h => h.final_pnl > 0).length;
    const losses = stratHistory.filter(h => h.final_pnl <= 0).length;
    const realizedPnl = stratHistory.reduce((acc, h) => acc + h.final_pnl, 0);
    const unrealizedPnL = stratActiveOps.reduce((acc, op) => acc + op.pnl, 0);

    const now = Date.now();

    // Balance inicial de 500€
    const strategyInitialBase = 500;

    const startTimeMs = filterSince ? filterTime : (state.strategies.find(s => s.id === stratId)?.start_time || 0) * 1000;
    const durationMs = Math.max(1000 * 60, now - (startTimeMs || now));
    const durationDays = durationMs / (1000 * 3600 * 24);

    // ROI basado en la base de 500 exacta
    const apy = (realizedPnl / strategyInitialBase) * (365 / durationDays) * 100;
    const dailyRoi = (realizedPnl / strategyInitialBase) / durationDays * 100;

    // Balance Bruto = 500 + Resultado de las cerradas (PNL Realizado)
    const rawBalance = strategyInitialBase + realizedPnl;

    // RESERVA DEL 10% PARA ESTRATEGIAS CON APALANCAMIENTO
    const leverageReserve = LEVERAGED_STRATEGIES.includes(stratId) ? (rawBalance * 0.10) : 0;

    // Balance Neto (Disponible) = Balance Bruto - Reserva
    // Aseguramos que si no hay operaciones, sea exactamente el capital inicial (menos reserva si aplica)
    const filteredBalance = (stratHistory.length === 0 && realizedPnl === 0)
      ? (strategyInitialBase - (LEVERAGED_STRATEGIES.includes(stratId) ? (strategyInitialBase * 0.10) : 0))
      : (rawBalance - leverageReserve);

    // Equity = Balance Bruto + PNL de las abiertas (Unrealized)
    // El equity representa el valor real de la cuenta (incluidas las abiertas), 
    // mientras que el balance/disponible es lo que queda libre tras las cerradas y reservas.
    const filteredEquity = rawBalance + unrealizedPnL;

    // Ops/Day
    const opsPerDay = stratHistory.length / Math.max(0.1, durationDays);

    // Tiempo medio en segundos -> minutos
    const durations = stratHistory.filter(h => h.entry_time > 0).map(h => h.close_time - h.entry_time);
    const avgDuration = durations.length > 0 ? (durations.reduce((a, b) => a + b, 0) / durations.length) / 60 : 0;

    return {
      wins,
      losses,
      pnl: realizedPnl,
      unrealizedPnL,
      total: stratHistory.length,
      apy,
      dailyRoi,
      avgDuration,
      opsPerDay,
      equity: filteredEquity,
      balance: filteredBalance,
      activeCount: stratActiveOps.length,
      leverageReserve
    };
  };

  const globalStats = filteredHistory.reduce((acc, h) => {
    acc.pnl += h.final_pnl;
    if (h.final_pnl > 0) acc.wins++;
    else acc.losses++;
    return acc;
  }, { pnl: 0, wins: 0, losses: 0 });

  const totalWins = globalStats.wins;
  const totalLosses = globalStats.losses;
  const winRate = (totalWins / (totalWins + totalLosses) * 100) || 0;

  // Calculamos TOTAL EQUITY y TOTAL BALANCE GLOBAL basados en los bots filtrados
  const totalPnLRealized = globalStats.pnl;
  const totalPnLUnrealized = filteredOperations.reduce((acc, op) => acc + op.pnl, 0);

  const globalInitialCapital = state.strategies.length * 500;

  // Equity Global: Capital Inicial + Resultados Totales
  const totalGlobalEquity = filterSince
    ? globalInitialCapital + totalPnLRealized + totalPnLUnrealized
    : state.global_equity;

  const totalGlobalAvailable = state.strategies.reduce((acc, s) => {
    const stratStats = getFilteredStratStats(s.id);
    return acc + stratStats.balance;
  }, 0);

  const getTrendColor = (trend?: string) => {
    if (!trend) return 'cyan';
    const t = trend.toUpperCase();
    if (t.includes('BULL') || t === 'HALCON' || t === 'TENDENCIA') return 'green';
    if (t.includes('BEAR') || t === 'DUMP' || t === 'BTC_CRASH' || t === 'BUNKER' || t === 'CRASH') return 'red';
    if (t === 'NEUTRAL' || t === 'ASPIRADORA' || t === 'LATERAL') return 'blue';
    return 'blue';
  };

  const dynamicColor = getTrendColor(state.market_trend);

  return (
    <div className="p-8 space-y-8 max-w-7xl mx-auto">
      {/* Header with Filter */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white/5 p-6 rounded-3xl border border-white/10">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">RESUMEN GENERAL</h2>
          <p className="text-xs text-white/40 font-mono mt-1">ESTADÍSTICAS CALCULADAS EN TIEMPO REAL</p>
        </div>
        <div className="flex flex-col gap-2">
          <label className="text-[10px] uppercase tracking-widest text-white/40 font-bold ml-1 flex items-center gap-2">
            <Clock className="w-3 h-3 text-cyan-400" />
            Visualizar datos desde:
          </label>
          <div className="flex items-center gap-2">
            <input
              type="datetime-local"
              step="1"
              value={filterSince}
              onChange={(e) => setFilterSince(e.target.value)}
              className="bg-black/40 border border-white/10 rounded-xl px-4 py-2 text-xs font-mono text-cyan-400 outline-none focus:border-cyan-500/50 transition-colors cursor-pointer"
            />
            {filterSince && (
              <button
                onClick={() => setFilterSince('')}
                className="p-2 rounded-xl bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                title="Limpiar filtro"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Global Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title="Saldo Total" value={`${totalGlobalEquity.toFixed(2)} €`} icon={Wallet} color={dynamicColor} subValue={`Disponible: ${totalGlobalAvailable.toFixed(2)} €`} />
        <StatCard title="PnL Generado" value={`${totalPnLRealized >= 0 ? '+' : ''}${totalPnLRealized.toFixed(2)} €`} icon={Activity} color={dynamicColor} subValue={`Win Rate: ${winRate.toFixed(1)}%`} />
        <StatCard title="Operaciones" value={filteredHistory.length} icon={TrendingUp} color={dynamicColor} subValue={`${totalWins} Gan / ${totalLosses} Per`} />
        <StatCard title="Estado Sistema" value="ONLINE" icon={Zap} color={dynamicColor} subValue="Latencia: 42ms" />
      </div>

      {/* Strategy Table */}
      <div className="glass rounded-3xl overflow-hidden border-white/5 border">
        <div className="p-6 border-b border-white/5 bg-white/5 flex items-center justify-between">
          <h3 className="font-bold text-lg">ESTRATEGIAS ACTIVAS</h3>
          <span className="text-[10px] text-white/20 font-mono tracking-tighter uppercase">{state.strategies.length} Bots Detectados</span>
        </div>
        <div className="overflow-x-auto max-h-[600px] overflow-y-auto scrollbar-thin">
          <table className="w-full text-left font-mono text-xs border-separate border-spacing-0">
            <thead className="sticky top-0 z-10 bg-[#1a1a1a]">
              <tr className="bg-white/5 text-white/30 uppercase text-[9px] tracking-widest font-black">
                <th className="px-6 py-4">Nombre / ID</th>
                <th className="px-6 py-4 text-center">Equity</th>
                <th className="px-6 py-4 text-center">Balance</th>
                <th className="px-6 py-4 text-center">PnL Realizado</th>
                <th className="px-6 py-4 text-center">ROI (APY)</th>
                <th className="px-6 py-4 text-center">Perf (G-P-A)</th>
                <th className="px-6 py-4 text-center">Ops/Día</th>
                <th className="px-6 py-4 text-center">Daily ROI</th>
                <th className="px-6 py-4 text-center">T. Medio</th>
                <th className="px-6 py-4 text-center">Status</th>
                {role === 'admin' && <th className="px-6 py-4 text-center">Acciones</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {[...state.strategies]
                .sort((a, b) => {
                  const statsA = getFilteredStratStats(a.id);
                  const statsB = getFilteredStratStats(b.id);
                  return statsB.apy - statsA.apy || statsB.pnl - statsA.pnl;
                })
                .map(strat => {
                  const f = getFilteredStratStats(strat.id);
                  const isLeveraged = LEVERAGED_STRATEGIES.includes(strat.id);
                  return (
                    <tr key={strat.id} className="hover:bg-cyan-500/5 transition-colors group">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="flex flex-col">
                            <div className="font-bold text-white group-hover:text-cyan-400 transition-colors uppercase">{strat.id}</div>
                            <div className="text-[8px] text-white/20 uppercase tracking-widest">{isLeveraged ? 'Apalancado x3 ISOLATED' : 'Bot de Trading'}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 font-bold text-center">{(f.equity || 0).toFixed(2)} €</td>
                      <td className="px-6 py-4 text-white/50 text-center">
                        <div className="flex flex-col items-center">
                          <span>{f.balance.toFixed(2)} €</span>
                          {f.leverageReserve > 0 && <span className="text-[8px] text-orange-500/60" title="Reserva 10% comisiones leverage">-{f.leverageReserve.toFixed(2)}€</span>}
                        </div>
                      </td>
                      <td className={`px-6 py-4 font-bold text-center ${f.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {f.pnl >= 0 ? '+' : ''}{f.pnl.toFixed(2)} €
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className={`flex items-center justify-center gap-1 font-bold ${f.apy < 30 ? 'text-red-500' :
                          f.apy < 500 ? 'text-orange-500' :
                            'text-green-500'
                          }`}>
                          <Percent className="w-3 h-3" />
                          {f.apy.toFixed(1)}%
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <div className="flex items-center justify-center gap-1.5 font-mono text-[10px] font-black">
                          <span className="text-green-500">{f.wins}</span>
                          <span className="text-white/10">-</span>
                          <span className="text-red-500">{f.losses}</span>
                          <span className="text-white/10">-</span>
                          <span className="text-blue-500">{f.activeCount}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-center font-bold text-cyan-400">{f.opsPerDay.toFixed(1)}</td>
                      <td className="px-6 py-4 font-bold text-center">{f.dailyRoi.toFixed(3)}%</td>
                      <td className="px-6 py-4 text-white/40 text-center">{f.avgDuration.toFixed(0)} min</td>
                      <td className="px-6 py-4">
                        <div className="flex justify-center">
                          <div className={`px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-widest flex items-center gap-1.5 ${strat.paused ? 'bg-orange-500/10 text-orange-400 border border-orange-500/20' : 'bg-green-500/10 text-green-400 border border-green-500/20'}`}>
                            <div className={`w-1.5 h-1.5 rounded-full ${strat.paused ? 'bg-orange-500' : 'bg-green-500'}`} />
                            {strat.paused ? 'PAUSED' : 'ONLINE'}
                          </div>
                        </div>
                      </td>
                      {role === 'admin' && (
                        <td className="px-6 py-4">
                          <div className="flex justify-center gap-2">
                            {strat.paused ? (
                              <button
                                onClick={() => axios.post(`/api/control/${strat.id}/resume`)}
                                className="p-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
                                title="Reanudar"
                              >
                                <Play className="w-3.5 h-3.5" />
                              </button>
                            ) : (
                              <button
                                onClick={() => axios.post(`/api/control/${strat.id}/pause`)}
                                className="p-1.5 rounded-lg bg-orange-500/20 text-orange-400 hover:bg-orange-500/30 transition-colors"
                                title="Pausar"
                              >
                                <Pause className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const OperationsView = ({ state, role, onReload, filterSince }: { state: BotState; role: string; onReload: () => void; filterSince: string }) => {
  const [strategyFilter, setStrategyFilter] = useState('ALL');
  const filterTime = filterSince ? new Date(filterSince).getTime() : 0;

  // Sort operations by pnl descending
  let displayOps = [...state.operations].sort((a, b) => b.pnl - a.pnl);

  // NO filtrar las operaciones activas por fecha
  // if (filterSince) {
  //   displayOps = displayOps.filter(op => op.open_time * 1000 >= filterTime);
  // }

  // Filter 2: Strategy specific
  if (strategyFilter !== 'ALL') {
    displayOps = displayOps.filter(op => op.strategy_id === strategyFilter);
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <h2 className="text-2xl font-bold tracking-tight">OPERACIONES <span className="text-cyan-400 text-sm font-mono ml-2">{displayOps.length} ACTIVAS</span></h2>
        <div className="flex flex-wrap items-center gap-4">
          {/* Strategy Selector */}
          <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 shadow-inner">
            <Filter className="w-3.5 h-3.5 text-white/40" />
            <select
              value={strategyFilter}
              onChange={(e) => setStrategyFilter(e.target.value)}
              className="bg-transparent text-xs font-mono text-cyan-400 outline-none cursor-pointer uppercase appearance-none"
            >
              <option value="ALL">TODAS LAS ESTRATEGIAS</option>
              {state.strategies.map(s => (
                <option key={s.id} value={s.id}>{s.id}</option>
              ))}
            </select>
          </div>

          {role === 'admin' && (
            <>
              <button
                onClick={onReload}
                className="px-6 py-2 bg-slate-800/20 border border-slate-700/30 rounded-xl text-slate-400 text-xs font-black uppercase tracking-[0.2em] shadow-lg hover:bg-slate-700/20 transition-all flex items-center gap-2"
                title="Recargar Estrategias"
              >
                <RefreshCw className="w-3 h-3" />
                Recargar
              </button>
              {displayOps.some(o => o.pnl > 0) && (
                <motion.button
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  onClick={() => {
                    if (window.confirm('¿Cerrar TODAS las operaciones en positivo?')) {
                      axios.post('/api/control/close_positive_trades');
                    }
                  }}
                  className="px-6 py-2 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-emerald-400 text-xs font-black uppercase tracking-[0.2em] shadow-lg shadow-emerald-500/10 hover:bg-emerald-500/20 transition-all flex items-center gap-2"
                >
                  <Zap className="w-3 h-3 fill-current" />
                  Cerrar Positivos
                </motion.button>
              )}
            </>
          )}
          <div className="px-4 py-2 bg-green-500/10 border border-green-500/20 rounded-xl text-green-400 text-xs font-bold uppercase tracking-widest shadow-sm">
            Long: {displayOps.filter(o => o.side === 'LONG' || o.side === 'buy').length}
          </div>
          <div className="px-4 py-2 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-xs font-bold uppercase tracking-widest shadow-sm">
            Short: {displayOps.filter(o => o.side === 'SHORT' || o.side === 'sell').length}
          </div>
        </div>
      </div>

      <div className="glass rounded-3xl overflow-hidden border-white/5 border">
        <div className="overflow-x-auto max-h-[85vh] overflow-y-auto scrollbar-thin">
          <table className="w-full text-left font-mono text-xs border-separate border-spacing-0">
            <thead className="sticky top-0 z-10 bg-[#1a1a1a]">
              <tr className="bg-white/5 text-white/30 uppercase text-[9px] tracking-widest font-black">
                {role === 'admin' && <th className="px-6 py-4 text-center">Acciones</th>}
                <th className="px-6 py-4">Estrategia</th>
                <th className="px-6 py-4">Símbolo</th>
                <th className="px-6 py-4">Inv. (€)</th>
                <th className="px-6 py-4 text-right">PnL (€)</th>
                <th className="px-6 py-4 text-center">PnL (%)</th>
                <th className="px-6 py-4">Entrada / Avg</th>
                <th className="px-6 py-4">Actual</th>
                <th className="px-6 py-4 text-center">Trailing Stop</th>
                <th className="px-6 py-4 text-center">Lado</th>
                <th className="px-6 py-4 text-center">DCA</th>
                <th className="px-6 py-4 text-right">Tiempo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {displayOps.map(op => (
                <tr key={`${op.strategy_id}-${op.id}`} className="hover:bg-white/5 transition-colors group">
                  {role === 'admin' && (
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={() => {
                          if (window.confirm(`¿Cerrar operación ${op.symbol} (${op.strategy_id})?`)) {
                            axios.post(`/api/control/close_trade/${op.strategy_id}/${op.id}`);
                          }
                        }}
                        className="p-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
                        title="Cerrar Operación"
                      >
                        <XCircle className="w-4 h-4" />
                      </button>
                    </td>
                  )}
                  <td className="px-6 py-4 text-white/40 font-bold uppercase">{op.strategy_id}</td>
                  <td className="px-6 py-4">
                    <span className="font-bold text-white text-sm">{op.symbol}</span>
                  </td>
                  <td className="px-6 py-4 font-bold">{(op.invested || op.margin || 0).toFixed(2)} €</td>
                  <td className={`px-6 py-4 text-right font-black text-sm ${op.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {op.pnl >= 0 ? '+' : ''}{op.pnl.toFixed(2)} €
                  </td>
                  <td className={`px-6 py-4 text-center font-bold ${op.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {op.pnl_pct.toFixed(2)}%
                  </td>
                  <td className="px-6 py-4">
                    <div className="font-bold text-white">{op.entry_price.toFixed(5)}</div>
                    <div className="text-[9px] text-white/30 lowercase font-mono">Avg: {(op.avg_price || op.avg || op.entry_price)?.toFixed(5)}</div>
                  </td>
                  <td className="px-6 py-4 text-cyan-400 font-bold">{op.current_price.toFixed(5)}</td>
                  <td className="px-6 py-4 text-center">
                    <span className={`text-[10px] font-black ${op.ts_price > 0 ? 'text-orange-400 bg-orange-500/10 border border-orange-500/20 px-2 py-0.5 rounded shadow-sm' : 'text-white/10'}`}>
                      {op.ts_price > 0 ? `${op.ts_price.toFixed(5)}` : 'WAITING'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className={`px-2 py-0.5 rounded text-[8px] font-black uppercase tracking-widest ${op.side === 'LONG' || op.side === 'buy' ? 'bg-green-500 text-black' : 'bg-red-500 text-white'}`}>
                      {op.side}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className="text-[9px] text-white/40 uppercase font-black tracking-widest bg-white/5 px-2 py-0.5 rounded">L {op.dca}</span>
                  </td>
                  <td className="px-6 py-4 text-right text-white/40">
                    {Math.floor((Date.now() / 1000 - op.open_time) / 60)}m
                  </td>
                </tr>
              ))}
              {displayOps.length === 0 && (
                <tr>
                  <td colSpan={role === 'admin' ? 12 : 11} className="px-6 py-12 text-center text-white/20 italic">No hay operaciones activas correspondientes al filtro</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

const LogsView = ({ logs }: { logs: string[] }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="p-8 h-screen flex flex-col space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold tracking-tight">TERMINAL <span className="text-cyan-400 text-sm font-mono ml-2">CORE ACTIVITY</span></h2>
        <div className="flex items-center gap-2 text-green-500 text-[10px] font-mono animate-pulse">
          <div className="w-2 h-2 rounded-full bg-green-500" />
          STREAMING LIVE
        </div>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 bg-[#050505] rounded-3xl border border-white/5 p-6 font-mono text-[12px] overflow-y-auto space-y-1 scroll-smooth shadow-2xl"
      >
        {logs.map((log, i) => {
          const isError = log.includes('ERROR');
          const isTrade = log.includes('OPEN') || log.includes('CLOSE');
          return (
            <div key={i} className={`flex gap-4 ${isError ? 'text-red-400' : isTrade ? 'text-cyan-400' : 'text-white/40'}`}>
              <span className="text-white/10 select-none">[{i.toString().padStart(4, '0')}]</span>
              <span className="whitespace-pre-wrap">{log}</span>
            </div>
          );
        })}
        {logs.length === 0 && <div className="text-white/20 italic">No hay actividad reciente en el log...</div>}
      </div>
    </div>
  );
};

const HistoryView = ({ history, filterSince, strategies }: { history: HistoryItem[]; filterSince: string; strategies: Strategy[] }) => {
  const [strategyFilter, setStrategyFilter] = useState('ALL');

  let filteredHistory = filterSince
    ? history.filter(h => h.close_time * 1000 >= new Date(filterSince).getTime())
    : history;

  if (strategyFilter !== 'ALL') {
    filteredHistory = filteredHistory.filter(h => h.strategy_id === strategyFilter);
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <h2 className="text-2xl font-bold tracking-tight">HISTORIAL <span className="text-cyan-400 text-sm font-mono ml-2">{filterSince ? `FILTRADO DESDE ${new Date(filterSince).toLocaleString()}` : 'ÚLTIMAS OPERACIONES'}</span></h2>

        {/* Strategy Selector */}
        <div className="flex items-center gap-2 bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 shadow-inner">
          <Filter className="w-3.5 h-3.5 text-white/40" />
          <select
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value)}
            className="bg-transparent text-xs font-mono text-cyan-400 outline-none cursor-pointer uppercase appearance-none"
          >
            <option value="ALL">TODAS LAS ESTRATEGIAS</option>
            {strategies.map(s => (
              <option key={s.id} value={s.id}>{s.id}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="glass rounded-3xl overflow-hidden border-white/5">
        <div className="overflow-x-auto max-h-[75vh] overflow-y-auto scrollbar-thin">
          <table className="w-full text-left font-mono text-xs border-separate border-spacing-0">
            <thead className="sticky top-0 z-10 bg-[#1a1a1a]">
              <tr className="bg-white/5 text-white/30 uppercase text-[9px] tracking-widest font-black">
                <th className="px-6 py-4">Cierre</th>
                <th className="px-6 py-4">Estrategia</th>
                <th className="px-6 py-4">Símbolo</th>
                <th className="px-6 py-4 text-center">Lado</th>
                <th className="px-6 py-4">Entrada</th>
                <th className="px-6 py-4">Salida</th>
                <th className="px-6 py-4 text-right">Resultado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {filteredHistory.map(item => (
                <tr key={item.id} className="hover:bg-white/5 transition-colors">
                  <td className="px-6 py-4 text-white/40 whitespace-nowrap text-[10px]">
                    {new Date(item.close_time * 1000).toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </td>
                  <td className="px-6 py-4 font-bold text-white/80 uppercase">{item.strategy_id}</td>
                  <td className="px-6 py-4">{item.symbol}</td>
                  <td className="px-6 py-4 text-center">
                    <span className={`px-2 py-0.5 rounded text-[8px] font-black ${item.side === 'LONG' || item.side === 'buy' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'
                      }`}>
                      {item.side}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-white/40">{item.entry_price.toFixed(5)}</td>
                  <td className="px-6 py-4 text-white/40">{item.exit_price.toFixed(5)}</td>
                  <td className={`px-6 py-4 text-right font-bold ${item.final_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {item.final_pnl >= 0 ? '+' : ''}{item.final_pnl.toFixed(2)} €
                  </td>
                </tr>
              ))}
              {filteredHistory.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-white/20 italic">No hay historial para el periodo seleccionado</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// --- Root Component ---

const DashboardContent = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [state, setState] = useState<BotState | null>(null);
  const [filterSince, setFilterSince] = useState('2026-03-01T00:00');
  const [role, setRole] = useState('viewer');
  const [loading, setLoading] = useState(true);
  const ws = useRef<WebSocket | null>(null);

  const checkRole = async () => {
    try {
      const res = await axios.get('/api/role');
      if (res.data.role) setRole(res.data.role);
    } catch (err) { console.error(err); }
  };

  const handleReloadStrategies = async () => {
    try {
      await axios.post('/api/control/reload');
    } catch (error) {
      console.error("Error reloading strategies:", error);
    }
  };

  const handleLogin = async () => {
    const password = prompt("Introduce la contraseña de administrador:");
    if (!password) return;

    try {
      const res = await axios.post('/api/auth/login', { password });
      if (res.data.status === 'success') {
        setRole('admin');
        alert("¡Bienvenido, Administrador!");
      }
    } catch (err) {
      alert("Contraseña incorrecta.");
    }
  };

  useEffect(() => {
    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.port === '5173' ? '192.168.1.99:8000' : window.location.host;
      const wsUrl = `${protocol}//${host}/ws`;

      const currentWs = new WebSocket(wsUrl);
      ws.current = currentWs;

      currentWs.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'full_state' || data.global_equity !== undefined) {
            setState(data);
            setLoading(false);
          } else if (data.type === 'market_tick') {
            const ticks = data.data;
            setState(prev => {
              if (!prev) return prev;
              const newState = { ...prev };

              // 1. Update Market Monitor
              if (newState.market) {
                newState.market = newState.market.map((m: any) => {
                  const tick = ticks.find((t: any) => t.symbol === m.symbol);
                  return tick ? { ...m, ...tick } : m;
                });
              }

              // 2. Update Operations Prices & PnL
              newState.operations = newState.operations.map(op => {
                const tick = ticks.find((t: any) => t.symbol === op.symbol);
                if (!tick) return op;

                const current_price = tick.price;
                const entry_price = op.avg_price || op.avg || op.entry_price;

                let pnl = 0;
                let pnl_pct = 0;

                const qty = op.quantity || op.size || 0;
                if (op.side === 'LONG' || op.side === 'buy') {
                  pnl = (current_price - entry_price) * qty;
                  pnl_pct = ((current_price - entry_price) / entry_price) * 100;
                } else {
                  pnl = (entry_price - current_price) * qty;
                  pnl_pct = ((entry_price - current_price) / entry_price) * 100;
                }

                return {
                  ...op,
                  current_price,
                  pnl,
                  pnl_pct
                };
              });

              return newState;
            });
          }
        } catch (e) { console.error(e); }
      };
      currentWs.onclose = () => setTimeout(connect, 3000);
    };

    const fetchState = () => {
      axios.get('/api/state').then(res => {
        if (res.data) {
          setState(res.data);
          setLoading(false);
        }
      }).catch(err => console.error("Refresh Error:", err));
    };

    fetchState();
    checkRole();
    connect();

    const interval = setInterval(fetchState, 10000);

    return () => {
      ws.current?.close();
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!state?.strategies) return;

    const scriptId = 'json-ld-strategies';
    let script = document.getElementById(scriptId) as HTMLScriptElement;

    if (!script) {
      script = document.createElement('script');
      script.id = scriptId;
      script.type = 'application/ld+json';
      document.head.appendChild(script);
    }

    const ldData = {
      "@context": "https://schema.org",
      "@type": "ItemList",
      "name": "Trading Strategies Dashboard",
      "description": "Performance metrics for automated trading strategies",
      "itemListElement": state.strategies.map((strat, index) => ({
        "@type": "SoftwareApplication",
        "name": `Bot Strategy: ${strat.id}`,
        "applicationCategory": "FinancialApplication",
        "operatingSystem": "Bot Agresivo Core",
        "softwareVersion": "2.4.0",
        "aggregateRating": {
          "@type": "AggregateRating",
          "ratingValue": Math.max(0, Math.min(100, (strat.win_rate || 0))),
          "bestRating": "100",
          "worstRating": "0"
        }
      }))
    };

    script.textContent = JSON.stringify(ldData);
  }, [state?.strategies]);

  if (loading || !state) {
    return (
      <div className="h-screen bg-black flex flex-col items-center justify-center gap-6">
        <Zap className="w-12 h-12 text-cyan-400 animate-pulse" />
        <div className="space-y-2 text-center">
          <p className="font-mono text-cyan-400 animate-pulse text-sm uppercase tracking-[0.3em]">Iniciando Núcleo</p>
          <p className="font-mono text-white/20 text-[10px] uppercase tracking-widest">Estableciendo conexión segura...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex bg-[#050505] min-h-screen text-white/90">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        role={role}
        onLogin={handleLogin}
      />

      <main className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2 }}
          >
            {activeTab === 'dashboard' && <DashboardView state={state} role={role} filterSince={filterSince} setFilterSince={setFilterSince} />}
            {activeTab === 'operations' && <OperationsView state={state} role={role} onReload={handleReloadStrategies} filterSince={filterSince} />}
            {activeTab === 'logs' && <LogsView logs={state.logs || []} />}
            {activeTab === 'history' && <HistoryView history={state.history || []} filterSince={filterSince} strategies={state.strategies || []} />}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
};

export default function App() {
  return <DashboardContent />;
}
