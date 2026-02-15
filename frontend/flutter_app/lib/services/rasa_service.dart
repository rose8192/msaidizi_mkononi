import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../config.dart';

class RasaService {
  // Use the central config for the backend URL
  static String get baseUrl => '${AppConfig.backendBaseUrl}/chat';

  Future<List<String>> sendMessage(String message, String senderId, String language) async {
    // Correct Endpoint: Flutter calls Flask /chat, NOT Rasa directly
    final url = baseUrl; 
    try {
      debugPrint('SENDING TO FLASK PROXY: $url');
      final response = await http.post(
        Uri.parse(url),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'sender': senderId,
          'message': message,
          // metadata is optional, but Flask proxy expects 'sender' and 'message'
        }),
      ).timeout(const Duration(seconds: 60));

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        // Rasa returns a list of messages like [{"text": "Hello"}, {"text": "How can I help?"}]
        return data.map((msg) => msg['text'] as String).toList();
      } else {
        debugPrint('BACKEND ERROR: Status ${response.statusCode}');
        debugPrint('RESPONSE BODY: ${response.body}');
        return ['Sorry, I am having trouble connecting to the AI engine. (${response.statusCode})'];
      }
    } catch (e) {
      debugPrint('CONNECTION ERROR: $e');
      return ['Could not reach the server. Please check your internet connection.'];
    }
  }
}
