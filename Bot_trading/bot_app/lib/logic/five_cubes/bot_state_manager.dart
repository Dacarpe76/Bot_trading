import 'dart:convert';
import 'dart:io';
import 'package:path_provider/path_provider.dart';

import 'package:flutter/foundation.dart';

class BotStateManager {
  static const String _fileName = "portfolio_state.json";

  Future<File> get _localFile async {
    final directory = await getApplicationDocumentsDirectory();
    return File('${directory.path}/$_fileName');
  }

  Future<Map<String, dynamic>> loadState() async {
    try {
      final file = await _localFile;
      if (await file.exists()) {
        final contents = await file.readAsString();
        return json.decode(contents);
      }
    } catch (e) {
      debugPrint("Error loading state: $e");
    }
    return {'avg_buy_price': {}};
  }

  Future<void> saveState(Map<String, dynamic> state) async {
    try {
      final file = await _localFile;
      await file.writeAsString(json.encode(state));
    } catch (e) {
      debugPrint("Error saving state: $e");
    }
  }

  Future<void> updateAvgBuyPrice(
    String asset,
    double quantity,
    double price,
    Map<String, dynamic> currentState,
  ) async {
    // Current state
    Map<String, dynamic> avgBuyMap = currentState['avg_buy_price'] ?? {};

    // Simplified: Just storing last buy price for now.
    // Weighted average logic commented out as 'current_qty' context is missing here.
    // double currentAvg = (avgBuyMap[asset] ?? 0.0).toDouble();

    avgBuyMap[asset] = price;

    currentState['avg_buy_price'] = avgBuyMap;
    await saveState(currentState);
  }
}
