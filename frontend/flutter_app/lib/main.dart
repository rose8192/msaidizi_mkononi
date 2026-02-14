import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import 'providers/chat_provider.dart';
import 'screens/chat_screen.dart';

// Modern Kenyan Theme Colors
const Color kPrimaryGreen = Color(0xFF006644); // Dark Green from Flag
const Color kBackgroundBeige = Color(0xFFF5F2E8); // Background
const Color kUserBubbleColor = Color(0xFF006644);
const Color kBotBubbleColor = Colors.white;
const Color kAccentRed = Color(0xFFBF0028); // Red from flag

void main() {
  runApp(MsaidiziMkononiApp());
}

class MsaidiziMkononiApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => ChatProvider(),
      child: MaterialApp(
        title: 'Msaidizi Mkononi',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(
            seedColor: kPrimaryGreen,
            primary: kPrimaryGreen,
            surface: kBackgroundBeige,
          ),
          scaffoldBackgroundColor: kBackgroundBeige,
          textTheme: GoogleFonts.latoTextTheme(),
          appBarTheme: const AppBarTheme(
            backgroundColor: kPrimaryGreen,
            foregroundColor: Colors.white,
            elevation: 2,
            centerTitle: true,
          ),
        ),
        home: ChatScreen(),
      ),
    );
  }
}
