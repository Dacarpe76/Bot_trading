import 'dart:async';
import 'dart:io';
import 'dart:ui';
import 'package:bot_app/config/app_secrets.dart';
import 'package:bot_app/logic/five_cubes/binance_client.dart';
import 'package:bot_app/logic/five_cubes/bot_state_manager.dart';
import 'package:bot_app/logic/five_cubes/indicator_client.dart';
import 'package:bot_app/logic/five_cubes/strategy_engine.dart';
import 'package:bot_app/logic/kraken_client.dart'; // Correct client
import 'package:bot_app/logic/kraken/macro_policy.dart';
import 'package:bot_app/services/notification_helper.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';

Future<void> initializeService() async {
  final service = FlutterBackgroundService();

  const AndroidNotificationChannel channel = AndroidNotificationChannel(
    'daily_bot_reports',
    'Daily Reports',
    description: 'Notifications for daily trading bot execution',
    importance: Importance.high,
  );

  final FlutterLocalNotificationsPlugin flutterLocalNotificationsPlugin =
      FlutterLocalNotificationsPlugin();

  if (Platform.isIOS || Platform.isAndroid) {
    await flutterLocalNotificationsPlugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(channel);
  }

  await service.configure(
    androidConfiguration: AndroidConfiguration(
      onStart: onStart,
      autoStart: true,
      isForegroundMode: true,
      notificationChannelId: 'daily_bot_reports',
      initialNotificationTitle: 'Bot Trading Service',
      initialNotificationContent: 'Monitoring schedule...',
      foregroundServiceNotificationId: 888,
    ),
    iosConfiguration: IosConfiguration(
      autoStart: true,
      onForeground: onStart,
      onBackground: onIosBackground,
    ),
  );
}

@pragma('vm:entry-point')
void onStart(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationHelper.initialize();

  // === INITIALIZATION ===
  // 1. Five Cubes (Binance)
  final binance = BinanceClient(
    apiKey: AppSecrets.binanceApiKey,
    apiSecret: AppSecrets.binanceSecretKey,
    isMock: false, // REAL MODE
  );
  final indicators = IndicatorClient();
  final stateMgr = BotStateManager();
  final fiveCubes = FiveCubesEngine(
    binance: binance,
    indicators: indicators,
    stateManager: stateMgr,
  );

  // 2. Kraken (Macro)
  final krakenClient = KrakenClient(
    apiKey: AppSecrets.krakenApiKey,
    secretKey: AppSecrets.krakenSecretKey,
  );
  final macroPolicy = MacroPolicy();

  service.on('stopService').listen((event) {
    service.stopSelf();
  });

  // === SCHEDULE LOOP ===
  // Check every 10 minutes
  Timer.periodic(const Duration(minutes: 10), (timer) async {
    final now = DateTime.now();
    final prefs = await SharedPreferences.getInstance();

    // Check if we passed 9:00 AM
    if (now.hour >= 9) {
      final String todayKey = "${now.year}-${now.month}-${now.day}";
      final String? lastRun = prefs.getString('last_run_date');

      if (lastRun != todayKey) {
        // Has NOT run today. Check Connectivity.
        final connectivityResult = await (Connectivity().checkConnectivity());
        bool hasInternet = !connectivityResult.contains(
          ConnectivityResult.none,
        );

        if (hasInternet) {
          debugPrint("🚀 Starting Daily Routine (Retry/First Run)...");
          await _executeDailyRoutine(
            fiveCubes,
            krakenClient,
            macroPolicy,
            todayKey,
            prefs,
          );
        } else {
          debugPrint("⚠️ No Internet. Retrying next cycle.");
          if (service is AndroidServiceInstance) {
            service.setForegroundNotificationInfo(
              title: "Bot Trading Paused",
              content: "Waiting for internet to run daily routine...",
            );
          }
        }
      } else {
        // Already ran today
        if (service is AndroidServiceInstance) {
          service.setForegroundNotificationInfo(
            title: "Bot Trading Active",
            content: "Routine completed for today ($todayKey).",
          );
        }
      }
    }
  });
}

Future<void> _executeDailyRoutine(
  FiveCubesEngine fiveCubes,
  KrakenClient kraken,
  MacroPolicy policy,
  String todayKey,
  SharedPreferences prefs,
) async {
  try {
    // Notify Start
    await NotificationHelper.showNotification(
      "Trading Bots Running",
      "Executing daily logic for Binance & Kraken...",
    );

    // --- 1. Binance Routine ---
    String binanceLog = await fiveCubes.runDailyRoutine();
    debugPrint("Binance Output: $binanceLog");

    // Save logs for UI
    final List<String> currentLogs = prefs.getStringList('binance_logs') ?? [];
    currentLogs.insert(0, "[${DateTime.now()}] $binanceLog");
    if (currentLogs.length > 50) currentLogs.removeLast(); // Keep last 50
    await prefs.setStringList('binance_logs', currentLogs);

    // Parse result or fetch balance for notification
    final binanceBals = await fiveCubes.binance.fetchBalances(['USDT']);
    double binanceUsdt = binanceBals['USDT'] ?? 0.0;

    // SAVE HISTORY for Chart
    List<String> historyList = prefs.getStringList('binance_history') ?? [];
    // Format: "timestamp|value"
    historyList.add("${DateTime.now().millisecondsSinceEpoch}|$binanceUsdt");
    if (historyList.length > 100) {
      historyList.removeAt(0); // Keep last 100 points
    }
    await prefs.setStringList('binance_history', historyList);

    // --- 2. Kraken Routine ---
    final kEur = await kraken.getTradeBalance();

    // Done
    await prefs.setString('last_run_date', todayKey); // Mark as done

    await NotificationHelper.showNotification(
      "Daily Report 📊",
      "Binance: ${binanceUsdt.toStringAsFixed(2)} USDT | Kraken: ${kEur.toStringAsFixed(2)} €\nCheck app for details.",
    );
  } catch (e) {
    debugPrint("❌ CRITICAL ERROR IN BOT ROUTINE: $e");
    await NotificationHelper.showNotification(
      "Bot Execution Failed",
      "Error: $e. Will retry next cycle if not saved.",
    );
  }
}

@pragma('vm:entry-point')
Future<bool> onIosBackground(ServiceInstance service) async {
  WidgetsFlutterBinding.ensureInitialized();
  DartPluginRegistrant.ensureInitialized();
  return true;
}
