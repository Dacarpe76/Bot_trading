import 'package:fl_chart/fl_chart.dart';
import 'package:bot_app/config/app_secrets.dart';
import 'package:bot_app/logic/five_cubes/binance_client.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:share_plus/share_plus.dart';

class BinanceView extends StatefulWidget {
  const BinanceView({super.key});

  @override
  State<BinanceView> createState() => _BinanceViewState();
}

class _BinanceViewState extends State<BinanceView> {
  late BinanceClient _client;
  double _usdtBalance = 0.0;
  double _netDeposits = 500.0; // NEW: Track net invested
  bool _isLoading = true;
  bool _isPanic = false;
  String? _error;
  List<String> _logs = [];
  Map<String, dynamic> _portfolio = {}; // Store {'qty':..., 'val':...}
  List<FlSpot> _spots = [];
  bool _showLogs = false;

  @override
  void initState() {
    super.initState();
    _client = BinanceClient(
      apiKey: AppSecrets.binanceApiKey,
      apiSecret: AppSecrets.binanceSecretKey,
      isMock: false,
    );
    _refreshData();
  }

  Future<void> _refreshData() async {
    await _fetchBalance();
    await _loadData();
  }

  Future<void> _fetchBalance() async {
    setState(() => _isLoading = true);
    try {
      // 0. Fetch Net Deposits
      double netDeposits = await _client.getNetDeposits();

      // 2. Fetch EURUSDT Rate
      // 2. Portfolio Calculation involves fetching prices for all
      // We will do one big fetch below.

      // 3. Convert to EUR (Portfolio Calculation)
      double totalEur = 0.0;
      Map<String, dynamic> newPortfolio = {};

      // Fetch ALL balances for Portfolio View
      final allBals = await _client.fetchBalances([]); // Fetch all

      // Get Prices for calc
      final prices = await _client.fetchPrices([
        'BTCEUR',
        'ETHEUR',
        'SOLEUR',
        'PAXGEUR',
        'EURUSDT',
      ]);
      double eurUsdt = prices['EURUSDT'] ?? 1.0;
      if (eurUsdt == 0) eurUsdt = 1.0;

      for (var asset in allBals.keys) {
        double qty = allBals[asset]!;
        if (qty == 0) continue;

        double priceInEur = 0.0;
        if (asset == 'EUR') {
          priceInEur = 1.0;
        } else if (asset == 'USDT') {
          priceInEur = 1.0 / eurUsdt;
        } else {
          priceInEur = prices['${asset}EUR'] ?? 0.0;
        }

        double valEur = qty * priceInEur;
        // Filter dust: Show if Val > 1 OR Qty > 0.0001
        if (valEur > 1.0 || qty > 0.0001) {
          // Filter dust < 1€
          // Store both Qty and Value
          newPortfolio[asset] = {'qty': qty, 'val': valEur};
          totalEur += valEur;
        }
      }

      if (mounted) {
        setState(() {
          _usdtBalance = totalEur; // Update Total Val
          _netDeposits = netDeposits > 0 ? netDeposits : 500.0;
          _portfolio = newPortfolio;
          _isLoading = false;
        });
        _saveToHistory(totalEur);
      }
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _saveToHistory(double val) async {
    final prefs = await SharedPreferences.getInstance();
    List<String> history = prefs.getStringList('binance_history') ?? [];

    // Add current point if it's been > 10 mins since last or list is empty
    int now = DateTime.now().millisecondsSinceEpoch;
    bool shouldAdd = true;
    if (history.isNotEmpty) {
      int lastTime = int.parse(history.last.split('|')[0]);
      if (now - lastTime < 600000) shouldAdd = false; // 10 mins
    }

    if (shouldAdd) {
      history.add("$now|$val");
      if (history.length > 100) history.removeAt(0);
      await prefs.setStringList('binance_history', history);
      _parseHistory(history);
    }
  }

  Future<void> _loadData() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _logs = prefs.getStringList('binance_logs') ?? ["No logs yet"];
    });

    // Try fetching from API (Account Snapshot)
    try {
      List<Map<String, dynamic>> snapshot = await _client.getAccountSnapshot();
      if (snapshot.isNotEmpty) {
        // We have API data! Conver to FlSpot
        // Problem: Data is in BTC. We need EUR.
        // Approximation: Use current EUR/BTC rate? Or current Total EUR / current Total BTC?
        // Let's use: (Snapshot BTC) * (Current EUR/BTC Price).
        // It's not perfect historical accuracy but shows trend.

        double btcEurPrice = 40000.0; // Default
        // Fetch current price
        try {
          final p = await _client.fetchPrices(['BTCEUR']);
          if (p['BTCEUR'] != null) btcEurPrice = p['BTCEUR']!;
        } catch (e) {
          debugPrint("Error fetching price for $btcEurPrice: $e");
        }

        List<FlSpot> spots = [];
        for (var s in snapshot) {
          double btcVal =
              double.tryParse(s['totalAssetOfBtc'].toString()) ?? 0.0;
          double eurVal = btcVal * btcEurPrice;
          spots.add(FlSpot(s['time'].toDouble(), eurVal));
        }
        setState(() => _spots = spots);
        return;
      }
    } catch (e) {
      debugPrint("API Snapshot failed, falling back to local: $e");
    }

    // Fallback to Local History
    setState(() {
      List<String> history = prefs.getStringList('binance_history') ?? [];
      _parseHistory(history);
    });
  }

  void _parseHistory(List<String> history) {
    List<FlSpot> spots = [];
    for (var h in history) {
      final parts = h.split('|');
      if (parts.length == 2) {
        spots.add(FlSpot(double.parse(parts[0]), double.parse(parts[1])));
      }
    }
    setState(() => _spots = spots);
  }

  Future<void> _triggerPanic() async {
    setState(() => _isPanic = true);
    // Sell All Logic (BTC, ETH, SOL, PAXG)
    final assets = ['BTC', 'ETH', 'SOL', 'PAXG'];
    for (var asset in assets) {
      // 1. Get Balance
      final bals = await _client.fetchBalances([asset]);
      double qty = bals[asset] ?? 0.0;
      if (qty > 0.0001) {
        // Min dust
        // 2. Sell
        await _client.placeMarketOrder('${asset}USDT', 'SELL', qty);
      }
    }
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text("🚨 Panic Sell Executed! Sold all assets to USDT."),
      ),
    );
    _refreshData(); // Updates balance
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Info Card with Gold Theme
          Card(
            color: const Color(0xFFC5A028), // Gold/Mustard color
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Text(
                        "BINANCE EQUITY",
                        style: TextStyle(color: Colors.white70),
                      ),
                      const SizedBox(width: 8),
                      IconButton(
                        icon: const Icon(
                          Icons.refresh,
                          color: Colors.white70,
                          size: 20,
                        ),
                        onPressed: _refreshData,
                        tooltip: "Refresh Balance",
                      ),
                    ],
                  ),
                  if (_isLoading)
                    const Padding(
                      padding: EdgeInsets.all(8.0),
                      child: CircularProgressIndicator(color: Colors.white),
                    )
                  else if (_error != null)
                    Text(
                      "Error: $_error",
                      style: const TextStyle(color: Colors.redAccent),
                    )
                  else
                    Text(
                      "€${_usdtBalance.toStringAsFixed(2)}",
                      style: const TextStyle(
                        fontSize: 40,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  Text(
                    "${((_usdtBalance - _netDeposits) / _netDeposits * 100) >= 0 ? '+' : ''}${((_usdtBalance - _netDeposits) / _netDeposits * 100).toStringAsFixed(2)}%",
                    style: TextStyle(
                      fontSize: 20,
                      color:
                          ((_usdtBalance - _netDeposits) /
                                  _netDeposits *
                                  100) >=
                              0
                          ? Colors.greenAccent
                          : Colors.redAccent,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  Text(
                    "Invested: €${_netDeposits.toStringAsFixed(0)}",
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    "Status: Active (Real)",
                    style: TextStyle(
                      color: Colors.white70,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Chart
          if (_spots.isNotEmpty)
            SizedBox(
              height: 200,
              child: LineChart(
                LineChartData(
                  gridData: const FlGridData(show: false),
                  titlesData: const FlTitlesData(show: false),
                  borderData: FlBorderData(show: false),
                  lineBarsData: [
                    LineChartBarData(
                      spots: _spots,
                      isCurved: true,
                      color: const Color(0xFFC5A028),
                      barWidth: 3,
                      dotData: const FlDotData(show: false),
                      belowBarData: BarAreaData(
                        show: true,
                        color: const Color(0xFFC5A028).withValues(alpha: 0.2),
                      ),
                    ),
                  ],
                ),
              ),
            )
          else
            const Center(
              child: Text(
                "Waiting for data points...",
                style: TextStyle(color: Colors.grey),
              ),
            ),

          const SizedBox(height: 20),

          // Panic Button
          ElevatedButton.icon(
            onPressed: _triggerPanic,
            icon: Icon(
              _isPanic ? Icons.check_circle : Icons.warning_amber_rounded,
            ), // Use _isPanic
            label: Text(
              _isPanic ? "ESTADO: PÁNICO ACTIVADO" : "PÁNICO: VENDER TODO",
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: _isPanic
                  ? Colors.green
                  : Colors.red, // Visual feedback
              foregroundColor: Colors.white,
              padding: const EdgeInsets.all(15),
            ),
          ),

          const SizedBox(height: 20),

          // --- PORTFOLIO UI ---
          if (_portfolio.isNotEmpty)
            Card(
              color: Colors.grey.shade900,
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          "Five Cubes Alloc",
                          style: TextStyle(
                            color: Colors.tealAccent,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        IconButton(
                          icon: const Icon(
                            Icons.refresh,
                            size: 20,
                            color: Colors.white70,
                          ),
                          onPressed: _refreshData,
                          tooltip: "Refresh Portfolio",
                        ),
                      ],
                    ),
                    const Divider(color: Colors.white24),
                    ..._portfolio.entries.map((e) {
                      final data = e.value as Map<String, dynamic>;
                      double qty = data['qty'] ?? 0.0;
                      double val = data['val'] ?? 0.0;

                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 4.0),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              e.key,
                              style: const TextStyle(
                                color: Colors.white70,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  qty.toStringAsFixed(4),
                                  style: const TextStyle(
                                    color: Colors.white54,
                                    fontSize: 12,
                                    fontFamily: 'monospace',
                                  ),
                                ),
                                Text(
                                  "€${val.toStringAsFixed(2)}",
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontFamily: 'monospace',
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      );
                    }),
                  ],
                ),
              ),
            ),

          const SizedBox(height: 20),

          // Logs Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                "Logs",
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              IconButton(
                icon: Icon(_showLogs ? Icons.expand_less : Icons.expand_more),
                onPressed: () => setState(() => _showLogs = !_showLogs),
              ),
              IconButton(
                icon: const Icon(Icons.share, size: 20),
                onPressed: () {
                  if (_logs.isNotEmpty) {
                    Share.share(_logs.join('\n'), subject: 'Binance Bot Logs');
                  }
                },
                tooltip: "Share Logs",
              ),
            ],
          ),
          const Divider(),

          // Logs Area
          if (_showLogs)
            Container(
              height: 300,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.grey),
                borderRadius: BorderRadius.circular(8),
              ),
              child: ListView.builder(
                padding: const EdgeInsets.all(8),
                itemCount: _logs.length,
                itemBuilder: (context, index) => Padding(
                  padding: const EdgeInsets.only(bottom: 8.0),
                  child: Text(
                    _logs[index],
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
