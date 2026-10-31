import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'theme/app_theme.dart';
import 'screens/splash_screen.dart';
import 'screens/pos_billing_screen.dart';
import 'screens/recovery_tower_screen.dart';
import 'screens/khata_ledger_screen.dart';
import 'screens/sarkar_copilot_screen.dart';
import 'screens/soundbox_feed_screen.dart';

void main() {
  runApp(const ProviderScope(child: WapasMerchantApp()));
}

class WapasMerchantApp extends StatelessWidget {
  const WapasMerchantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wapas Merchant OS',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: const SplashScreen(),
    );
  }
}

class MainNavigationShell extends StatefulWidget {
  const MainNavigationShell({super.key});

  @override
  State<MainNavigationShell> createState() => _MainNavigationShellState();
}

class _MainNavigationShellState extends State<MainNavigationShell> {
  int _currentIndex = 0;

  List<Widget> get _screens => [
    PosBillingScreen(onNavigateTab: (index) => setState(() => _currentIndex = index)),
    const RecoveryTowerScreen(),
    const KhataLedgerScreen(),
    const SarkarCopilotScreen(),
    const SoundboxFeedScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: AppColors.surfaceLowest,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.06),
              blurRadius: 10,
              offset: const Offset(0, -2),
            ),
          ],
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) => setState(() => _currentIndex = index),
          type: BottomNavigationBarType.fixed,
          backgroundColor: AppColors.surfaceLowest,
          selectedItemColor: AppColors.secondary,
          unselectedItemColor: AppColors.outline,
          selectedLabelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11),
          unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.w500, fontSize: 11),
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.point_of_sale),
              activeIcon: Icon(Icons.point_of_sale, color: AppColors.secondary),
              label: 'Billing',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.shield_outlined),
              activeIcon: Icon(Icons.shield, color: AppColors.secondary),
              label: 'Recovery',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.menu_book_outlined),
              activeIcon: Icon(Icons.menu_book, color: AppColors.secondary),
              label: 'Khata',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.psychology_outlined),
              activeIcon: Icon(Icons.psychology, color: AppColors.secondary),
              label: 'Sarkar AI',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.speaker_outlined),
              activeIcon: Icon(Icons.speaker, color: AppColors.secondary),
              label: 'Soundbox',
            ),
          ],
        ),
      ),
    );
  }
}
