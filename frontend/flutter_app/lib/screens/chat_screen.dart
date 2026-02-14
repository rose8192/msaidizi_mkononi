import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import '../providers/chat_provider.dart';
import '../widgets/chat_bubble.dart';
import '../config.dart';
import '../main.dart'; // To access theme colors
import '../admin_dashboard.dart'; // To access AdminDashboard

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  int _adminTapCount = 0;
  DateTime? _lastTapTime;

  // Voice implementation
  late stt.SpeechToText _speech;
  late FlutterTts _tts;
  bool _isListening = false;
  String _lastWords = '';

  @override
  void initState() {
    super.initState();
    _speech = stt.SpeechToText();
    _tts = FlutterTts();
    _initTts();
  }

  Future<void> _initTts() async {
    try {
      await _tts.setLanguage("sw-KE"); // Default to Swahili
      await _tts.setSpeechRate(0.5);
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);
    } catch (e) {
      debugPrint("Error initializing TTS: $e");
    }
  }

  Future<void> _listen() async {
    if (!_isListening) {
      // Check and request microphone permission
      var status = await Permission.microphone.status;
      if (status.isDenied) {
        status = await Permission.microphone.request();
        if (status.isDenied) {
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('Microphone permission is required for voice input.')),
            );
          }
          return;
        }
      }

      try {
        bool available = await _speech.initialize(
          onStatus: (val) {
            if (val == 'done' || val == 'notListening') {
              if (mounted) setState(() => _isListening = false);
            }
            debugPrint('onStatus: $val');
          },
          onError: (val) {
            debugPrint('onError: $val');
            if (mounted) setState(() => _isListening = false);
          },
        );
        if (available) {
          if (mounted) setState(() => _isListening = true);
          final chatProvider = Provider.of<ChatProvider>(context, listen: false);
          _speech.listen(
            onResult: (val) {
              if (mounted) {
                setState(() {
                  _lastWords = val.recognizedWords;
                  if (val.finalResult) {
                    _isListening = false;
                    _controller.text = _lastWords;
                    _handleSubmitted(_lastWords, chatProvider);
                  }
                });
              }
            },
            localeId: chatProvider.language == 'sw' ? 'sw_KE' : 'en_KE',
          );
        }
      } catch (e) {
        debugPrint("Error initializing speech recognition: $e");
        if (mounted) setState(() => _isListening = false);
      }
    } else {
      if (mounted) setState(() => _isListening = false);
      _speech.stop();
    }
  }

  Future<void> _speak(String text) async {
    try {
      final chatProvider = Provider.of<ChatProvider>(context, listen: false);
      // Strip markdown for cleaner speech
      String cleanText = text.replaceAll(RegExp(r'\*\*|\*|__|_|#'), '');
      await _tts.setLanguage(chatProvider.language == 'sw' ? "sw-KE" : "en-US");
      await _tts.speak(cleanText);
    } catch (e) {
      debugPrint("Error speaking: $e");
    }
  }

  void _handleSubmitted(String text, ChatProvider chatProvider) async {
    if (text.trim().isEmpty) return;
    _controller.clear();
    await chatProvider.sendMessage(text);
    
    // Speak the last message if it's from the bot
    if (chatProvider.messages.isNotEmpty && !chatProvider.messages.last.isUser) {
      _speak(chatProvider.messages.last.text);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    _tts.stop();
    _speech.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final chatProvider = Provider.of<ChatProvider>(context);
    _scrollToBottom();

    return Scaffold(
      appBar: AppBar(
        leadingWidth: 120,
        leading: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(width: 4),
            IconButton(
              icon: const Icon(FontAwesomeIcons.telegram, size: 24),
              onPressed: _openTelegram,
              padding: const EdgeInsets.symmetric(horizontal: 4),
              constraints: const BoxConstraints(),
              tooltip: 'Telegram Bot',
            ),
            IconButton(
              icon: const Icon(Icons.phonelink_setup, size: 20),
              onPressed: _openUSSD,
              padding: const EdgeInsets.symmetric(horizontal: 4),
              constraints: const BoxConstraints(),
              tooltip: 'USSD Simulator',
            ),
          ],
        ),
        title: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            final now = DateTime.now();
            if (_lastTapTime == null || now.difference(_lastTapTime!) > const Duration(seconds: 2)) {
              _adminTapCount = 1;
            } else {
              _adminTapCount++;
            }
            _lastTapTime = now;

            if (_adminTapCount > 0 && _adminTapCount < 7) {
              ScaffoldMessenger.of(context).hideCurrentSnackBar();
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Admin access: $_adminTapCount/7 taps'),
                  duration: const Duration(milliseconds: 500),
                ),
              );
            }

            if (_adminTapCount >= 7) {
              _adminTapCount = 0; // Reset
              ScaffoldMessenger.of(context).hideCurrentSnackBar();
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const AdminDashboard()),
              );
            }
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Msaidizi Mkononi',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 17),
              ),
              const SizedBox(height: 4),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(height: 2, width: 20, color: Colors.black),
                  Container(height: 2, width: 20, color: kAccentRed),
                  Container(height: 2, width: 20, color: kPrimaryGreen),
                ],
              )
            ],
          ),
        ),
        actions: [
          PopupMenuButton<String>(
            onSelected: (lang) => chatProvider.setLanguage(lang),
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'en', child: Text('English')),
              const PopupMenuItem(value: 'sw', child: Text('Kiswahili')),
            ],
            icon: const Icon(Icons.language),
          ),
        ],
      ),
      drawer: _buildDrawer(),
      floatingActionButton: FloatingActionButton(
        onPressed: _listen,
        backgroundColor: _isListening ? Colors.red : kPrimaryGreen,
        child: Icon(_isListening ? Icons.mic : Icons.mic_none, color: Colors.white),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
              itemCount: chatProvider.messages.length,
              itemBuilder: (context, index) {
                return ChatBubble(message: chatProvider.messages[index]);
              },
            ),
          ),
          if (chatProvider.isTyping)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: _TypingIndicator(),
            ),
          _buildQuickReplies(chatProvider),
          _buildInputArea(chatProvider),
        ],
      ),
    );
  }

  Future<void> _openTelegram() async {
    final url = Uri.parse('https://t.me/${AppConfig.telegramBotUsername}');
    try {
      if (await canLaunchUrl(url)) {
        await launchUrl(url, mode: LaunchMode.externalApplication);
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not launch Telegram. Please ensure it is installed.')),
          );
        }
      }
    } catch (e) {
      debugPrint("Error launching Telegram: $e");
    }
  }

  Future<void> _openUSSD() async {
    final url = Uri.parse(AppConfig.ussdSandboxUrl);
    try {
      if (await canLaunchUrl(url)) {
        await launchUrl(url, mode: LaunchMode.externalApplication);
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not open USSD simulation.')),
          );
        }
      }
    } catch (e) {
      debugPrint("Error launching USSD: $e");
    }
  }

  Widget _buildDrawer() {
    return Drawer(
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(color: kPrimaryGreen),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: const [
                CircleAvatar(backgroundColor: Colors.white, radius: 30, child: Icon(Icons.account_balance, color: kPrimaryGreen)),
                SizedBox(height: 10),
                Text('Msaidizi Mkononi', style: TextStyle(color: Colors.white, fontSize: 20)),
                Text('Civic Assistant', style: TextStyle(color: Colors.white70)),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(FontAwesomeIcons.telegram, color: Colors.blue),
            title: const Text('Chat on Telegram'),
            onTap: () {
              Navigator.pop(context);
              _openTelegram();
            },
          ),
          ListTile(
            leading: const Icon(Icons.phone_android, color: Colors.orange),
            title: const Text('USSD Simulator'),
            onTap: () {
              Navigator.pop(context);
              _openUSSD();
            },
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('About'),
            onTap: () {
              Navigator.pop(context);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildQuickReplies(ChatProvider provider) {
    final List<String> quickReplies = [
      "Renew ID Card",
      "Passport Info",
      "Driving License",
      "KRA PIN Help"
    ];

    return Container(
      height: 45,
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        itemCount: quickReplies.length,
        itemBuilder: (context, i) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: OutlinedButton(
              onPressed: () => _handleSubmitted(quickReplies[i], provider),
              style: OutlinedButton.styleFrom(
                shape: const StadiumBorder(),
                side: const BorderSide(color: kPrimaryGreen),
                foregroundColor: kPrimaryGreen,
                padding: const EdgeInsets.symmetric(horizontal: 16),
              ),
              child: Text(quickReplies[i]),
            ),
          );
        },
      ),
    );
  }

  Widget _buildInputArea(ChatProvider provider) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildDisclaimerBanner(provider),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [
              BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 10, offset: const Offset(0, -2))
            ],
          ),
          child: SafeArea(
            child: Row(
              children: [
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      color: Colors.grey[100],
                      borderRadius: BorderRadius.circular(25),
                    ),
                    child: TextField(
                      controller: _controller,
                      decoration: InputDecoration(
                        hintText: _isListening 
                          ? (provider.language == 'sw' ? 'Nasikiliza...' : 'Listening...')
                          : (provider.language == 'sw' ? 'Andika ujumbe...' : 'Type a message...'),
                        border: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                      ),
                      onSubmitted: (val) => _handleSubmitted(val, provider),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  decoration: const BoxDecoration(
                    color: kPrimaryGreen,
                    shape: BoxShape.circle,
                  ),
                  child: IconButton(
                    onPressed: () => _handleSubmitted(_controller.text, provider),
                    icon: const Icon(Icons.send, color: Colors.white),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDisclaimerBanner(ChatProvider provider) {
    final text = provider.language == 'en'
        ? "I am an informational chatbot only. I do not perform applications, payments, or status checks. Please use official government portals or Huduma Centres."
        : "Msaidizi Mkononi ni mfumo wa kutoa taarifa pekee. Hatufanyi maombi, malipo, au ukaguzi wa hali. Tafadhali tumia tovuti rasmi za serikali au Vituo vya Huduma.";

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      color: kPrimaryGreen.withOpacity(0.1),
      child: Row(
        children: [
          const Icon(Icons.info_outline, size: 16, color: kPrimaryGreen),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(fontSize: 11, color: kPrimaryGreen, fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 1000))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.start,
      children: [
        const CircleAvatar(
          radius: 16,
          backgroundColor: kPrimaryGreen,
          child: Icon(Icons.account_balance, size: 18, color: Colors.white),
        ),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(18),
              topRight: Radius.circular(18),
              bottomRight: Radius.circular(18),
            ),
            boxShadow: [
              BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 5, offset: const Offset(0, 2))
            ],
          ),
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(3, (index) {
                  final delay = index * 0.2;
                  final value = ((_controller.value + delay) % 1.0);
                  final double offset = -6.0 * (1.0 - (value - 0.5).abs() * 2);
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: Transform.translate(
                      offset: Offset(0, offset < 0 ? offset : 0),
                      child: Container(
                        width: 6,
                        height: 6,
                        decoration: const BoxDecoration(color: Colors.grey, shape: BoxShape.circle),
                      ),
                    ),
                  );
                }),
              );
            },
          ),
        ),
      ],
    );
  }
}
