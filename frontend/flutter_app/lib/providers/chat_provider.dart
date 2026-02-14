import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/chat_message.dart';
import '../services/rasa_service.dart';

class ChatProvider with ChangeNotifier {
  final List<ChatMessage> _messages = [];
  final RasaService _rasaService = RasaService();
  String _language = 'en';
  bool _isTyping = false;

  List<ChatMessage> get messages => _messages;
  String get language => _language;
  bool get isTyping => _isTyping;

  ChatProvider() {
    _loadSettings();
    _addInitialMessage();
  }

  void _addInitialMessage() {
    if (_messages.isEmpty) {
      _messages.add(ChatMessage(
        text: _language == 'sw' 
            ? "Habari! Mimi ni **Msaidizi Mkononi**, msaidizi wako wa uraia nchini Kenya. Nawezaje kukusaidia leo?\n\nJaribu kuuliza kuhusu:\n• **Maombi ya Pasipoti**\n• **Urejeshaji wa Kitambulisho**\n• **Leseni ya Udereva**" 
            : "Habari! I am **Msaidizi Mkononi**, your Kenyan civic assistant. How can I help you today?\n\nTry asking about:\n• **Passport Application**\n• **ID Renewal**\n• **Driving License**",
        isUser: false,
        timestamp: DateTime.now(),
      ));
    }
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _language = prefs.getString('language') ?? 'en';
    notifyListeners();
  }

  Future<void> setLanguage(String lang) async {
    _language = lang;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', lang);
    notifyListeners();
  }

  Future<void> sendMessage(String text) async {
    if (text.trim().isEmpty) return;

    final userMessage = ChatMessage(
      text: text,
      isUser: true,
      timestamp: DateTime.now(),
    );
    _messages.add(userMessage);
    _isTyping = true;
    notifyListeners();

    final botReplies = await _rasaService.sendMessage(text, "flutter_user", _language);
    
    _isTyping = false;
    for (var reply in botReplies) {
      _messages.add(ChatMessage(
        text: reply,
        isUser: false,
        timestamp: DateTime.now(),
      ));
    }
    notifyListeners();
  }
}
