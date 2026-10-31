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
                    border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.3)),
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

                const SizedBox(height: 16),

                // AI "Scan & Fetch" Handwritten Parchi Banner
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF0051D5), Color(0xFF003180)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.1),
                        blurRadius: 8,
                        offset: const Offset(0, 3),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.15),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(Icons.document_scanner, color: Colors.white, size: 28),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                Text(
                                  "Scan & Fetch Parchi",
                                  style: TextStyle(
                                    fontSize: 15,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                                SizedBox(width: 6),
                                Text(
                                  "AI OCR",
                                  style: TextStyle(
                                    fontSize: 9,
                                    fontWeight: FontWeight.bold,
                                    color: Color(0xFF4EDEA3),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 3),
                            const Text(
                              "Scan handwritten paper note / khata slip to auto-extract name, phone & items.",
                              style: TextStyle(fontSize: 11, color: Color(0xFFDCE9FF)),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      ElevatedButton(
                        onPressed: () => _simulateScanAndFetch(context),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: AppColors.secondary,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                        ),
                        child: const Text(
                          "SCAN",
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                        ),
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
        border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.3)),
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
                    color: AppColors.secondaryContainer.withValues(alpha: 0.12),
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

  void _simulateScanAndFetch(BuildContext context) {
    // Show Scanning progress indicator
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        content: Padding(
          padding: const EdgeInsets.symmetric(vertical: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: const [
              CircularProgressIndicator(color: AppColors.secondary),
              SizedBox(height: 18),
              Text(
                "Scanning Handwritten Parchi...",
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
              ),
              SizedBox(height: 6),
              Text(
                "Sarvam AI OCR extracting Hindi/English text & numbers",
                style: TextStyle(fontSize: 12, color: AppColors.outline),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );

    // Wait 1.4s then pop scanner and open Review & Edit Dialog
    Future.delayed(const Duration(milliseconds: 1400), () {
      Navigator.pop(context);
      _showParchiReviewDialog(
        context,
        extractedName: "Mahesh Gupta (Kaka)",
        extractedPhone: "+91 98765 43210",
        extractedAmount: "1650",
        extractedItems: "Atta 5kg (₹245), Dal 2kg (₹320), Ghee 1L (₹650), Chawal 5kg (₹435)",
      );
    });
  }

  void _showParchiReviewDialog(
    BuildContext context, {
    required String extractedName,
    required String extractedPhone,
    required String extractedAmount,
    required String extractedItems,
  }) {
    final nameCtrl = TextEditingController(text: extractedName);
    final phoneCtrl = TextEditingController(text: extractedPhone);
    final amountCtrl = TextEditingController(text: extractedAmount);
    final itemsCtrl = TextEditingController(text: extractedItems);

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surfaceLowest,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    "Review Handwritten Parchi",
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.onSurface),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: AppColors.tertiaryContainer,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: const Text(
                      "94% OCR MATCH",
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppColors.onTertiaryContainer),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              const Text(
                "You can edit any field before adding to Khata ledger.",
                style: TextStyle(fontSize: 12, color: AppColors.outline),
              ),
              const SizedBox(height: 16),

              TextField(
                controller: nameCtrl,
                decoration: const InputDecoration(
                  labelText: "Customer Name",
                  prefixIcon: Icon(Icons.person, color: AppColors.secondary),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: phoneCtrl,
                decoration: const InputDecoration(
                  labelText: "Phone Number",
                  prefixIcon: Icon(Icons.phone, color: AppColors.secondary),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: amountCtrl,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: "Total Udhaar Amount (₹)",
                  prefixIcon: Icon(Icons.currency_rupee, color: Color(0xFFC75C00)),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: itemsCtrl,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: "Extracted Parchi Note / Items",
                  prefixIcon: Icon(Icons.notes, color: AppColors.secondary),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 20),

              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () => Navigator.pop(ctx),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      child: const Text("Discard"),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    flex: 2,
                    child: ElevatedButton.icon(
                      onPressed: () {
                        if (nameCtrl.text.isNotEmpty) {
                          storeState.addKhataCustomer(
                            nameCtrl.text,
                            phoneCtrl.text,
                            double.tryParse(amountCtrl.text) ?? 0.0,
                          );
                          Navigator.pop(ctx);
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: AppColors.tertiary,
                              content: Text("Added ${nameCtrl.text} (₹${amountCtrl.text}) to Khata!"),
                            ),
                          );
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.secondary,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      icon: const Icon(Icons.check, size: 18),
                      label: const Text(
                        "CONFIRM & ADD",
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
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
