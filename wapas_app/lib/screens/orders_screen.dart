import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../theme/app_theme.dart';
import '../models/order_models.dart';
import '../providers/app_providers.dart';

class OrdersScreen extends ConsumerStatefulWidget {
  const OrdersScreen({super.key});

  @override
  ConsumerState<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends ConsumerState<OrdersScreen> {
  List<StoreOrderModel> _orders = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadOrders();
  }

  Future<void> _loadOrders() async {
    setState(() => _isLoading = true);
    try {
      final orders = await ref.read(ordersRepoProvider).getOrders();
      if (mounted) {
        setState(() {
          _orders = orders;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Failed to load orders: $e")),
        );
      }
    }
  }

  void _showStorefrontQrModal() async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => const Center(child: CircularProgressIndicator()),
    );

    try {
      final qrData = await ref.read(ordersRepoProvider).getStorefrontQr();
      if (!mounted) return;
      Navigator.pop(context); // Dismiss loader

      final targetUrl = qrData['target_url'] ?? qrData['storefront_url'] ?? 'http://localhost:8000/s/default-store';

      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Row(
            children: const [
              Icon(Icons.qr_code, color: AppColors.secondary),
              SizedBox(width: 8),
              Text("Storefront QR Code", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                "Customers scan this QR to order online directly from your Kirana storefront:",
                style: TextStyle(fontSize: 12, color: AppColors.outline),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 14),
              QrImageView(
                data: targetUrl,
                version: QrVersions.auto,
                size: 180,
              ),
              const SizedBox(height: 12),
              SelectableText(
                targetUrl,
                style: const TextStyle(fontSize: 11, color: AppColors.secondary, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Close")),
          ],
        ),
      );
    } catch (e) {
      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Failed to load Storefront QR: $e")),
        );
      }
    }
  }

  void _fulfillOrder(StoreOrderModel order) async {
    try {
      await ref.read(ordersRepoProvider).fulfillOrder(order.id);
      _loadOrders();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: const Color(0xFF2E7D32),
            content: Text("Order #${order.orderNumber} marked FULFILLED!"),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Fulfillment failed: $e")),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        backgroundColor: AppColors.surfaceLowest,
        elevation: 0.5,
        title: const Text("Online Storefront Orders", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        actions: [
          IconButton(
            icon: const Icon(Icons.qr_code_2, color: AppColors.secondary),
            tooltip: "Storefront QR & Link",
            onPressed: _showStorefrontQrModal,
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadOrders,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _orders.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.local_shipping_outlined, size: 48, color: AppColors.outline),
                      const SizedBox(height: 12),
                      const Text(
                        "No storefront orders received yet.",
                        style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.outline),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(backgroundColor: AppColors.secondary, foregroundColor: Colors.white),
                        icon: const Icon(Icons.qr_code, size: 18),
                        label: const Text("Show Storefront QR"),
                        onPressed: _showStorefrontQrModal,
                      ),
                    ],
                  ),
                )
              : ListView.separated(
                  padding: const EdgeInsets.all(12),
                  itemCount: _orders.length,
                  separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                  itemBuilder: (ctx, idx) {
                    final o = _orders[idx];
                    final isPending = o.isPending;

                    return Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceLowest,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.4)),
                      ),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: isPending ? Colors.orange.shade50 : Colors.green.shade50,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Icon(
                              isPending ? Icons.pending_actions : Icons.check_circle,
                              color: isPending ? Colors.orange.shade800 : Colors.green,
                              size: 24,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text("Order #${o.orderNumber}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                                const SizedBox(height: 2),
                                Text("${o.customerName} • ${o.createdAt}", style: const TextStyle(fontSize: 12, color: AppColors.outline)),
                                const SizedBox(height: 4),
                                Text(
                                  "₹${o.totalInr.toStringAsFixed(2)}",
                                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: AppColors.secondary),
                                ),
                              ],
                            ),
                          ),
                          if (isPending)
                            ElevatedButton(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.green,
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                              ),
                              onPressed: () => _fulfillOrder(o),
                              child: const Text("FULFILL", style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                            )
                          else
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                              decoration: BoxDecoration(
                                color: Colors.green.shade100,
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: const Text(
                                "FULFILLED",
                                style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.green),
                              ),
                            ),
                        ],
                      ),
                    );
                  },
                ),
    );
  }
}
