import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../services/store_state.dart';

class PosBillingScreen extends StatefulWidget {
  const PosBillingScreen({super.key});

  @override
  State<PosBillingScreen> createState() => _PosBillingScreenState();
}

class _PosBillingScreenState extends State<PosBillingScreen> {
  String searchQuery = "";

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: storeState,
      builder: (context, _) {
        final filteredItems = storeState.inventory.where((item) {
          return item.name.toLowerCase().contains(searchQuery.toLowerCase()) ||
                 item.category.toLowerCase().contains(searchQuery.toLowerCase());
        }).toList();

        return Scaffold(
          backgroundColor: AppColors.surface,
          appBar: AppBar(
            backgroundColor: AppColors.surfaceLowest,
            elevation: 0.5,
            title: Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: const BoxDecoration(
                    shape: BoxShape.circle,
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Image.asset(
                    'assets/images/wapas_logo.png',
                    fit: BoxFit.cover,
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.secondaryContainer.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.storefront, size: 16, color: AppColors.secondary),
                      const SizedBox(width: 6),
                      Text(
                        storeState.storeName,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                          color: AppColors.onSurface,
                        ),
                      ),
                    ],
                  ),
                ),
                const Spacer(),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.tertiaryContainer,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: AppColors.tertiary,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Text(
                        "SOUNDBOX LIVE",
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: AppColors.onTertiaryContainer,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          body: Column(
            children: [
              // Search & Barcode Quick Action Bar
              Container(
                padding: const EdgeInsets.all(12),
                color: AppColors.surfaceLowest,
                child: Row(
                  children: [
                    Expanded(
                      child: Container(
                        height: 44,
                        decoration: BoxDecoration(
                          color: AppColors.surfaceLow,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: TextField(
                          onChanged: (val) => setState(() => searchQuery = val),
                          decoration: const InputDecoration(
                            hintText: "Search item, barcode or brand...",
                            hintStyle: TextStyle(fontSize: 13, color: AppColors.outline),
                            prefixIcon: Icon(Icons.search, size: 20, color: AppColors.outline),
                            border: InputBorder.none,
                            contentPadding: EdgeInsets.symmetric(vertical: 12),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    InkWell(
                      onTap: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text("Barcode scanner ready")),
                        );
                      },
                      child: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: AppColors.secondaryContainer,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Icon(Icons.qr_code_scanner, color: Colors.white, size: 22),
                      ),
                    ),
                  ],
                ),
              ),

              // Item Catalogue List
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.all(12),
                  itemCount: filteredItems.length,
                  separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                  itemBuilder: (ctx, idx) {
                    final item = filteredItems[idx];
                    return Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceLowest,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: item.quantityInCart > 0
                              ? AppColors.secondary.withOpacity(0.5)
                              : AppColors.outlineVariant.withOpacity(0.3),
                          width: item.quantityInCart > 0 ? 1.5 : 1,
                        ),
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(
                              color: AppColors.surfaceContainer,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(Icons.shopping_bag_outlined, color: AppColors.secondary),
                          ),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  item.name,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 14,
                                    color: AppColors.onSurface,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  "${item.weight} • Stock: ${item.stock} left",
                                  style: const TextStyle(
                                    fontSize: 12,
                                    color: AppColors.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(
                                "₹${item.price.toStringAsFixed(0)}",
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 16,
                                  color: AppColors.onSurface,
                                ),
                              ),
                              const SizedBox(height: 4),
                              item.quantityInCart == 0
                                  ? InkWell(
                                      onTap: () => storeState.addToCart(item),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
                                        decoration: BoxDecoration(
                                          color: AppColors.secondary,
                                          borderRadius: BorderRadius.circular(6),
                                        ),
                                        child: const Text(
                                          "ADD",
                                          style: TextStyle(
                                            color: Colors.white,
                                            fontWeight: FontWeight.bold,
                                            fontSize: 11,
                                          ),
                                        ),
                                      ),
                                    )
                                  : Row(
                                      children: [
                                        InkWell(
                                          onTap: () => storeState.removeFromCart(item),
                                          child: Container(
                                            padding: const EdgeInsets.all(4),
                                            decoration: BoxDecoration(
                                              color: AppColors.surfaceContainer,
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: const Icon(Icons.remove, size: 14, color: AppColors.onSurface),
                                          ),
                                        ),
                                        Padding(
                                          padding: const EdgeInsets.symmetric(horizontal: 8),
                                          child: Text(
                                            "${item.quantityInCart}",
                                            style: const TextStyle(fontWeight: FontWeight.bold),
                                          ),
                                        ),
                                        InkWell(
                                          onTap: () => storeState.addToCart(item),
                                          child: Container(
                                            padding: const EdgeInsets.all(4),
                                            decoration: BoxDecoration(
                                              color: AppColors.secondary,
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: const Icon(Icons.add, size: 14, color: Colors.white),
                                          ),
                                        ),
                                      ],
                                    ),
                            ],
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),

              // Bottom POS Checkout Dock
              if (storeState.cartCount > 0)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLowest,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.08),
                        blurRadius: 10,
                        offset: const Offset(0, -3),
                      ),
                    ],
                  ),
                  child: SafeArea(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  "${storeState.cartCount} ITEMS IN BILL",
                                  style: const TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                    color: AppColors.outline,
                                    letterSpacing: 0.5,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  "₹${storeState.cartTotal.toStringAsFixed(2)}",
                                  style: const TextStyle(
                                    fontSize: 22,
                                    fontWeight: FontWeight.w800,
                                    color: AppColors.onSurface,
                                  ),
                                ),
                              ],
                            ),
                            Row(
                              children: [
                                OutlinedButton(
                                  onPressed: () => storeState.clearCart(),
                                  style: OutlinedButton.styleFrom(
                                    foregroundColor: AppColors.error,
                                    side: const BorderSide(color: AppColors.error),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                                  ),
                                  child: const Text("Clear"),
                                ),
                                const SizedBox(width: 8),
                                ElevatedButton.icon(
                                  onPressed: () => _showPaymentOptions(context),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: AppColors.secondary,
                                    foregroundColor: Colors.white,
                                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                  ),
                                  icon: const Icon(Icons.arrow_forward, size: 18),
                                  label: const Text(
                                    "COLLECT",
                                    style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 0.5),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  void _showPaymentOptions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surfaceLowest,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                "Select Payment Mode",
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppColors.onSurface),
              ),
              const SizedBox(height: 6),
              Text(
                "Total Amount: ₹${storeState.cartTotal.toStringAsFixed(2)}",
                style: const TextStyle(fontSize: 14, color: AppColors.secondary, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 16),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: AppColors.surfaceLow, borderRadius: BorderRadius.circular(8)),
                  child: const Icon(Icons.qr_code, color: AppColors.secondary),
                ),
                title: const Text("Paytm Dynamic UPI QR", style: TextStyle(fontWeight: FontWeight.bold)),
                subtitle: const Text("Verified with Paytm Soundbox live trigger"),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.pop(ctx);
                  storeState.completeCheckout("Paytm QR");
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      backgroundColor: AppColors.tertiary,
                      content: Text("Payment Verified! Paytm Soundbox: ₹" " announced successfully!"),
                    ),
                  );
                },
              ),
              const Divider(),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: AppColors.surfaceLow, borderRadius: BorderRadius.circular(8)),
                  child: const Icon(Icons.money, color: Colors.green),
                ),
                title: const Text("Cash Payment", style: TextStyle(fontWeight: FontWeight.bold)),
                subtitle: const Text("Print physical thermal receipt"),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.pop(ctx);
                  storeState.completeCheckout("Cash");
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text("Cash bill saved & inventory deducted")),
                  );
                },
              ),
              const Divider(),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: AppColors.surfaceLow, borderRadius: BorderRadius.circular(8)),
                  child: const Icon(Icons.book, color: Colors.orange),
                ),
                title: const Text("Add to Khata (उधार खाता)", style: TextStyle(fontWeight: FontWeight.bold)),
                subtitle: const Text("Record debit under trusted customer profile"),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.pop(ctx);
                  storeState.completeCheckout("Khata");
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text("Recorded to customer Khata Ledger")),
                  );
                },
              ),
            ],
          ),
        );
      },
    );
  }
}
