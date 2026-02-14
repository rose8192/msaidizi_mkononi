import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config.dart';

class RasaService {
  // Use the central config for the backend URL
  static const String baseUrl = '${AppConfig.backendBaseUrl}/chat';

  Future<List<String>> sendMessage(String message, String senderId, String language) async {
    try {
      final response = await http.post(
        Uri.parse(baseUrl),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'sender': senderId,
          'message': message,
          'metadata': {'language': language}
        }),
      ).timeout(const Duration(seconds: 40));

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((msg) => msg['text'] as String).toList();
      } else {
        // Enhanced error logging as requested
        print('BACKEND ERROR: Status ${response.statusCode}');
        print('RESPONSE BODY: ${response.body}');
        throw Exception('Server returned status ${response.statusCode}');
      }
    } catch (e) {
      print('CONNECTION ERROR: $e');
      return ['Error: Could not reach Msaidizi Mkononi backend. Please check your connection.'];
    }
  }
}
