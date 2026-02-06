import 'package:bot_app/logic/five_cubes/binance_client.dart';
import 'package:bot_app/logic/five_cubes/bot_state_manager.dart';
import 'package:bot_app/logic/five_cubes/indicator_client.dart';

class FiveCubesEngine {
  final BinanceClient binance;
  final IndicatorClient indicators;
  final BotStateManager stateManager;

  FiveCubesEngine({
    required this.binance,
    required this.indicators,
    required this.stateManager,
  });

  static const double fearThreshold = 30.0;
  static const double dxyThreshold = 103.0;
  static const double pmiThreshold = 50.0;

  Future<String> runDailyRoutine() async {
    final sb = StringBuffer();
    sb.writeln("--- Five Cubes Routine Started ---");

    // 1. Fetch Indicators & Determine Mode
    final fng = await indicators.getFearAndGreed();
    final dxy = await indicators.getDXY();
    final pmi = await indicators.getPMI();

    sb.writeln("Indicators: F&G=$fng, DXY=$dxy, PMI=$pmi");

    String mode = "SHIELD";
    if (fng < fearThreshold) {
      mode = "ATTACK";
    } else if (dxy < dxyThreshold && pmi > pmiThreshold) {
      mode = "CRUISE";
    }

    sb.writeln("Selected Mode: $mode");

    // 2. Fetch Portfolio (ALL assets for Smart Liquidity)
    // Pass empty list to fetch EVERYTHING
    final balances = await binance.fetchBalances([]);

    // Define Core Assets
    final coreAssets = ['BTC', 'ETH', 'SOL', 'PAXG', 'EUR'];
    final otherAssets = balances.keys
        .where((k) => !coreAssets.contains(k))
        .toList();

    // Calculate Total USD Value
    // Fetch Prices
    final prices = await binance.fetchPrices([
      'BTCEUR',
      'ETHEUR',
      'SOLEUR',
      'PAXGEUR',
    ]);
    prices['EUREUR'] = 1.0;

    double totalValue = 0.0;
    Map<String, double> portfolio = {};

    for (var asset in coreAssets) {
      double qty = balances[asset] ?? 0.0;
      double price = (asset == 'EUR') ? 1.0 : (prices['${asset}EUR'] ?? 0.0);
      double val = qty * price;
      portfolio[asset] = val;
      totalValue += val;
      sb.writeln("  - $asset: $qty (€${val.toStringAsFixed(2)})");
    }

    // Calculate "Other" Assets Value (Liquidity)
    // We need prices for them in EUR.
    // Making a batch request for likely others might be too heavy?
    // For now, let's fetch individual prices for significant others (>0 qty)
    Map<String, double> otherPrices = {};
    for (var other in otherAssets) {
      // Ignore very small dust?
      if ((balances[other] ?? 0) < 0.0001) continue;

      try {
        // Try finding EUR pair
        var pMap = await binance.fetchPrices(['${other}EUR']);
        double p = pMap['${other}EUR'] ?? 0.0;
        if (p > 0) {
          otherPrices[other] = p;
          double val = (balances[other]! * p);
          totalValue += val; // Treat as Cash Equivalent
          sb.writeln(
            "  - [OTHER] $other: ${balances[other]} (€${val.toStringAsFixed(2)}) -> Liquidity",
          );
        }
      } catch (e) {
        // Pair might not exist
      }
    }
    sb.writeln("Total Portfolio Value: €${totalValue.toStringAsFixed(2)}");

    // 3. Calculate Trades
    Map<String, double> targetRatios;
    switch (mode) {
      case 'ATTACK':
        targetRatios = {
          'SOL': 0.40,
          'ETH': 0.30,
          'BTC': 0.30,
          'PAXG': 0.0,
          'EUR': 0.0,
        };
        break;
      case 'CRUISE':
        targetRatios = {
          'BTC': 0.40,
          'ETH': 0.30,
          'SOL': 0.30,
          'PAXG': 0.0,
          'EUR': 0.0,
        };
        break;
      case 'SHIELD':
      default:
        targetRatios = {
          'BTC': 0.40,
          'PAXG': 0.40,
          'EUR': 0.20,
          'ETH': 0.0,
          'SOL': 0.0,
        };
        break;
    }

    // Load State for Zero Loss
    final state = await stateManager.loadState();
    final avgBuyPrices = state['avg_buy_price'] ?? {};

    // Execute logic
    // Sells first to free up EUR (Core Assets)
    for (var asset in coreAssets) {
      if (asset == 'EUR') continue;

      double targetPct = targetRatios[asset] ?? 0.0;
      // ... (Rest of Sell Logic is same, relying on coreAssets loop)
      double targetUsd = totalValue * targetPct;
      double currentUsd = portfolio[asset] ?? 0.0;
      double diffUsd = targetUsd - currentUsd;
      double price = prices['${asset}EUR'] ?? 0.0;

      if (price == 0) continue;

      if (diffUsd < -10) {
        // Sell threshold $10
        // CHECK ZERO LOSS if not SHIELD mode
        bool isDefensive = (mode == 'SHIELD');
        double avgBuy = (avgBuyPrices[asset] ?? 0.0).toDouble();

        if (!isDefensive && avgBuy > 0 && price < avgBuy) {
          sb.writeln(
            "  [HOLD] Zero Loss Protection for $asset (Price $price < Avg $avgBuy)",
          );
          continue;
        }

        double amountToSell = diffUsd.abs() / price;
        sb.writeln("  [EXECUTE] SELL $amountToSell $asset");
        await binance.placeMarketOrder('${asset}EUR', 'SELL', amountToSell);
      }
    }

    // Buys second (Using EUR + Smart Liquidity)
    for (var asset in coreAssets) {
      if (asset == 'EUR') continue;

      double targetPct = targetRatios[asset] ?? 0.0;
      double targetUsd = totalValue * targetPct;
      double currentUsd = portfolio[asset] ?? 0.0;
      // Note: currentUsd is stale if we sold, but strictly speaking we are buying the *deficit*
      // If we held (Zero Loss), currentUsd is higher than target, so diffUsd is negative, so we won't buy. Correct.

      double diffUsd = targetUsd - currentUsd;
      double price = prices['${asset}EUR'] ?? 0.0;

      if (diffUsd > 10) {
        // Need to BUY. Check Liquidity sources.

        // 1. Check "Other" Assets (Smart Liquidity)
        for (var other in otherAssets) {
          double otherVal = (balances[other] ?? 0) * (otherPrices[other] ?? 0);
          if (otherVal > 10) {
            if (asset == 'BTC' || asset == 'ETH' || asset == 'BNB') {
              String pair = '$other$asset';
              try {
                var pMap = await binance.fetchPrices([pair]);
                double pairPrice = pMap[pair] ?? 0.0;
                if (pairPrice > 0) {
                  double valToMoveEur = (diffUsd < otherVal)
                      ? diffUsd
                      : otherVal;
                  double qtyOther = valToMoveEur / (otherPrices[other]!);

                  sb.writeln(
                    "  [SMART] Swapping $other -> $asset directly ($pair). Qty: $qtyOther",
                  );

                  bool success = await binance.placeMarketOrder(
                    pair,
                    'SELL',
                    qtyOther,
                  );

                  if (success) {
                    diffUsd -= valToMoveEur;
                    balances[other] = (balances[other] ?? 0) - qtyOther;
                    portfolio[asset] = (portfolio[asset] ?? 0) + valToMoveEur;
                  }
                }
              } catch (e) {
                // Direct pair likely doesn't exist
              }
            }
          }
          if (diffUsd <= 10) break;
        }

        // 2. Buy with EUR if still needed
        if (diffUsd > 10) {
          double amountToBuy = diffUsd / price;
          sb.writeln("  [EXECUTE] BUY $amountToBuy $asset");
          bool success = await binance.placeMarketOrder(
            '${asset}EUR',
            'BUY',
            amountToBuy,
          );
          if (success) {
            // Update Avg Buy Price
            // Simplified: Just updating to current price. complex weighted logic requires more state management.
            Map<String, dynamic> newState = Map.from(state);
            Map<String, dynamic> newAvgMap = Map.from(
              newState['avg_buy_price'] ?? {},
            );
            newAvgMap[asset] = price;
            newState['avg_buy_price'] = newAvgMap;
            await stateManager.saveState(newState);
          }
        }
      }
    }

    sb.writeln("--- Routine Finished ---");
    return sb.toString();
  }
}
