import 'package:bot_app/logic/daily_bot_runner.dart';
import 'package:bot_app/pages/auth_page.dart';
import 'package:bot_app/pages/binance_view.dart';
import 'package:bot_app/pages/kraken_view.dart';
import 'package:flutter/material.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);

    // Check if strategy needs to run (once per 24h)
    DailyBotRunner().checkAndRunOnOpen();
  }

  void _logout() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (context) => const AuthPage()),
    );
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Bot Trading Native"),
        backgroundColor: Colors.blueGrey.shade900,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.flash_on, color: Colors.orangeAccent),
            tooltip: 'Force Run Strategy',
            onPressed: () => DailyBotRunner().forceRun(context),
          ),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: Colors.tealAccent,
          labelColor: Colors.tealAccent,
          unselectedLabelColor: Colors.white70,
          tabs: const [
            Tab(text: "KRAKEN (Macro)", icon: Icon(Icons.trending_up)),
            Tab(
              text: "BINANCE (5 Cubes)",
              icon: Icon(Icons.hexagon, color: Color(0xFFFFD700)),
            ), // Gold Icon
          ],
        ),
      ),
      body: SafeArea(
        child: TabBarView(
          controller: _tabController,
          children: const [KrakenView(), BinanceView()],
        ),
      ),
    );
  }
}
