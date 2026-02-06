import 'dart:async';
import 'package:bot_app/config/app_secrets.dart';
import 'package:bot_app/logic/bot_logic.dart'; // Using generic BotLogic (Kraken)
import 'package:bot_app/logic/five_cubes/binance_client.dart';
import 'package:bot_app/logic/five_cubes/bot_state_manager.dart';
import 'package:bot_app/logic/five_cubes/indicator_client.dart';
import 'package:bot_app/logic/five_cubes/strategy_engine.dart';

import 'package:bot_app/services/notification_helper.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class DailyBotRunner {
  // Singleton
  static final DailyBotRunner _instance = DailyBotRunner._internal();
  factory DailyBotRunner() => _instance;
  DailyBotRunner._internal();

  bool _isRunning = false;

  /// Check if 24h passed since last run. If so, run.
  Future<void> checkAndRunOnOpen() async {
    if (_isRunning) return;

    final prefs = await SharedPreferences.getInstance();
    final String? lastRunDate = prefs.getString('last_run_date');
    final now = DateTime.now();
    final String todayKey = "${now.year}-${now.month}-${now.day}";

    bool shouldRun = false;

    if (lastRunDate != todayKey) {
      debugPrint(
        "🚀 Last run was $lastRunDate. Today is $todayKey. checking connectivity...",
      );
      final connectivityResult = await (Connectivity().checkConnectivity());
      bool hasInternet = !connectivityResult.contains(ConnectivityResult.none);
      if (hasInternet) {
        shouldRun = true;
      } else {
        debugPrint("⚠️ No internet to run bot.");
      }
    } else {
      debugPrint("✅ Already ran today ($todayKey).");
    }

    if (shouldRun) {
      await _executeRoutine(prefs, todayKey, isForce: false);
    }
  }

  /// Force run now (ignoring date).
  Future<void> forceRun(BuildContext context) async {
    if (_isRunning) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Bot is already running...")),
      );
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    final now = DateTime.now();
    final String todayKey = "${now.year}-${now.month}-${now.day}";

    await _executeRoutine(prefs, todayKey, isForce: true);

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Execution Finished. Check logs.")),
      );
    }
  }

  Future<void> _executeRoutine(
    SharedPreferences prefs,
    String todayKey, {
    required bool isForce,
  }) async {
    _isRunning = true;

    await NotificationHelper.showNotification(
      "Trading Bot Active",
      isForce
          ? "Executing FORCED strategy check..."
          : "Executing daily strategy check...",
    );

    try {
      debugPrint("🤖 Bot Runner Started...");

      // === 1. BINANCE Routine ===
      final binance = BinanceClient(
        apiKey: AppSecrets.binanceApiKey,
        apiSecret: AppSecrets.binanceSecretKey,
        isMock: false,
      );
      final indicators = IndicatorClient();
      final stateMgr = BotStateManager();
      final fiveCubes = FiveCubesEngine(
        binance: binance,
        indicators: indicators,
        stateManager: stateMgr,
      );

      String binanceLog = await fiveCubes.runDailyRoutine();
      debugPrint("Binance Output: $binanceLog");

      // Save Logs (Binance)
      final List<String> currentLogs =
          prefs.getStringList('binance_logs') ?? [];
      currentLogs.insert(0, "[${DateTime.now()}] $binanceLog");
      if (currentLogs.length > 50) currentLogs.removeLast();
      await prefs.setStringList('binance_logs', currentLogs);

      // Save History (Binance)
      final binanceBals = await fiveCubes.binance.fetchBalances(['EUR']);
      double binanceTotal = binanceBals['EUR'] ?? 0.0;
      List<String> historyList = prefs.getStringList('binance_history') ?? [];
      historyList.add("${DateTime.now().millisecondsSinceEpoch}|$binanceTotal");
      if (historyList.length > 100) historyList.removeAt(0);
      await prefs.setStringList('binance_history', historyList);

      // === 2. KRAKEN Routine ===
      // Check if we can use existing BotLogic or just run manual code due to loose structure.
      // BotLogic in 'logic/bot_logic.dart' has logic to fetch balance and "Simulate" strategy.
      // We will define a temporary BotLogic just to run its 'refresh' or '_executeCycle' logic if accessible,
      // but methods are private or view-bound.
      // So we will replicate the basic Kraken Fetch here to ensure balance updates.
      // NOTE: The 'BotLogic' class handles its own logs/history in 'kraken_logs'/'equity_history'.
      // If we want to update those, we should replicate the logic or instantiate BotLogic.
      // Let's Instantiate BotLogic and call 'refresh()' which is public and executes the cycle!
      final krakenBot = BotLogic(
        apiKey: AppSecrets.krakenApiKey,
        secretKey: AppSecrets.krakenSecretKey,
      );
      // 'start' runs 'executeCycle' and sets up timer. We don't want timer. we want one-off.
      // 'refresh' runs 'executeCycle'.
      await krakenBot.refresh();
      // Note: BotLogic.refresh() is async.

      // Mark as done for today
      if (!isForce) {
        await prefs.setString('last_run_date', todayKey);
      }

      await NotificationHelper.showNotification(
        "Run Completed 🏁",
        "Binance: ${binanceTotal.toStringAsFixed(2)} EUR | Kraken checked.",
      );
    } catch (e) {
      debugPrint("❌ CRITICAL ERROR IN BOT RUNNER: $e");
      await NotificationHelper.showNotification(
        "Bot Execution Failed",
        "Error: $e",
      );
    } finally {
      _isRunning = false;
    }
  }
}
