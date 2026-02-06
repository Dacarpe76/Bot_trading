import 'package:bot_app/config/app_secrets.dart';
import 'package:bot_app/logic/bot_logic.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:share_plus/share_plus.dart';

class KrakenView extends StatefulWidget {
  const KrakenView({super.key});

  @override
  State<KrakenView> createState() => _KrakenViewState();
}

class _KrakenViewState extends State<KrakenView> {
  BotLogic? _bot;
  bool _showLogs = false;

  @override
  void initState() {
    super.initState();
    // Auto-init with keys from AppSecrets (Assumed unlocked by AuthPage)
    _bot = BotLogic(
      apiKey: AppSecrets.krakenApiKey,
      secretKey: AppSecrets.krakenSecretKey,
    );
    _bot!.start();
  }

  @override
  void dispose() {
    _bot?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<BotState>(
      stream: _bot!.stateStream,
      initialData: BotState.initial(),
      builder: (context, snapshot) {
        final state = snapshot.data!;
        return SingleChildScrollView(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Info Card
              Card(
                color: Colors.indigo.shade900,
                child: Padding(
                  padding: const EdgeInsets.all(24.0),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Text(
                            "KRAKEN EQUITY",
                            style: TextStyle(color: Colors.white70),
                          ),
                          const SizedBox(width: 8),
                          IconButton(
                            icon: const Icon(
                              Icons.refresh,
                              color: Colors.white70,
                              size: 20,
                            ),
                            onPressed: () => _bot!.refresh(),
                            tooltip: "Refresh Balance",
                          ),
                        ],
                      ),
                      Text(
                        "€${state.equity.toStringAsFixed(2)}",
                        style: const TextStyle(
                          fontSize: 40,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                      Text(
                        "${state.profitPercent >= 0 ? '+' : ''}${state.profitPercent.toStringAsFixed(2)}%",
                        style: TextStyle(
                          fontSize: 20,
                          color: state.profitPercent >= 0
                              ? Colors.greenAccent
                              : Colors.redAccent,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        state.status,
                        style: TextStyle(
                          color: state.isPanic
                              ? Colors.redAccent
                              : Colors.greenAccent,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 10),

              // --- PORTFOLIO ---
              if (state.portfolio.isNotEmpty)
                Card(
                  elevation: 2,
                  child: Padding(
                    padding: const EdgeInsets.all(12.0),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              "Current Portfolio",
                              style: TextStyle(fontWeight: FontWeight.bold),
                            ),
                            IconButton(
                              icon: const Icon(
                                Icons.refresh,
                                size: 20,
                                color: Colors.grey,
                              ),
                              onPressed: () => _bot!.refresh(),
                              tooltip: "Refresh Portfolio",
                            ),
                          ],
                        ),
                        const Divider(),
                        ...state.portfolio.entries.map((e) {
                          // e.value is now {'qty': double, 'val': double}
                          final data = e.value as Map<String, dynamic>;
                          double qty = data['qty'] ?? 0.0;
                          double val = data['val'] ?? 0.0;

                          // Filter small dust: Show if Val > 1 OR Qty > 0.0001 (to show assets even if price is missing)
                          if (val < 1.0 && qty < 0.0001) {
                            return const SizedBox.shrink();
                          }

                          // Name mapping
                          String name = e.key;
                          if (name == 'XXBT') name = 'BTC';
                          if (name == 'PAXG' || name == 'XAU') name = 'GOLD';
                          if (name == 'ZEUR') name = 'EUR';

                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 4.0),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  name,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text(
                                      qty.toStringAsFixed(4),
                                      style: const TextStyle(
                                        fontFamily: 'monospace',
                                        fontSize: 12,
                                        color: Colors.black54,
                                      ),
                                    ),
                                    Text(
                                      "€${val.toStringAsFixed(2)}",
                                      style: const TextStyle(
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

              const SizedBox(height: 10),

              // Chart
              if (state.equityHistory.isNotEmpty)
                SizedBox(
                  height: 200,
                  child: LineChart(
                    LineChartData(
                      gridData: const FlGridData(show: false),
                      titlesData: const FlTitlesData(show: false),
                      borderData: FlBorderData(show: false),
                      lineBarsData: [
                        LineChartBarData(
                          spots: state.equityHistory.map((e) {
                            return FlSpot(
                              e['time'].toDouble(),
                              e['value'].toDouble(),
                            );
                          }).toList(),
                          isCurved: true,
                          color: Colors.blueAccent,
                          barWidth: 3,
                          dotData: const FlDotData(show: false),
                          belowBarData: BarAreaData(
                            show: true,
                            color: Colors.blueAccent.withValues(alpha: 0.2),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

              const SizedBox(height: 20),

              // Panic
              ElevatedButton.icon(
                onPressed: () => _bot!.togglePanic(),
                icon: Icon(state.isPanic ? Icons.play_arrow : Icons.warning),
                label: Text(
                  state.isPanic ? "DESACTIVAR PÁNICO" : "PÁNICO: VENDER TODO",
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: state.isPanic ? Colors.green : Colors.red,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.all(15),
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
                    icon: Icon(
                      _showLogs ? Icons.expand_less : Icons.expand_more,
                    ),
                    onPressed: () => setState(() => _showLogs = !_showLogs),
                  ),
                  IconButton(
                    icon: const Icon(Icons.share, size: 20),
                    onPressed: () {
                      if (state.logs.isNotEmpty) {
                        Share.share(
                          state.logs.join('\n'),
                          subject: 'Kraken Bot Logs',
                        );
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
                  height: 200,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.grey),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: ListView.builder(
                    padding: const EdgeInsets.all(8),
                    itemCount: state.logs.length,
                    itemBuilder: (context, index) => Text(
                      state.logs[index],
                      style: const TextStyle(
                        fontSize: 12,
                        fontFamily: 'monospace',
                      ),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
