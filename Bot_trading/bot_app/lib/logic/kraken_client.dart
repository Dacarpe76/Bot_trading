import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

class KrakenClient {
  final String apiKey;
  final String secretKey;
  final String baseUrl = 'https://api.kraken.com';

  KrakenClient({required this.apiKey, required this.secretKey});

  /// Generates the Kraken signature
  String _getSignature(
    String urlPath,
    Map<String, dynamic> data,
    String nonce,
  ) {
    if (secretKey.isEmpty) return "";

    // POST data string
    String postData = data.entries.map((e) => '${e.key}=${e.value}').join('&');

    // Initial SHA256(nonce + postData)
    var sha256Digest = sha256.convert(utf8.encode(nonce + postData));

    // HMAC-SHA512(path + hash, b64decode(secret))
    List<int> secretBytes = base64Decode(secretKey);
    List<int> pathBytes = utf8.encode(urlPath);
    List<int> hashBytes = sha256Digest.bytes;

    var hmac = Hmac(sha512, secretBytes);
    var signature = hmac.convert(pathBytes + hashBytes);

    return base64Encode(signature.bytes);
  }

  /// Public Request (Ticker)
  Future<Map<String, dynamic>> getTicker(String pair) async {
    final url = Uri.parse('$baseUrl/0/public/Ticker?pair=$pair');
    final response = await http.get(url);

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to load ticker: ${response.body}');
    }
  }

  /// Private Request
  Future<Map<String, dynamic>> _privateRequest(
    String method, [
    Map<String, dynamic>? params,
  ]) async {
    if (apiKey.isEmpty || secretKey.isEmpty) {
      throw Exception("API Keys missing");
    }

    final uri = '$baseUrl/0/private/$method';
    final urlPath = '/0/private/$method';
    final nonce = DateTime.now().millisecondsSinceEpoch.toString();

    Map<String, dynamic> data = {'nonce': nonce};
    if (params != null) {
      data.addAll(params);
    }

    final signature = _getSignature(urlPath, data, nonce);

    final response = await http.post(
      Uri.parse(uri),
      headers: {'API-Key': apiKey, 'API-Sign': signature},
      body: data,
    );

    if (response.statusCode == 200) {
      final jsonResponse = json.decode(response.body);
      if (jsonResponse['error'] != null &&
          (jsonResponse['error'] as List).isNotEmpty) {
        throw Exception("Kraken API Error: ${jsonResponse['error']}");
      }
      return jsonResponse;
    } else {
      throw Exception('Failed private request: ${response.body}');
    }
  }

  /// Get Trade Balance (Equity)
  Future<double> getTradeBalance() async {
    // "eb" = equivalent balance (equity)
    final data = await _privateRequest('TradeBalance', {'asset': 'ZEUR'});
    if (data['result'] != null) {
      return double.tryParse(data['result']['eb'].toString()) ?? 0.0;
    }
    return 0.0;
  }

  /// Get Open Positions / Account Balance
  Future<Map<String, double>> getAccountBalance() async {
    final data = await _privateRequest('Balance');
    Map<String, double> balances = {};

    if (data['result'] != null) {
      (data['result'] as Map).forEach((k, v) {
        double val = double.tryParse(v.toString()) ?? 0.0;
        if (val > 0) {
          balances[k] = val;
        }
      });
    }
    return balances;
  }

  /// Get Detailed Asset Balances (For Smart Liquidity)
  Future<Map<String, double>> getDetailedBalances() async {
    // Alias for getAccountBalance, but ensuring we have it clearly defined
    return await getAccountBalance();
  }

  /// Add Order
  Future<void> addOrder(
    String pair,
    String type,
    String side,
    double volume,
  ) async {
    await _privateRequest('AddOrder', {
      'pair': pair,
      'type': type,
      'ordertype': 'market',
      'volume': volume.toString(),
    });
  }

  /// Get Ledgers (Deposits/Withdrawals)
  Future<Map<String, dynamic>> getLedgers() async {
    return await _privateRequest('Ledgers', {
      'type': 'deposit', // Filter for deposits primarily
      // 'asset': 'ZEUR', // Optional filter
    });
  }

  /// Calculate Net Deposits (Total Invested in EUR)
  Future<double> getNetDeposits() async {
    try {
      final data = await getLedgers();
      double totalDeposits = 0.0;
      if (data['result'] != null && data['result']['ledger'] != null) {
        final ledger = data['result']['ledger'] as Map<String, dynamic>;
        ledger.forEach((key, value) {
          // Check if it's a deposit
          if (value['type'] == 'deposit') {
            double amount = double.tryParse(value['amount'].toString()) ?? 0.0;
            // Very rough assumption: 1 unit = 1 EUR if asset is ZEUR or KFEE
            // We should ideally check 'asset' == 'ZEUR' or 'ZEUR'
            // For MVP, we assume most fiat deposits are EUR
            if (value['asset'] == 'ZEUR' || value['asset'] == 'EUR') {
              totalDeposits += amount;
            }
          }
        });
      }
      return totalDeposits > 0 ? totalDeposits : 500.0; // Fallback to 500 if 0
    } catch (e) {
      // If permission denied or error, fallback
      return 500.0;
    }
  }
}
