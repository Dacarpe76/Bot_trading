import 'dart:convert';
import 'package:bot_app/config/app_secrets.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:crypto/crypto.dart';

class KrakenClient {
  final String _baseUrl = 'https://api.kraken.com';
  final String _apiKey = AppSecrets.krakenApiKey;
  final String _apiSecret = AppSecrets.krakenSecretKey;

  // MOCK MODE: Set to false to enable real trading
  final bool isMock = true;

  KrakenClient();

  /// Generates the Kraken API signature
  String _generateSignature(String path, String nonce, String postData) {
    final List<int> pathBytes = utf8.encode(path);
    final List<int> noncePostBytes = utf8.encode(nonce + postData);
    final List<int> sha256Hash = sha256.convert(noncePostBytes).bytes;

    final List<int> secretBytes = base64.decode(_apiSecret);

    final List<int> hmacInput = [...pathBytes, ...sha256Hash];
    final Hmac hmacSha512 = Hmac(sha512, secretBytes);
    final Digest digest = hmacSha512.convert(hmacInput);

    return base64.encode(digest.bytes);
  }

  /// Makes a private API call
  Future<dynamic> _privatePost(
    String endPoint,
    Map<String, String> body,
  ) async {
    if (isMock) {
      debugPrint('[MOCK] Kraken Private Call: $endPoint with $body');
      return {}; // return empty success-like
    }

    final String nonce = DateTime.now().millisecondsSinceEpoch.toString();
    body['nonce'] = nonce;
    final String postData = body.keys
        .map((key) => '$key=${body[key]}')
        .join('&');
    final String path = '/0/private/$endPoint';
    final String signature = _generateSignature(path, nonce, postData);

    final response = await http.post(
      Uri.parse('$_baseUrl$path'),
      headers: {
        'API-Key': _apiKey,
        'API-Sign': signature,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body,
    );

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception(
        'Kraken API Error: ${response.statusCode} - ${response.body}',
      );
    }
  }

  Future<Map<String, double>> fetchBalances() async {
    if (isMock) {
      return {'ZEUR': 1000.0, 'XXBT': 0.05, 'PAXG': 2.0};
    }

    final response = await _privatePost('Balance', {});
    final result = response['result'] as Map<String, dynamic>;

    Map<String, double> balances = {};
    result.forEach((key, value) {
      balances[key] = double.parse(value);
    });
    return balances;
  }

  // Add other methods (Ticker, AddOrder) as needed per strategy requirements
}
