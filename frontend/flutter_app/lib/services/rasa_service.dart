import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

class RasaService {
  // Use the central config for the backend URL
  static String get baseUrl => '${AppConfig.backendBaseUrl}/chat';

  Future<List<String>> sendMessage(String message, String senderId, String language) async {
    final url = baseUrl;
    try {
      debugPrint('SENDING TO: $url');
      final response = await http.post(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'sender': senderId,
          'message': message,
          'metadata': {'language': language}
        }),
      ).timeout(const Duration(seconds: 60));

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((msg) => msg['text'] as String).toList();
      } else {
        // Enhanced error logging as requested
        debugPrint('BACKEND ERROR: Status ${response.statusCode}');
        debugPrint('RESPONSE BODY: ${response.body}');
        try {
          final List<dynamic> data = jsonDecode(response.body);
          if (data.isNotEmpty && data[0]['text'] != null) {
            return [data[0]['text'] as String];
          }
        } catch (_) {}
        return ['Error: Server returned status ${response.statusCode}. Please try again later.'];
      }
    } catch (e) {
      debugPrint('CONNECTION ERROR: $e');
      return ['Error: Could not reach Msaidizi Mkononi backend. Details: $e'];
    }
  }
}
