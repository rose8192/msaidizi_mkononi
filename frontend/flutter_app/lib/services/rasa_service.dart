import 'dart:convert';
import 'package:http/http.dart' as http;

class RasaService {
  // CHANGE THIS to your Computer's IP Address (run 'ipconfig' to find it)
  // Example: 'http://192.168.1.50:5005/webhooks/rest/webhook'
  static const String baseUrl = 'http://10.5.50.79:5005/webhooks/rest/webhook';

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
      );

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        return data.map((msg) => msg['text'] as String).toList();
      } else {
        throw Exception('Failed to connect to Rasa');
      }
    } catch (e) {
      return ['Error: Could not reach Msaidizi Mkononi backend. Please check your connection.'];
    }
  }
}
