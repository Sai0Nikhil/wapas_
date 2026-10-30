import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/store_state.dart';
import '../models/app_models.dart';

class KhataLedgerScreen extends StatelessWidget {
  const KhataLedgerScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: storeState,
      builder: (context, _) {
        final totalKhataDue = storeState.khataList.fold(0.0, (acc, k) => acc + k.totalDue);

        return Scaffold(
          backgroundColor: AppColors.surface,
          appBar: AppBar(
            backgroundColor: AppColors.surfaceLowest,
            title: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text("Khata Ledger (उधार खाता)", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                Text("Zero disputes • Verified Paytm collection links", style: TextStyle(fontSize: 11, color: AppColors.outline)),
              ],
            ),
          ),
          body: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Khata Balance Card
                Container(
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLowest,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: AppColors.outlineVariant.withOpacity(0.3)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            "TOTAL OUTSTANDING UDHAAR",
                            style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppColors.outline, letterSpacing: 0.5),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            "₹${totalKhataDue.toStringAsFixed(2)}",
                            style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, color: Color(0xFFC75C00)),
                          ),
                        ],
                      ),
                      ElevatedButton.icon(
                        onPressed: () {
                          _showAddCustomerDialog(context);
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.secondary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        icon: const Icon(Icons.person_add, size: 16),
                        label: const Text("New Khata"),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 20),
                const Text(
                  "Customer Ledger Accounts",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                ),
                const SizedBox(height: 12),

                ...storeState.khataList.map((customer) => _buildKhataItem(context, customer)),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildKhataItem(BuildContext context, KhataCustomer customer) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surfaceLowest,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.outlineVariant.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor: AppColors.surfaceContainer,
            child: Text(
              customer.name[0],
              style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.secondary),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  customer.name,
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppColors.onSurface),
                ),
                const SizedBox(height: 2),
                Text(
                  "${customer.phone} • Last: ${customer.lastTransactionDate}",
                  style: const TextStyle(fontSize: 12, color: AppColors.onSurfaceVariant),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                "₹${customer.totalDue.toStringAsFixed(0)}",
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: Color(0xFFC75C00)),
              ),
              const SizedBox(height: 4),
              InkWell(
                onTap: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      backgroundColor: AppColors.secondary,
                      content: Text("Paytm Collection link sent to ${customer.name} (${customer.phone})"),
                    ),
                  );
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.secondaryContainer.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Text(
                    "Send Link",
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppColors.secondary),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  void _showAddCustomerDialog(BuildContext context) {
    final nameCtrl = TextEditingController();
    final phoneCtrl = TextEditingController();
    final amountCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text("Create Khata Account"),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: "Customer Name")),
            TextField(controller: phoneCtrl, decoration: const InputDecoration(labelText: "Phone Number")),
            TextField(controller: amountCtrl, decoration: const InputDecoration(labelText: "Opening Due (₹)")),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Cancel")),
          ElevatedButton(
            onPressed: () {
              if (nameCtrl.text.isNotEmpty) {
                storeState.addKhataCustomer(
                  nameCtrl.text,
                  phoneCtrl.text,
                  double.tryParse(amountCtrl.text) ?? 0.0,
                );
                Navigator.pop(ctx);
              }
            },
            child: const Text("Save"),
          ),
        ],
      ),
    );
  }
}
