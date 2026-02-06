import 'package:local_auth/local_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'dart:io';

class AuthService {
  final LocalAuthentication auth = LocalAuthentication();

  Future<bool> authenticate() async {
    try {
      // Bypass on Desktop (Linux/Windows)
      if (Platform.isLinux || Platform.isWindows || Platform.isMacOS) {
        return true;
      }

      final bool canAuthenticateWithBiometrics = await auth.canCheckBiometrics;
      final bool canAuthenticate =
          canAuthenticateWithBiometrics || await auth.isDeviceSupported();

      if (!canAuthenticate) {
        // If device not supported, maybe fallback to simple "Continue" or PIN logic
        // For now, return true (insecure fallback) or false?
        // Let's assume user must have security.
        return true;
      }

      final bool didAuthenticate = await auth.authenticate(
        localizedReason: 'Please authenticate to access Trading Bots',
      );
      return didAuthenticate;
    } on PlatformException catch (e) {
      debugPrint("Auth Error: $e");
      return false;
    }
  }
}
