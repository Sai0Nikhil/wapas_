import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'theme/app_theme.dart';
import 'providers/app_providers.dart';
import 'screens/splash_screen.dart';
import 'screens/pos_billing_screen.dart';
import 'screens/recovery_tower_screen.dart';
import 'screens/khata_ledger_screen.dart';
import 'screens/sarkar_copilot_screen.dart';
import 'screens/soundbox_feed_screen.dart';
import 'screens/catalog_management_screen.dart';
import 'screens/orders_screen.dart';
import 'screens/agent_activity_screen.dart';
import 'screens/settings_screen.dart';

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

class MainNavigationShell extends ConsumerStatefulWidget {
  const MainNavigationShell({super.key});

  @override
  ConsumerState<MainNavigationShell> createState() => _MainNavigationShellState();
}

class _MainNavigationShellState extends ConsumerState<MainNavigationShell> {
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
    final authState = ref.watch(authNotifierProvider);
    final rawStoreName = authState.session.storeName;
    final storeName = (rawStoreName != null && rawStoreName.isNotEmpty) ? rawStoreName : "Wapas Kirana Store";

    return Scaffold(
      drawer: Drawer(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            DrawerHeader(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  colors: [AppColors.primary, AppColors.secondary],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Container(
                    width: 48,
                    height: 48,
                    decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white),
                    clipBehavior: Clip.antiAlias,
                    child: Image.asset('assets/images/wapas_logo.png', fit: BoxFit.cover),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    storeName,
                    style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  Text(
                    "Role: ${authState.session.role.name.toUpperCase()}",
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ],
              ),
            ),
            ListTile(
              leading: const Icon(Icons.point_of_sale, color: AppColors.secondary),
              title: const Text("POS Counter Billing"),
              selected: _currentIndex == 0,
              onTap: () {
                Navigator.pop(context);
                setState(() => _currentIndex = 0);
              },
            ),
            ListTile(
              leading: const Icon(Icons.shield, color: AppColors.secondary),
              title: const Text("Recovery Control Tower"),
              selected: _currentIndex == 1,
              onTap: () {
                Navigator.pop(context);
                setState(() => _currentIndex = 1);
              },
            ),
            ListTile(
              leading: const Icon(Icons.menu_book, color: AppColors.secondary),
              title: const Text("Digital Khata Ledger"),
              selected: _currentIndex == 2,
              onTap: () {
                Navigator.pop(context);
                setState(() => _currentIndex = 2);
              },
            ),
            ListTile(
              leading: const Icon(Icons.psychology, color: AppColors.secondary),
              title: const Text("Sarkar AI Retail Copilot"),
              selected: _currentIndex == 3,
              onTap: () {
                Navigator.pop(context);
                setState(() => _currentIndex = 3);
              },
            ),
            ListTile(
              leading: const Icon(Icons.speaker, color: AppColors.secondary),
              title: const Text("Paytm Soundbox Live"),
              selected: _currentIndex == 4,
              onTap: () {
                Navigator.pop(context);
                setState(() => _currentIndex = 4);
              },
            ),
            const Divider(),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: Text("OPERATIONS & AGENTS", style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppColors.outline)),
            ),
            ListTile(
              leading: const Icon(Icons.inventory_2_outlined),
              title: const Text("Catalogue & Stock"),
              onTap: () {
                Navigator.pop(context);
                Navigator.push(context, MaterialPageRoute(builder: (_) => const CatalogManagementScreen()));
              },
            ),
            ListTile(
              leading: const Icon(Icons.local_shipping_outlined),
              title: const Text("Online Storefront Orders"),
              onTap: () {
                Navigator.pop(context);
                Navigator.push(context, MaterialPageRoute(builder: (_) => const OrdersScreen()));
              },
            ),
            ListTile(
              leading: const Icon(Icons.smart_toy_outlined),
              title: const Text("Autonomous Teammates (Track 3)"),
              onTap: () {
                Navigator.pop(context);
                Navigator.push(context, MaterialPageRoute(builder: (_) => const AgentActivityScreen()));
              },
            ),
            const Divider(),
            ListTile(
              leading: const Icon(Icons.settings_outlined),
              title: const Text("Settings & Server URL"),
              onTap: () {
                Navigator.pop(context);
                Navigator.push(context, MaterialPageRoute(builder: (_) => const SettingsScreen()));
              },
            ),
          ],
        ),
      ),
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
