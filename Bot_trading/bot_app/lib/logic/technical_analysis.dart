class TechnicalAnalysis {
  /// Calculate Simple Moving Average (SMA)
  static List<double?> calculateSMA(List<double> closePrices, int period) {
    List<double?> sma = List.filled(closePrices.length, null);
    if (closePrices.length < period) return sma;

    for (int i = period - 1; i < closePrices.length; i++) {
      double sum = 0;
      for (int j = 0; j < period; j++) {
        sum += closePrices[i - j];
      }
      sma[i] = sum / period;
    }
    return sma;
  }

  /// Calculate Relative Strength Index (RSI)
  /// Uses the Wilder's Smoothing method typically (or simple SMA for variations).
  /// Standard RSI uses Smoothed Moving Average (SMMA).
  static List<double?> calculateRSI(List<double> closePrices, int period) {
    List<double?> rsiValues = List.filled(closePrices.length, null);
    if (closePrices.length < period + 1) return rsiValues;

    double gainSum = 0.0;
    double lossSum = 0.0;

    // 1. Initial Calculation (Simple Average of Gains/Losses)
    for (int i = 1; i <= period; i++) {
      double change = closePrices[i] - closePrices[i - 1];
      if (change > 0) {
        gainSum += change;
      } else {
        lossSum += -change; // Make positive
      }
    }

    double avgGain = gainSum / period;
    double avgLoss = lossSum / period;

    // First RSI
    double rs = (avgLoss == 0) ? 100 : avgGain / avgLoss;
    rsiValues[period] = 100 - (100 / (1 + rs));

    // 2. Smoothed Calculation for subsequent points
    for (int i = period + 1; i < closePrices.length; i++) {
      double change = closePrices[i] - closePrices[i - 1];
      double currentGain = (change > 0) ? change : 0.0;
      double currentLoss = (change < 0) ? -change : 0.0;

      // Wilder's Smoothing
      avgGain = ((avgGain * (period - 1)) + currentGain) / period;
      avgLoss = ((avgLoss * (period - 1)) + currentLoss) / period;

      if (avgLoss == 0) {
        rsiValues[i] = 100.0;
      } else {
        double rs = avgGain / avgLoss;
        rsiValues[i] = 100 - (100 / (1 + rs));
      }
    }

    return rsiValues;
  }
}
