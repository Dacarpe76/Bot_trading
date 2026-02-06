import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:crypto/crypto.dart';

import 'package:flutter/foundation.dart';

import 'package:bot_app/config/app_secrets.dart';

class BinanceClient {
  final String apiKey;
  final String apiSecret;
  final String baseUrl = 'https://api.binance.com';
  final bool isMock;

  BinanceClient({
    this.apiKey = AppSecrets.binanceApiKey,
    this.apiSecret = AppSecrets.binanceSecretKey,
    this.isMock = false, // ENABLE REAL TRADING
  });

  /// Generates the HMAC SHA256 signature required by Binance
  String _sign(String queryString) {
    var key = utf8.encode(apiSecret);
    var bytes = utf8.encode(queryString);
    var hmac = Hmac(sha256, key);
    var digest = hmac.convert(bytes);
    return digest.toString();
  }

  /// Headers for the request
  Map<String, String> get _headers => {
    'X-MBX-APIKEY': apiKey,
    'Content-Type': 'application/x-www-form-urlencoded',
  };

  /// Fetch Account Information (Balances)
  Future<Map<String, double>> fetchBalances(List<String> assets) async {
    if (isMock) {
      if (assets.isEmpty) {
        // Return mostly empty or some random "Other" for testing
        return {
          'BTC': 0.1,
          'ETH': 0.0,
          'SOL': 0.0,
          'PAXG': 0.0,
          'EUR': 1000.0,
          'XRP': 500.0,
        };
      }
      return {'BTC': 0.1, 'ETH': 0.0, 'SOL': 0.0, 'PAXG': 0.0, 'EUR': 1000.0};
    }

    final endpoint = '/api/v3/account';
    final timestamp =
        DateTime.now().millisecondsSinceEpoch -
        10000; // Subtract 10s for sync safety
    final queryString = 'timestamp=$timestamp';
    final signature = _sign(queryString);
    final url = Uri.parse(
      '$baseUrl$endpoint?$queryString&signature=$signature',
    );

    try {
      final response = await http.get(url, headers: _headers);
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final balances = <String, double>{};
        final List<dynamic> balancesList = data['balances'];

        if (assets.isEmpty) {
          // Fetch ALL non-zero
          for (var b in balancesList) {
            double free = double.tryParse(b['free']) ?? 0.0;
            if (free > 0) {
              balances[b['asset']] = free;
            }
          }
        } else {
          for (var asset in assets) {
            final assetData = balancesList.firstWhere(
              (b) => b['asset'] == asset,
              orElse: () => {'free': '0.0'},
            );
            balances[asset] = double.tryParse(assetData['free']) ?? 0.0;
          }
        }
        return balances;
      } else {
        debugPrint('Binance Error fetchBalances: ${response.body}');
        return {};
      }
    } catch (e) {
      debugPrint('Exception fetchBalances: $e');
      return {};
    }
  }

  /// Fetch Current Prices for symbols (e.g., BTCUSDT)
  Future<Map<String, double>> fetchPrices(List<String> symbols) async {
    if (isMock) {
      return {
        'BTCEUR': 40000.0,
        'ETHEUR': 2200.0,
        'SOLEUR': 90.0,
        'PAXGEUR': 2000.0,
        'EUREUR': 1.0,
      };
    }

    final prices = <String, double>{};
    for (var symbol in symbols) {
      // Small optimization: fetchTickerPrice can be batch, but simplified here
      final endpoint = '/api/v3/ticker/price';
      final url = Uri.parse('$baseUrl$endpoint?symbol=$symbol');

      try {
        final response = await http.get(url); // No auth needed for public data
        if (response.statusCode == 200) {
          final data = json.decode(response.body);
          prices[symbol] = double.tryParse(data['price']) ?? 0.0;
        }
      } catch (e) {
        debugPrint('Error fetching price for $symbol: $e');
      }
    }
    return prices;
  }

  /// Place a Market Order
  Future<bool> placeMarketOrder(
    String symbol,
    String side,
    double quantity,
  ) async {
    if (isMock) {
      debugPrint('[MOCK] Placed MARKET $side for $quantity $symbol');
      return true;
    }

    final endpoint = '/api/v3/order';
    final timestamp =
        DateTime.now().millisecondsSinceEpoch -
        10000; // Subtract 10s for sync safety
    final queryString =
        'symbol=$symbol&side=${side.toUpperCase()}&type=MARKET&quantity=$quantity&timestamp=$timestamp';
    final signature = _sign(queryString);
    final url = Uri.parse(
      '$baseUrl$endpoint',
    ); // POST request parameters go in body usually, but query string works too for Binance

    try {
      final response = await http.post(
        url,
        headers: _headers,
        body:
            '$queryString&signature=$signature', // body must contain the params for POST
      );

      if (response.statusCode == 200) {
        debugPrint('Order Successful: ${response.body}');
        return true;
      } else {
        debugPrint('Order Failed: ${response.body}');
        return false;
      }
    } catch (e) {
      debugPrint('Exception placeOrder: $e');
      return false;
    }
  }

  /// Fetch Account Snapshot (Daily Equity History)
  Future<List<Map<String, dynamic>>> getAccountSnapshot() async {
    if (isMock) {
      // Mock data for graph
      final now = DateTime.now();
      return List.generate(30, (index) {
        return {
          'time': now
              .subtract(Duration(days: 30 - index))
              .millisecondsSinceEpoch,
          'totalAssetOfBtc': '0.15', // Mock BTC value
        };
      });
    }

    final endpoint = '/sapi/v1/accountSnapshot';
    final timestamp = DateTime.now().millisecondsSinceEpoch - 10000;
    final queryString = 'type=SPOT&limit=30&timestamp=$timestamp';
    final signature = _sign(queryString);
    final url = Uri.parse(
      '$baseUrl$endpoint?$queryString&signature=$signature',
    );

    try {
      final response = await http.get(url, headers: _headers);
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        // Structure: { "code": 200, "msg": "", "snapshotVos": [ { "data": { "totalAssetOfBtc": "0.001" }, "type": "spot", "updateTime": 12345 } ] }
        final List<dynamic> snapshots = data['snapshotVos'] ?? [];
        return snapshots.map((s) {
          return {
            'time': s['updateTime'],
            'totalAssetOfBtc': s['data']['totalAssetOfBtc'],
          };
        }).toList();
      }
    } catch (e) {
      debugPrint('Error getting snapshot: $e');
    }
    return [];
  }

  /// Fetch Deposit History (Mainly for EUR/USDT net invested calc)
  Future<List<Map<String, dynamic>>> getDepositHistory() async {
    if (isMock) {
      return [
        {'amount': '500.0', 'coin': 'EUR', 'insertTime': 1609459200000},
      ];
    }

    // SAPI endpoint for deposit history
    final endpoint = '/sapi/v1/capital/deposit/hisrec';
    final timestamp = DateTime.now().millisecondsSinceEpoch - 10000;
    // status=1 means successful
    final queryString = 'status=1&timestamp=$timestamp';
    final signature = _sign(queryString);
    final url = Uri.parse(
      '$baseUrl$endpoint?$queryString&signature=$signature',
    );

    try {
      final response = await http.get(url, headers: _headers);
      if (response.statusCode == 200) {
        final List<dynamic> list = json.decode(response.body);
        return list.map((e) => Map<String, dynamic>.from(e)).toList();
      } else {
        debugPrint('Error fetch deposit history: ${response.body}');
      }
    } catch (e) {
      debugPrint('Exception deposit history: $e');
    }
    return [];
  }

  /// Calculate Net Deposits (Total Invested in USDT approx)
  Future<double> getNetDeposits() async {
    try {
      final deposits = await getDepositHistory();
      double total = 0.0;
      for (var d in deposits) {
        // Sum up EUR or USDT deposits
        // If EUR, we might need to convert to USDT if the base is USDT,
        // but for 'Net Invested' we usually want it in the currency we view (EUR).
        // The Binance view currently shows "€X".
        // But the balance `_usdtBalance` in the View seems to be summing EUR value?
        // Let's assume we want Total EUR Invested.

        String coin = d['coin'] ?? '';
        double amount = double.tryParse(d['amount'].toString()) ?? 0.0;

        if (coin == 'EUR') {
          total += amount;
        } else if (coin == 'USDT') {
          // If they deposited USDT directly, treat as EUR 1:1 for simplicity
          // or fetch rate if we want perfection.
          // For now, let's assume 1:1 or ignore USDT deposits if the user mainly does EUR SEPA.
          // Let's add it 1:1 as a "stablecoin" investment.
          total += amount;
        }
      }
      return total > 0 ? total : 500.0; // Default fallback
    } catch (e) {
      return 500.0;
    }
  }
}
