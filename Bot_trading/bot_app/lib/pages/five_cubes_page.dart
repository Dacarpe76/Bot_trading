import 'package:flutter/material.dart';
import 'package:bot_app/logic/five_cubes/bot_state_manager.dart';

class FiveCubesPage extends StatefulWidget {
  const FiveCubesPage({super.key});

  @override
  State<FiveCubesPage> createState() => _FiveCubesPageState();
}

class _FiveCubesPageState extends State<FiveCubesPage> {
  final BotStateManager _stateManager = BotStateManager();
  Map<String, dynamic> _state = {};

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    final state = await _stateManager.loadState();
    setState(() {
      _state = state;
    });
  }

  @override
  Widget build(BuildContext context) {
    // Determine last run or current status (placeholder as we don't have a live state stream yet)
    final rawAvgBuys = _state['avg_buy_price'];
    final avgBuys = (rawAvgBuys is Map)
        ? Map<String, dynamic>.from(rawAvgBuys)
        : {};

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Card(
            color: Colors.blueGrey,
            child: Padding(
              padding: EdgeInsets.all(16.0),
              child: Column(
                children: [
                  Text(
                    "Daily Schedule: 09:00 AM",
                    style: TextStyle(color: Colors.white, fontSize: 18),
                  ),
                  SizedBox(height: 8),
                  Text(
                    "Service Status: Active (Foreground)",
                    style: TextStyle(color: Colors.white70),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            "Portfolio State (Avg Buy Prices)",
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 10),
          if (avgBuys.isEmpty)
            const Text("No data yet. Wait for daily run or execute manually.")
          else
            ListView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: avgBuys.length,
              itemBuilder: (context, index) {
                final key = avgBuys.keys.elementAt(index);
                final value = avgBuys[key];
                return ListTile(
                  leading: const Icon(Icons.monetization_on),
                  title: Text(key),
                  trailing: Text("\$${value.toString()}"),
                );
              },
            ),
          const SizedBox(height: 20),
          ElevatedButton.icon(
            onPressed: () {
              // Feature for future update: Trigger manual run via Service
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text("Manual run not yet linked to Service"),
                ),
              );
            },
            icon: const Icon(Icons.play_arrow),
            label: const Text("Force Run Now (ToDo)"),
          ),
        ],
      ),
    );
  }
}
