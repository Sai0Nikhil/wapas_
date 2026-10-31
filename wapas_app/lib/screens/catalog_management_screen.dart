import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../theme/app_theme.dart';
import '../models/catalog_models.dart';
import '../providers/app_providers.dart';

class CatalogManagementScreen extends ConsumerStatefulWidget {
  const CatalogManagementScreen({super.key});

  @override
  ConsumerState<CatalogManagementScreen> createState() => _CatalogManagementScreenState();
}

class _CatalogManagementScreenState extends ConsumerState<CatalogManagementScreen> {
  List<ProductModel> _products = [];
  bool _isLoading = true;
  String _search = "";

  @override
  void initState() {
    super.initState();
    _loadProducts();
  }

  Future<void> _loadProducts() async {
    setState(() => _isLoading = true);
    try {
      final items = await ref.read(catalogRepoProvider).getProducts(query: _search);
      if (mounted) {
        setState(() {
          _products = items;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Failed to load catalog: $e")),
        );
      }
    }
  }

  void _showStockAdjustDialog(ProductModel product) {
    final deltaCtrl = TextEditingController(text: "10");
    final reasonCtrl = TextEditingController(text: "Restocked from APMC mandi");
    bool isAdding = true;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: Text("Adjust Stock: ${product.name}", style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("Current Available: ${product.currentStock.toStringAsFixed(0)} ${product.unit}",
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: AppColors.secondary)),
              const SizedBox(height: 14),
              Row(
                children: [
                  ChoiceChip(
                    label: const Text("+ Restock"),
                    selected: isAdding,
                    selectedColor: Colors.green.shade100,
                    onSelected: (val) => setDialogState(() => isAdding = true),
                  ),
                  const SizedBox(width: 8),
                  ChoiceChip(
                    label: const Text("- Damage / Loss"),
                    selected: !isAdding,
                    selectedColor: Colors.red.shade100,
                    onSelected: (val) => setDialogState(() => isAdding = false),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: deltaCtrl,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: isAdding ? "Quantity to Add" : "Quantity to Deduct",
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: reasonCtrl,
                decoration: const InputDecoration(
                  labelText: "Audit Reason",
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Cancel")),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: isAdding ? Colors.green : AppColors.error,
                foregroundColor: Colors.white,
              ),
              onPressed: () async {
                final qty = double.tryParse(deltaCtrl.text) ?? 0.0;
                if (qty <= 0) return;
                final delta = isAdding ? qty : -qty;
                Navigator.pop(ctx);
                final scaffold = ScaffoldMessenger.of(context);
                try {
                  await ref.read(catalogRepoProvider).adjustStock(
                    product.id,
                    delta,
                    reasonCtrl.text.trim(),
                  );
                  _loadProducts();
                  if (!mounted) return;
                  scaffold.showSnackBar(
                    SnackBar(backgroundColor: const Color(0xFF2E7D32), content: Text("Stock adjusted by $delta for ${product.name}")),
                  );
                } catch (e) {
                  if (!mounted) return;
                  scaffold.showSnackBar(
                    SnackBar(content: Text("Stock adjustment failed: $e")),
                  );
                }
              },
              child: const Text("SAVE AUDIT ADJUSTMENT"),
            ),
          ],
        ),
      ),
    );
  }

  void _showMovementsModal() async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => const Center(child: CircularProgressIndicator()),
    );

    try {
      final movements = await ref.read(catalogRepoProvider).getMovements();
      if (!mounted) return;
      Navigator.pop(context); // Dismiss loader

      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: AppColors.surfaceLowest,
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
        builder: (ctx) => Container(
          height: MediaQuery.of(context).size.height * 0.75,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text("Inventory Movements Audit", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(ctx)),
                ],
              ),
              const SizedBox(height: 10),
              Expanded(
                child: movements.isEmpty
                    ? const Center(child: Text("No stock movements recorded yet.", style: TextStyle(color: AppColors.outline)))
                    : ListView.separated(
                        itemCount: movements.length,
                        separatorBuilder: (ctx, idx) => const Divider(),
                        itemBuilder: (ctx, idx) {
                          final m = movements[idx];
                          final isPos = m.delta > 0;
                          return ListTile(
                            leading: Icon(
                              isPos ? Icons.add_circle : Icons.remove_circle,
                              color: isPos ? Colors.green : Colors.red,
                            ),
                            title: Text(m.productName.isNotEmpty ? m.productName : m.productId, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                            subtitle: Text("${m.reason} • ${m.createdAt}", style: const TextStyle(fontSize: 11, color: AppColors.outline)),
                            trailing: Text(
                              "${isPos ? '+' : ''}${m.delta.toStringAsFixed(0)}",
                              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: isPos ? Colors.green : Colors.red),
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Failed to load movements: $e")),
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
        title: const Text("Store Catalogue & Stock", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
        actions: [
          IconButton(
            icon: const Icon(Icons.history, color: AppColors.secondary),
            tooltip: "Stock Movements Log",
            onPressed: _showMovementsModal,
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadProducts,
          ),
        ],
      ),
      body: Column(
        children: [
          // Search Bar
          Padding(
            padding: const EdgeInsets.all(12),
            child: TextField(
              onChanged: (val) {
                _search = val;
                _loadProducts();
              },
              decoration: InputDecoration(
                hintText: "Search products in inventory...",
                prefixIcon: const Icon(Icons.search, size: 18),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                contentPadding: const EdgeInsets.symmetric(vertical: 10),
              ),
            ),
          ),

          // Product List
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _products.isEmpty
                    ? const Center(child: Text("No products found.", style: TextStyle(color: AppColors.outline)))
                    : ListView.separated(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                        itemCount: _products.length,
                        separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                        itemBuilder: (ctx, idx) {
                          final p = _products[idx];
                          return Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceLowest,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: AppColors.outlineVariant.withValues(alpha: 0.4)),
                            ),
                            child: Row(
                              children: [
                                Container(
                                  width: 40,
                                  height: 40,
                                  decoration: BoxDecoration(
                                    color: AppColors.surfaceLow,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: const Icon(Icons.inventory_2, color: AppColors.secondary),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(p.name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                                      const SizedBox(height: 2),
                                      Text(
                                        "₹${p.price.toStringAsFixed(0)} • Stock: ${p.currentStock.toStringAsFixed(0)} ${p.unit}",
                                        style: TextStyle(
                                          fontSize: 12,
                                          fontWeight: p.isLowStock ? FontWeight.bold : FontWeight.normal,
                                          color: p.isLowStock ? Colors.orange.shade800 : AppColors.outline,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                OutlinedButton(
                                  style: OutlinedButton.styleFrom(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                    visualDensity: VisualDensity.compact,
                                  ),
                                  onPressed: () => _showStockAdjustDialog(p),
                                  child: const Text("Adjust Stock", style: TextStyle(fontSize: 11)),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}
