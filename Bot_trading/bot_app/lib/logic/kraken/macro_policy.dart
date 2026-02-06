class MacroPolicy {
  static const double pmiStrong = 55.0;
  static const double tipsStrong = 2.0;
  static const double vixStrong = 20.0;

  static const double pmiRisk = 48.0;
  static const double tipsRisk = 2.5;
  static const double vixRisk = 30.0;

  String detectRegimen({
    required double pmi,
    required double tips,
    required double vix,
    double fedRateDelta = 0.0,
  }) {
    // Bull Strong
    if (pmi > pmiStrong &&
        tips < tipsStrong &&
        vix < vixStrong &&
        fedRateDelta < 0.25) {
      return "BULL_STRONG";
    }

    // High Risk
    if (pmi < pmiRisk ||
        tips > tipsRisk ||
        vix > vixRisk ||
        fedRateDelta > 0.5) {
      return "HIGH_RISK";
    }

    return "NEUTRAL";
  }

  Map<String, double> getTargetAllocation(
    String regimen,
    double currentBtcPrice,
    double sma200,
    double rsi,
  ) {
    // Base Allocation
    // If Bear Trend (Price < SMA200) -> Defensive
    bool isBearTrend = (sma200 > 0 && currentBtcPrice < sma200);

    double targetBtc = 0.60;
    double targetGold = 0.40;

    if (isBearTrend) {
      // Defensive Mode
      targetBtc = 0.0; // Flat
      targetGold = 0.80; // High Gold
    }

    // RSI Adjustments
    if (rsi < 30) {
      targetBtc += 0.10;
      targetGold -= 0.10;
    } else if (rsi > 70) {
      targetBtc -= 0.10;
      targetGold += 0.10;
    }

    // Cash Bands (EUR/USD - Fiat)
    double minCash = 0.15;
    double maxCash = 0.40;

    switch (regimen) {
      case "BULL_STRONG":
        minCash = 0.10;
        maxCash = 0.25;
        break;
      case "HIGH_RISK":
        minCash = 0.40;
        maxCash = 0.60;
        break;
      case "NEUTRAL":
      default:
        minCash = 0.15;
        maxCash = 0.40;
        break;
    }

    // Normalize to ensure Cash constraint
    // 1. Calculate implicit cash from BTC+Gold
    double currentRiskAlloc = targetBtc + targetGold;
    double implicitCash = 1.0 - currentRiskAlloc;

    // 2. Clamp Cash
    double finalCash = implicitCash.clamp(minCash, maxCash);

    // 3. Rescale Risk Assets to fit (1 - finalCash)
    double riskBudget = 1.0 - finalCash;
    if (currentRiskAlloc > 0) {
      targetBtc = (targetBtc / currentRiskAlloc) * riskBudget;
      targetGold = (targetGold / currentRiskAlloc) * riskBudget;
    }

    return {'BTC': targetBtc, 'GOLD': targetGold, 'CASH': finalCash};
  }
}
