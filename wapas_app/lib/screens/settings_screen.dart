import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/app_providers.dart';
import '../theme/app_theme.dart';
import 'login_screen.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late TextEditingController _urlController;
  bool _testingConnection = false;
  String? _connectionStatus;
  bool? _isHealthy;

  @override
  void initState() {
    super.initState();
    final client = ref.read(apiClientProvider);
    _urlController = TextEditingController(text: client.baseUrl);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    setState(() {
      _testingConnection = true;
      _connectionStatus = null;
      _isHealthy = null;
    });

    final client = ref.read(apiClientProvider);
    await client.setBaseUrl(_urlController.text.trim());

    final stopwatch = Stopwatch()..start();
    final ok = await client.testHealth();
    stopwatch.stop();

    setState(() {
      _testingConnection = false;
      _isHealthy = ok;
      _connectionStatus = ok
          ? 'Connected successfully (/healthz responded in ${stopwatch.elapsedMilliseconds}ms)'
          : 'Failed to reach /healthz. Please verify server host and port.';
    });
  }

  Future<void> _saveUrl() async {
    final client = ref.read(apiClientProvider);
    await client.setBaseUrl(_urlController.text.trim());
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Server URL updated and saved'),
          backgroundColor: AppColors.secondary,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authNotifierProvider);
    final session = authState.session;

    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        title: const Text('Store & Server Settings'),
        backgroundColor: AppColors.surfaceLowest,
        foregroundColor: AppColors.primary,
        elevation: 0,
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // Store Context Card
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: const BorderSide(color: AppColors.surfaceLow),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.1),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.store, color: AppColors.primary),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              session.storeName ?? 'Wapas Merchant Store',
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                            ),
                            Text(
                              session.merchantName ?? 'Paytm Build for India',
                              style: TextStyle(color: AppColors.onSurface.withValues(alpha: 0.6), fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: session.role.isOwner
                              ? Colors.green.withValues(alpha: 0.15)
                              : Colors.blue.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          session.role.isOwner ? 'OWNER' : 'STAFF',
                          style: TextStyle(
                            color: session.role.isOwner ? Colors.green.shade800 : Colors.blue.shade800,
                            fontWeight: FontWeight.bold,
                            fontSize: 11,
                          ),
                        ),
                      ),
                    ],
                  ),
                  if (authState.memberships.length > 1) ...[
                    const Divider(height: 24),
                    const Text('Switch Store Membership', style: TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    ...authState.memberships.map((m) {
                      final isCurrent = m.id == session.membershipId;
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(
                          isCurrent ? Icons.check_circle : Icons.radio_button_unchecked,
                          color: isCurrent ? AppColors.secondary : AppColors.outline,
                        ),
                        title: Text(m.storeName, style: const TextStyle(fontSize: 14)),
                        subtitle: Text('Role: ${m.role.toApiString()}', style: const TextStyle(fontSize: 11)),
                        trailing: isCurrent ? null : TextButton(
                          onPressed: () => ref.read(authNotifierProvider.notifier).switchMembership(m.id),
                          child: const Text('Switch'),
                        ),
                      );
                    }),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Server Connection Card
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: const BorderSide(color: AppColors.surfaceLow),
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Backend Server URL', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                  const SizedBox(height: 6),
                  Text(
                    'Configure Wapas Merchant OS server address (e.g. adb reverse 127.0.0.1:8000, 10.0.2.2:8000 emulator, or production HTTPS)',
                    style: TextStyle(color: AppColors.onSurface.withValues(alpha: 0.6), fontSize: 12),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _urlController,
                    decoration: InputDecoration(
                      prefixIcon: const Icon(Icons.link),
                      hintText: 'http://10.0.2.2:8000',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.save, color: AppColors.secondary),
                        onPressed: _saveUrl,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      ElevatedButton.icon(
                        onPressed: _testingConnection ? null : _testConnection,
                        icon: _testingConnection
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            : const Icon(Icons.network_check, size: 18),
                        label: const Text('Test Connection (/healthz)'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primary,
                          foregroundColor: Colors.white,
                        ),
                      ),
                    ],
                  ),
                  if (_connectionStatus != null) ...[
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: _isHealthy == true
                            ? Colors.green.withValues(alpha: 0.1)
                            : Colors.red.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _isHealthy == true ? Icons.check_circle : Icons.error,
                            color: _isHealthy == true ? Colors.green : Colors.red,
                            size: 18,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _connectionStatus!,
                              style: TextStyle(
                                color: _isHealthy == true ? Colors.green.shade800 : Colors.red.shade800,
                                fontSize: 12,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Security & Architecture Info
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.surfaceLowest,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.outline.withValues(alpha: 0.2)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(
                  children: [
                    Icon(Icons.security, size: 18, color: AppColors.secondary),
                    SizedBox(width: 8),
                    Text(
                      'Security Policy & Gateway',
                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  '• Double-submit CSRF cookie & x-wapas-csrf header active\n'
                  '• Android Network Security Config: Release builds HTTPS-only\n'
                  '• Gateway: Paytm Staging / Simulated (No mock client data)',
                  style: TextStyle(color: AppColors.onSurface.withValues(alpha: 0.7), fontSize: 11, height: 1.4),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // Logout Button
          OutlinedButton.icon(
            onPressed: () async {
              await ref.read(authNotifierProvider.notifier).logout();
              if (context.mounted) {
                Navigator.of(context).pushAndRemoveUntil(
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                  (route) => false,
                );
              }
            },
            icon: const Icon(Icons.logout, color: Colors.red),
            label: const Text('Sign Out of Workspace', style: TextStyle(color: Colors.red)),
            style: OutlinedButton.styleFrom(
              side: const BorderSide(color: Colors.red),
              padding: const EdgeInsets.symmetric(vertical: 12),
            ),
          ),
        ],
      ),
    );
  }
}
