import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'dart:io';
import 'package:flutter/foundation.dart';

class NotificationHelper {
  static final FlutterLocalNotificationsPlugin flutterLocalNotificationsPlugin =
      FlutterLocalNotificationsPlugin();

  static Future<void> initialize() async {
    // Skip on Desktop for now to avoid crashes
    if (Platform.isLinux || Platform.isWindows || Platform.isMacOS) return;

    const AndroidInitializationSettings initializationSettingsAndroid =
        AndroidInitializationSettings(
          'ic_bg_service_small',
        ); // Make sure this icon exists or use @mipmap/ic_launcher

    final InitializationSettings initializationSettings =
        InitializationSettings(android: initializationSettingsAndroid);

    await flutterLocalNotificationsPlugin.initialize(initializationSettings);
  }

  static Future<void> showNotification(String title, String body) async {
    if (Platform.isLinux || Platform.isWindows || Platform.isMacOS) {
      debugPrint("Notification (Skipped on Desktop): $title - $body");
      return;
    }

    const AndroidNotificationDetails androidPlatformChannelSpecifics =
        AndroidNotificationDetails(
          'daily_report',
          'Daily Reports',
          channelDescription: 'Daily trading bot reports',
          importance: Importance.max,
          priority: Priority.high,
        );
    const NotificationDetails platformChannelSpecifics = NotificationDetails(
      android: androidPlatformChannelSpecifics,
    );

    await flutterLocalNotificationsPlugin.show(
      0,
      title,
      body,
      platformChannelSpecifics,
    );
  }
}
