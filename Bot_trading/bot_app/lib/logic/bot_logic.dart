import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:bot_app/logic/kraken/macro_policy.dart';
import 'package:bot_app/logic/kraken_client.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class BotState {
  final double equity;
  final String status;
  final List<String> logs;
  final DateTime lastUpdate;
  final bool isPanic;
  final List<Map<String, dynamic>> equityHistory;
  final double profitPercent;
  final Map<String, dynamic> portfolio; // NEW

  BotState({
    required this.equity,
    required this.status,
    required this.logs,
    required this.lastUpdate,
    this.isPanic = false,
    required this.equityHistory,
    this.profitPercent = 0.0,
    this.portfolio = const {},
  });

  factory BotState.initial() {
    return BotState(
      equity: 0.0,
      status: "Idle",
      logs: [],
      lastUpdate: DateTime.now(),
      equityHistory: [],
      portfolio: {},
    );
  }
}

class BotLogic {
  final KrakenClient client;
  final StreamController<BotState> _stateController =
      StreamController<BotState>.broadcast();

  Stream<BotState> get stateStream => _stateController.stream;

  bool _isRunning = false;
  bool _isPanic = false;

  final List<String> _logs = [];
  double _lastEquity = 0.0;
  List<Map<String, dynamic>> _equityHistory = [];
  Map<String, dynamic> _lastPortfolio = {}; // NEW
  double _netDeposits = 500.0; // Track total invested
  Timer? _timer;

  // Config constants
  static const double pmiThreshold = 47.0;
  static const int rsiPeriod = 14;
  static const int smaFast = 50;
  static const int smaSlow = 200;

  BotLogic({required String apiKey, required String secretKey})
    : client = KrakenClient(apiKey: apiKey, secretKey: secretKey);

  void start() async {
    if (_isRunning) return;
    _isRunning = true;
    // Load History & Logs FIRST to avoid overwriting
    await _loadHistory();
    await _loadLogs();

    _addLog("🤖 Bot Started.");

    // Fetch Net Deposited Capital
    _netDeposits = await client.getNetDeposits();
    _addLog("💰 Total Invested Check: €${_netDeposits.toStringAsFixed(2)}");

    _executeCycle(); // Run immediately
    _timer = Timer.periodic(Duration(minutes: 60), (timer) => _executeCycle());
    _emitState("Active");
  }

  void stop() {
    _isRunning = false;
    _timer?.cancel();
    _addLog("🛑 Bot Stopped.");
    _emitState("Stopped");
  }

  void togglePanic() {
    _isPanic = !_isPanic;
    if (_isPanic) {
      _addLog("🚨 PANIC MODE ACTIVATED!");
      _panicSell();
    } else {
      _addLog("✅ Panic Mode Deactivated.");
    }
    _emitState(_isPanic ? "PANIC" : "Active");
  }

  Future<void> refresh() async {
    _addLog("🔄 Manual Refresh Triggered...");
    _netDeposits = await client.getNetDeposits(); // Update deposits
    await _executeCycle();
  }

  Future<void> _panicSell() async {
    // Implement sell all logic
    try {
      // close positions logic...
      _addLog("Selling all positions (Simulation)...");
    } catch (e) {
      _addLog("Error in Panic Sell: $e");
    }
  }

  Future<void> _executeCycle() async {
    if (!_isRunning || _isPanic) return;

    _addLog("📡 Fetching Market Data...");
    _emitState("Fetching Data...");

    try {
      // 1. Fetch Balances (Detailed + Equity)
      final balances = await client.getDetailedBalances();
      double equity = await client.getTradeBalance();
      // If equity is 0 (API fail or empty), try summing balances?
      // Kraken 'TradeBalance' usually reliable for total equity in ZEUR.
      if (equity == 0 && balances.isNotEmpty) {
        // Fallback or just accept 0
      }

      _lastEquity = equity;
      _saveHistoryPoint(equity);

      // _lastPortfolio will be populated AFTER fetching prices to give real value
      _addLog("💰 Equity: €${equity.toStringAsFixed(2)}");

      // 2. Fetch Prices (Mocked/Snapshot)
      // We need BTC Price for strategy
      // 3. Prices
      // Try fetching separately or with standard alias if one fails
      // 'PAXGZEUR' failed. Try 'PAXGEUR' or 'XPAXGZEUR'.
      // Common Kraken pairs: XXBTZEUR (BTC/EUR), PAXGEUR (Paxos Gold/EUR)
      // Request BOTH standard and internal names to be safe
      // Request BOTH standard and internal names to be safe
      // Request standard aliases. 'PAXGZEUR' likely invalid INPUT, though valid OUTPUT key.
      final tickerData = await client.getTicker("XXBTZEUR,PAXGEUR");
      double btcPrice = 0.0;
      double goldPrice = 0.0;

      if (tickerData['error'] != null &&
          (tickerData['error'] as List).isNotEmpty) {
        _addLog("⚠️ Ticker API Error: ${tickerData['error']}");
      } else if (tickerData['result'] != null) {
        final res = tickerData['result'];
        // Debug keys to find correct Gold name
        // _addLog("DEBUG Keys: ${res.keys.join(', ')}");

        // BTC Check
        if (res['XXBTZEUR'] != null) {
          btcPrice = double.tryParse(res['XXBTZEUR']['c'][0]) ?? 0.0;
        } else if (res['XBTEUR'] != null) {
          btcPrice = double.tryParse(res['XBTEUR']['c'][0]) ?? 0.0;
        }

        // Gold Check (Check ALL variants)
        // PAXGZEUR (Kraken Standard) or PAXGEUR (Alias) or XPAXGZEUR (Internal)
        if (res['PAXGZEUR'] != null) {
          goldPrice = double.tryParse(res['PAXGZEUR']['c'][0]) ?? 0.0;
        } else if (res['PAXGEUR'] != null) {
          goldPrice = double.tryParse(res['PAXGEUR']['c'][0]) ?? 0.0;
        } else if (res['XPAXGZEUR'] != null) {
          goldPrice = double.tryParse(res['XPAXGZEUR']['c'][0]) ?? 0.0;
        }
      } else {
        _addLog("⚠️ Unexpected Ticker structure: $tickerData");
      }

      _addLog("Prices: BTC €$btcPrice | GOLD €$goldPrice");

      // 3b. Update Portfolio with Values (Kraken)
      Map<String, dynamic> enrichedPortfolio = {};
      balances.forEach((asset, qty) {
        if (qty <= 0) return;
        double valEur = 0.0;
        if (asset == 'ZEUR' || asset == 'EUR') {
          valEur = qty;
        } else if (asset == 'XXBT' || asset == 'XBT') {
          valEur = qty * btcPrice;
        } else if (asset == 'PAXG' || asset == 'XAU') {
          valEur = qty * goldPrice;
        }
        // Store struct: {'qty': 0.0, 'val': 0.0}
        enrichedPortfolio[asset] = {'qty': qty, 'val': valEur};
      });
      _lastPortfolio = enrichedPortfolio;

      // 3. Strategy Analysis
      final policy = MacroPolicy();

      // MOCKED INDICATORS (Placeholder for real data feeds)
      double pmi = 48.0;
      double tips = 1.5;
      double vix = 18.0;
      double rsi = 50.0;
      double sma200 = btcPrice * 0.9;

      // _addLog("📊 Inputs: PMI=$pmi | VIX=$vix");

      String regimen = policy.detectRegimen(pmi: pmi, tips: tips, vix: vix);
      // _addLog("🛡️ Regime: $regimen");

      final targets = policy.getTargetAllocation(
        regimen,
        btcPrice,
        sma200,
        rsi,
      );

      double tBtc = targets['BTC'] ?? 0.0;
      double tGold = targets['GOLD'] ?? 0.0;

      // SAFETY GUARD: Check prices before proceeding
      if (btcPrice <= 0 || goldPrice <= 0) {
        // _addLog("⚠️ Invalid prices. Skipping trade execution.");
        _emitState("Price Error");
        return;
      }

      // _addLog("🎯 Targets: BTC ${(tBtc * 100).toInt()}% | GOLD ${(tGold * 100).toInt()}%");

      // 4. Execution Logic (Smart Liquidity)
      // Core Tickers needing management
      // Note: In Kraken, Gold is 'PAXG' (per user) or 'XAU'?
      // Strategy says 'GOLD', let's map it to PAXG/XAU depending on what we have.
      // Assuming 'PAXG' for now based on Binance file usage.

      // Calculate Holdings Value
      double currentBtcQty = balances['XXBT'] ?? 0.0;
      double currentBtcVal = currentBtcQty * btcPrice;

      // Target Value
      double targetBtcVal = equity * tBtc;
      double diffBtc = targetBtcVal - currentBtcVal;

      // REBALANCE BTC
      if (diffBtc.abs() > 50) {
        // Threshold €50
        if (diffBtc > 0) {
          // BUY BTC
          // Check "Smart Liquidity" (Non-Core Assets)
          // Core: XXBT, PAXG, ZEUR, XAU
          // Others: XXRP, XETH, etc.
          for (var asset in balances.keys) {
            if (['XXBT', 'PAXG', 'XAU', 'ZEUR', 'KFEE'].contains(asset)) {
              continue;
            }

            double qty = balances[asset] ?? 0.0;
            if (qty > 0) {
              // Attempt to use this asset.
              // Strategy: Sell Asset -> EUR. Then Buy BTC.
              // We don't have price for Asset, so we can't calc exact value easily without fetch.
              // Blind swap: Sell ALL surplus of this asset? Or just log?
              _addLog(
                "💧 Smart Liquidity: Found $qty $asset. Converting to EUR for BTC...",
              );
              try {
                // Try selling to EUR. E.g. XXRPZEUR
                // Make basic assumption about pair name
                String pair = '${asset}ZEUR';
                await client.addOrder(pair, 'sell', 'market', qty);
                _addLog("✅ Sold $asset to EUR liquidity.");
              } catch (e) {
                _addLog("⚠️ Could not liquidate $asset: $e");
              }
            }
          }

          // Proceed to Buy BTC with EUR (Standard)
          if (!_isPanic) {
            double qtyToBuy = diffBtc / btcPrice;
            _addLog("✅ Buying $qtyToBuy BTC (~€${diffBtc.toStringAsFixed(2)})");
            await client.addOrder('XXBTZEUR', 'buy', 'market', qtyToBuy);
          }
        } else {
          // SELL BTC
          if (!_isPanic) {
            double qtyToSell = diffBtc.abs() / btcPrice;
            _addLog(
              "🔻 Selling $qtyToSell BTC (~€${diffBtc.abs().toStringAsFixed(2)})",
            );
            await client.addOrder('XXBTZEUR', 'sell', 'market', qtyToSell);
          }
        }
      }

      // REBALANCE GOLD (PAXG)
      double currentGoldQty = balances['PAXG'] ?? 0.0;
      // Add XAU if present? Usually PAXG on Kraken.
      double currentGoldVal = currentGoldQty * goldPrice;

      double targetGoldVal = equity * tGold;
      double diffGold = targetGoldVal - currentGoldVal;

      if (diffGold.abs() > 50) {
        // Threshold €50
        if (diffGold > 0) {
          // BUY GOLD
          if (!_isPanic) {
            double qtyToBuy = diffGold / goldPrice;
            _addLog(
              "✅ Buying $qtyToBuy PAXG (~€${diffGold.toStringAsFixed(2)})",
            );
            await client.addOrder('PAXGEUR', 'buy', 'market', qtyToBuy);
          }
        } else {
          // SELL GOLD
          if (!_isPanic) {
            double qtyToSell = diffGold.abs() / goldPrice;
            _addLog(
              "🔻 Selling $qtyToSell PAXG (~€${diffGold.abs().toStringAsFixed(2)})",
            );
            await client.addOrder('PAXGEUR', 'sell', 'market', qtyToSell);
          }
        }
      }

      _emitState("Sleeping...");
    } catch (e) {
      _addLog("❌ Cycle Error: $e");
      _emitState("Error");
    }
  }

  // Ensure logs are persistent
  // Ensure logs are persistent

  // ... (inside BotLogic)

  // [MODIFIED] Load logs from storage
  Future<void> _loadLogs() async {
    final prefs = await SharedPreferences.getInstance();
    final savedLogs = prefs.getStringList('kraken_logs') ?? [];
    _logs.clear();
    _logs.addAll(savedLogs);
  }

  // [MODIFIED] _addLog with persistence
  void _addLog(String msg) async {
    String time =
        "${DateTime.now().hour}:${DateTime.now().minute}:${DateTime.now().second}";
    String fullMsg = "[$time] $msg";
    _logs.insert(0, fullMsg);
    if (_logs.length > 50) {
      _logs.removeLast();
    }

    // Save to prefs (fire and forget)
    try {
      final prefs = await SharedPreferences.getInstance();
      prefs.setStringList('kraken_logs', _logs);
    } catch (e) {
      debugPrint("Error saving logs: $e");
    }

    // Trigger update if stream is active (handled by _emitState usually called after logs)
  }

  void _emitState(String status) {
    // Calculate P/L. Base: Net Deposits
    double initialCapital = _netDeposits;
    // Guard against zero
    if (initialCapital <= 0) initialCapital = 500.0;

    double pnl = ((_lastEquity - initialCapital) / initialCapital) * 100;

    _stateController.add(
      BotState(
        equity: _lastEquity,
        status: status,
        logs: List.from(_logs),
        lastUpdate: DateTime.now(),
        isPanic: _isPanic,
        equityHistory: List.from(_equityHistory),
        profitPercent: pnl,
        portfolio: _lastPortfolio, // Pass portfolio
      ),
    );
  }

  // --- PERSISTENCE ---
  Future<String> get _localPath async {
    final directory = await getApplicationDocumentsDirectory();
    return directory.path;
  }

  Future<File> get _historyFile async {
    final path = await _localPath;
    return File('$path/equity_history.json');
  }

  Future<void> _loadHistory() async {
    try {
      final file = await _historyFile;
      if (await file.exists()) {
        final contents = await file.readAsString();
        List<dynamic> jsonList = json.decode(contents);
        _equityHistory = jsonList
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
        _addLog("Loaded ${_equityHistory.length} history points.");
      }
    } catch (e) {
      _addLog("Error loading history: $e");
    }
  }

  Future<void> _saveHistoryPoint(double equity) async {
    try {
      final now = DateTime.now();
      _equityHistory.add({'time': now.millisecondsSinceEpoch, 'value': equity});

      final file = await _historyFile;
      await file.writeAsString(json.encode(_equityHistory));
    } catch (e) {
      _addLog("Error saving history: $e");
    }
  }

  void dispose() {
    _timer?.cancel();
    _stateController.close();
  }
}
