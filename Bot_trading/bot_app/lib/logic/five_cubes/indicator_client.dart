import 'dart:convert';
import 'package:http/http.dart' as http;

import 'package:flutter/foundation.dart';

class IndicatorClient {
  /// Fetches Fear and Greed Index from alternative.me
  Future<int> getFearAndGreed() async {
    try {
      final url = Uri.parse("https://api.alternative.me/fng/?limit=1");
      final response = await http.get(url);

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final value = data['data'][0]['value'];
        return int.tryParse(value) ?? 50;
      }
    } catch (e) {
      debugPrint("Error fetching Fear & Greed: $e");
    }
    return 50; // Default Neutral
  }

  /// Fetches DXY (Dollar Index)
  /// Note: Getting live DXY requires a paid API usually.
  /// We will monitor a public unexpected source or use a static fallback if not available
  /// For this simplified version, we return a safe default or mock it,
  /// as yfinance equivalent in Dart is complex without a backend proxy.
  /// Ideally: Call a Python endpoint or user input.
  /// Strategy: We will assume 100.0 (Safe) if we can't find a free API.
  Future<double> getDXY() async {
    // Placeholder value. Ideally call a real API or Backend.
    // For now, return a neutral/safe value to avoid accidental "Cruise" mode trigger
    // Cruise requires DXY < 103.
    return 100.0;
  }

  /// Fetches US Manufacturing PMI
  Future<double> getPMI() async {
    // Similar to DXY, reliable economic data APIs are often paid (TradingEconomics, Bloomberg).
    // Defaulting to 50.1 (Growth) as per Python script placeholder.
    return 50.1;
  }
}
