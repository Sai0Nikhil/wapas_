import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/app_models.dart';

class ApiService {
  // Support both USB ADB reverse (127.0.0.1:8000) and Local Wi-Fi LAN
  static const List<String> baseUrls = [
    "http://127.0.0.1:8000",
    "http://10.150.24.87:8000",
    "http://10.0.2.2:8000",
  ];

  static String _activeBaseUrl = baseUrls[0];

  static Future<String> getActiveBaseUrl() async {
    for (final url in baseUrls) {
      try {
        final res = await http.get(Uri.parse("$url/health")).timeout(const Duration(milliseconds: 1500));
        if (res.statusCode == 200) {
          _activeBaseUrl = url;
          return url;
        }
      } catch (_) {}
    }
    return _activeBaseUrl;
  }

  static Future<bool> isConnected() async {
    try {
      final url = await getActiveBaseUrl();
      final res = await http.get(Uri.parse("$url/health")).timeout(const Duration(seconds: 2));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Call live Sarvam-105B backend to parse spoken transactions & check duplicate accounts
  static Future<Map<String, dynamic>> parseVoiceWithSarvam(
    String spokenText,
    List<KhataCustomer> existingCustomers,
  ) async {
    final url = await getActiveBaseUrl();
    final endpoint = Uri.parse("$url/khata/voice-parse");

    final payload = {
      "text": spokenText,
      "existing_customers": existingCustomers.map((c) => {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "totalDue": c.totalDue,
      }).toList(),
    };

    try {
      final response = await http.post(
        endpoint,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode(payload),
      ).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      } else {
        throw Exception("Server returned ${response.statusCode}: ${response.body}");
      }
    } catch (e) {
      debugPrint("API call to Sarvam failed: $e, falling back to local heuristic");
      rethrow;
    }
  }

  /// Fetch live recovery cases from SQLite backend
  static Future<List<dynamic>> fetchCases() async {
    final url = await getActiveBaseUrl();
    final res = await http.get(Uri.parse("$url/cases")).timeout(const Duration(seconds: 4));
    if (res.statusCode == 200) {
      return jsonDecode(res.body) as List<dynamic>;
    }
    return [];
  }

  /// Call live Sarvam-105B backend for conversational retail Copilot
  static Future<Map<String, dynamic>> chatWithCopilot(
    String message,
    String language,
  ) async {
    final url = await getActiveBaseUrl();
    final endpoint = Uri.parse("$url/copilot/chat");

    final payload = {
      "message": message,
      "language": language,
    };

    try {
      final response = await http.post(
        endpoint,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode(payload),
      ).timeout(const Duration(seconds: 25));

      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      } else {
        throw Exception("Server returned ${response.statusCode}: ${response.body}");
      }
    } catch (e) {
      debugPrint("API call to Copilot failed: $e");
      rethrow;
    }
  }
}
