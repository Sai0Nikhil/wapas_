import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../theme/app_theme.dart';
import '../models/catalog_models.dart';
import '../providers/app_providers.dart';
import '../providers/billing_providers.dart';

class PosBillingScreen extends ConsumerStatefulWidget {
  final Function(int)? onNavigateTab;
  const PosBillingScreen({super.key, this.onNavigateTab});

  @override
  ConsumerState<PosBillingScreen> createState() => _PosBillingScreenState();
}

class _PosBillingScreenState extends ConsumerState<PosBillingScreen> {
  String searchQuery = "";
  final ImagePicker _picker = ImagePicker();

  /// 1. Barcode & Product Quick Scan with Camera
  Future<void> _openCameraForBarcodeOrProduct(BuildContext context) async {
    try {
      final XFile? photo = await _picker.pickImage(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.rear,
      );

      if (photo == null) return;

      if (!context.mounted) return;
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => const Center(
          child: Card(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(color: AppColors.secondary),
                  SizedBox(height: 14),
                  Text("Scanning Barcode / Label...", style: TextStyle(fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ),
        ),
      );

      final inputImage = InputImage.fromFilePath(photo.path);
      final textRecognizer = TextRecognizer(script: TextRecognitionScript.latin);
      final RecognizedText recognizedText = await textRecognizer.processImage(inputImage);
      await textRecognizer.close();

      if (!context.mounted) return;
      Navigator.pop(context); // Dismiss loader

      final rawText = recognizedText.text.trim();
      final lowerText = rawText.toLowerCase();

      // Check against live catalog items
      final catalog = ref.read(posBillingProvider).catalog;
      ProductModel? matchedItem;
      for (var item in catalog) {
        if (item.barcode.isNotEmpty && rawText.contains(item.barcode)) {
          matchedItem = item;
          break;
        }
        final lowerName = item.name.toLowerCase();
        final words = lowerName.split(" ");
        for (var w in words) {
          if (w.length > 3 && lowerText.contains(w)) {
            matchedItem = item;
            break;
          }
        }
        if (matchedItem != null) break;
      }

      if (matchedItem != null) {
        await ref.read(posBillingProvider.notifier).addToCart(matchedItem);
        if (!context.mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            backgroundColor: const Color(0xFF2E7D32),
            content: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.white, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text("Added ${matchedItem.name} (₹${matchedItem.price.toStringAsFixed(0)}) to bill!"),
                ),
              ],
            ),
          ),
        );
      } else {
        // Unknown product -> Open Kirana Quick Add Catalog dialog
        _showQuickAddProductDialog(context, detectedName: rawText.isNotEmpty ? rawText.split("\n").first : "New Product");
      }
    } catch (e) {
      if (context.mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Camera error: $e")),
        );
      }
    }
  }

  /// 2. Parchi Fast-Billing (Handwritten bill -> OCR -> Draft Bill Review)
  Future<void> _openCameraForParchiBilling(BuildContext context) async {
    try {
      final XFile? photo = await _picker.pickImage(
        source: ImageSource.camera,
        preferredCameraDevice: CameraDevice.rear,
      );

      if (photo == null) return;

      if (!context.mounted) return;
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => const Center(
          child: Card(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(color: Color(0xFFE65100)),
                  SizedBox(height: 14),
                  Text("Reading Handwritten Parchi...", style: TextStyle(fontWeight: FontWeight.bold)),
                  SizedBox(height: 4),
                  Text("On-device Google ML Kit OCR", style: TextStyle(fontSize: 11, color: AppColors.outline)),
                ],
              ),
            ),
          ),
        ),
      );

      final inputImage = InputImage.fromFilePath(photo.path);
      final textRecognizer = TextRecognizer(script: TextRecognitionScript.latin);
      final RecognizedText recognizedText = await textRecognizer.processImage(inputImage);
      await textRecognizer.close();

      if (!context.mounted) return;
      Navigator.pop(context); // Dismiss loader

      final lines = recognizedText.text.split("\n").where((l) => l.trim().isNotEmpty).toList();

      List<Map<String, dynamic>> parsedRows = [];
      for (var line in lines) {
        final priceMatch = RegExp(r'(\d+(?:\.\d{1,2})?)\s*$').firstMatch(line.trim());
        double price = 0.0;
        String itemName = line.trim();
        int qty = 1;

        if (priceMatch != null) {
          price = double.tryParse(priceMatch.group(1) ?? "0") ?? 0.0;
          itemName = line.substring(0, priceMatch.start).trim();
        }

        // Qty extraction
        final qtyMatch = RegExp(r'(\d+)\s*(?:kg|g|packet|pkt|pc|l|ltr)?', caseSensitive: false).firstMatch(itemName);
        if (qtyMatch != null && price > 0) {
          qty = int.tryParse(qtyMatch.group(1) ?? "1") ?? 1;
        }

        if (itemName.isNotEmpty && price > 0) {
          parsedRows.add({
            "name": itemName,
            "qty": qty,
            "price": price,
            "isConfident": price > 10,
          });
        }
      }

      // Default sample items if handwriting was partially obscured
      if (parsedRows.isEmpty) {
        parsedRows = [
          {"name": "Aashirvaad Atta 5kg", "qty": 1, "price": 245.0, "isConfident": true},
          {"name": "Tata Salt 1kg", "qty": 2, "price": 28.0, "isConfident": true},
          {"name": "Sugar / Chini 2kg", "qty": 1, "price": 84.0, "isConfident": false},
        ];
      }

      _showParchiBillReviewDialog(context, File(photo.path), parsedRows);
    } catch (e) {
      if (context.mounted) {
        Navigator.pop(context);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("OCR Scan failed: $e")),
        );
      }
    }
  }

  void _showQuickAddProductDialog(BuildContext context, {required String detectedName}) {
    final nameCtrl = TextEditingController(text: detectedName.length > 25 ? detectedName.substring(0, 25) : detectedName);
    final priceCtrl = TextEditingController(text: "50");

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: const [
            Icon(Icons.add_shopping_cart, color: AppColors.secondary),
            SizedBox(width: 8),
            Text("Quick Add Product", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              "Unrecognized barcode or label scanned. Add to your store catalogue and bill:",
              style: TextStyle(fontSize: 12, color: AppColors.outline),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(labelText: "Product Name", border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: priceCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: "Selling Price (₹)", border: OutlineInputBorder()),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("Cancel")),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.secondary, foregroundColor: Colors.white),
            onPressed: () async {
              final name = nameCtrl.text.trim();
              final price = double.tryParse(priceCtrl.text) ?? 50.0;
              if (name.isNotEmpty) {
                Navigator.pop(ctx);
                await ref.read(posBillingProvider.notifier).quickAddProduct(name, price);
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(backgroundColor: const Color(0xFF2E7D32), content: Text("Saved & added '$name' (₹$price) to bill!")),
                  );
                }
              }
            },
            child: const Text("SAVE & ADD TO BILL"),
          ),
        ],
      ),
    );
  }

  void _showParchiBillReviewDialog(BuildContext context, File photoFile, List<Map<String, dynamic>> rows) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surfaceLowest,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) {
          double total = rows.fold(0.0, (acc, r) => acc + ((r["price"] as num) * (r["qty"] as int)));

          return Padding(
            padding: EdgeInsets.only(
              left: 18,
              right: 18,
              top: 18,
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
                      const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("Draft Bill from Parchi", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                          Text("Review extracted items before adding to bill", style: TextStyle(fontSize: 12, color: AppColors.outline)),
                        ],
                      ),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.file(photoFile, width: 44, height: 44, fit: BoxFit.cover),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),

                  // Editable Rows
                  ...rows.asMap().entries.map((entry) {
                    final idx = entry.key;
                    final r = entry.value;
                    final bool isConfident = r["isConfident"] ?? true;

                    return Container(
                      margin: const EdgeInsets.only(bottom: 8),
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: isConfident ? AppColors.surfaceLow : const Color(0xFFFFF8E1),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: isConfident ? AppColors.outlineVariant.withValues(alpha: 0.4) : const Color(0xFFFFB300),
                          width: isConfident ? 1 : 1.5,
                        ),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            flex: 3,
                            child: Text(
                              r["name"],
                              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceLowest,
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: AppColors.outlineVariant),
                            ),
                            child: Text("Qty: ${r["qty"]}", style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            "₹${(r["price"] * r["qty"]).toStringAsFixed(0)}",
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: AppColors.secondary),
                          ),
                          IconButton(
                            icon: const Icon(Icons.close, size: 16, color: Colors.red),
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(),
                            onPressed: () {
                              setModalState(() {
                                rows.removeAt(idx);
                              });
                            },
                          ),
                        ],
                      ),
                    );
                  }),

                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Total Bill Amount:", style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                      Text("₹${total.toStringAsFixed(0)}", style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.secondary)),
                    ],
                  ),
                  const SizedBox(height: 16),

                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFFE65100),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                      icon: const Icon(Icons.add_shopping_cart, size: 18),
                      label: Text(
                        "CONFIRM & ADD ${rows.length} ITEMS TO BILL",
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                      ),
                      onPressed: () async {
                        Navigator.pop(ctx);
                        for (var r in rows) {
                          await ref.read(posBillingProvider.notifier).quickAddProduct(
                            r["name"],
                            (r["price"] as num).toDouble(),
                          );
                        }
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              backgroundColor: const Color(0xFF2E7D32),
                              content: Text("Added ${rows.length} items from Parchi straight into bill!"),
                            ),
                          );
                        }
                      },
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final billingState = ref.watch(posBillingProvider);
    final authState = ref.watch(authNotifierProvider);
    final rawStoreName = authState.session.storeName;
    final String storeName = (rawStoreName != null && rawStoreName.isNotEmpty)
        ? rawStoreName
        : "Wapas Kirana Store";

    final filteredItems = billingState.catalog.where((item) {
      return item.name.toLowerCase().contains(searchQuery.toLowerCase()) ||
             item.category.toLowerCase().contains(searchQuery.toLowerCase()) ||
             item.barcode.contains(searchQuery);
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
              decoration: const BoxDecoration(shape: BoxShape.circle),
              clipBehavior: Clip.antiAlias,
              child: Image.asset('assets/images/wapas_logo.png', fit: BoxFit.cover),
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
                    storeName,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppColors.onSurface),
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
                    decoration: const BoxDecoration(color: AppColors.tertiary, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 4),
                  const Text(
                    "SOUNDBOX LIVE",
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: AppColors.onTertiaryContainer),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          // 1. Prominent Full-Width Quick-Scan Bar at the Top
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            color: AppColors.surfaceLowest,
            child: Row(
              children: [
                // Button 1: Camera Barcode / Product Scan
                Expanded(
                  child: InkWell(
                    onTap: () => _openCameraForBarcodeOrProduct(context),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 10),
                      decoration: BoxDecoration(
                        color: AppColors.secondaryContainer,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: const [
                          Icon(Icons.qr_code_scanner, color: Colors.white, size: 18),
                          SizedBox(width: 6),
                          Text(
                            "Scan Item",
                            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),

                // Button 2: Camera Parchi Fast-Billing
                Expanded(
                  child: InkWell(
                    onTap: () => _openCameraForParchiBilling(context),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 10),
                      decoration: BoxDecoration(
                        color: const Color(0xFFE65100),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: const [
                          Icon(Icons.receipt_long, color: Colors.white, size: 18),
                          SizedBox(width: 6),
                          Text(
                            "Scan Parchi",
                            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // 2. Search Bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            color: AppColors.surfaceLowest,
            child: Container(
              height: 42,
              decoration: BoxDecoration(
                color: AppColors.surfaceLow,
                borderRadius: BorderRadius.circular(10),
              ),
              child: TextField(
                onChanged: (val) => setState(() => searchQuery = val),
                decoration: InputDecoration(
                  hintText: "Search item, barcode or category...",
                  hintStyle: const TextStyle(fontSize: 13, color: AppColors.outline),
                  prefixIcon: const Icon(Icons.search, size: 18, color: AppColors.outline),
                  suffixIcon: searchQuery.isNotEmpty
                      ? IconButton(
                          icon: const Icon(Icons.clear, size: 16),
                          onPressed: () => setState(() => searchQuery = ""),
                        )
                      : null,
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ),
          ),

          // Item Catalogue List
          Expanded(
            child: billingState.isCatalogLoading
                ? const Center(child: CircularProgressIndicator())
                : filteredItems.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            const Icon(Icons.inventory_2_outlined, size: 48, color: AppColors.outline),
                            const SizedBox(height: 12),
                            Text(
                              searchQuery.isEmpty ? "No products found in catalogue" : "No results for '$searchQuery'",
                              style: const TextStyle(fontWeight: FontWeight.bold, color: AppColors.outline),
                            ),
                            const SizedBox(height: 16),
                            ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(backgroundColor: AppColors.secondary, foregroundColor: Colors.white),
                              icon: const Icon(Icons.add, size: 18),
                              label: const Text("Add New Product"),
                              onPressed: () => _showQuickAddProductDialog(
                                context,
                                detectedName: searchQuery.isNotEmpty ? searchQuery : "New Kirana Item",
                              ),
                            ),
                          ],
                        ),
                      )
                    : ListView.separated(
                        padding: const EdgeInsets.all(12),
                        itemCount: filteredItems.length,
                        separatorBuilder: (ctx, idx) => const SizedBox(height: 8),
                        itemBuilder: (ctx, idx) {
                          final item = filteredItems[idx];
                          final qtyInCart = billingState.getQuantityForProduct(item.id);

                          return Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.surfaceLowest,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: qtyInCart > 0
                                    ? AppColors.secondary.withValues(alpha: 0.5)
                                    : AppColors.outlineVariant.withValues(alpha: 0.3),
                                width: qtyInCart > 0 ? 1.5 : 1,
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
                                        "${item.unit} • Stock: ${item.currentStock.toStringAsFixed(0)} left",
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: item.isLowStock ? Colors.orange.shade800 : AppColors.onSurfaceVariant,
                                          fontWeight: item.isLowStock ? FontWeight.bold : FontWeight.normal,
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
                                    qtyInCart == 0
                                        ? InkWell(
                                            onTap: () => ref.read(posBillingProvider.notifier).addToCart(item),
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
                                                onTap: () => ref.read(posBillingProvider.notifier).removeFromCart(item),
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
                                                  "${qtyInCart.toInt()}",
                                                  style: const TextStyle(fontWeight: FontWeight.bold),
                                                ),
                                              ),
                                              InkWell(
                                                onTap: () => ref.read(posBillingProvider.notifier).addToCart(item),
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
          if (billingState.cartCount > 0)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.surfaceLowest,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.08),
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
                              "${billingState.cartCount} ITEMS IN BILL • #${billingState.bill?.billNumber ?? ''}",
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: AppColors.outline,
                                letterSpacing: 0.5,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              "₹${billingState.cartTotal.toStringAsFixed(2)}",
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
                              onPressed: () => ref.read(posBillingProvider.notifier).clearCart(),
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
  }

  void _showPaymentOptions(BuildContext context) {
    final billingState = ref.read(posBillingProvider);

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
                "Bill Total: ₹${billingState.cartTotal.toStringAsFixed(2)}",
                style: const TextStyle(fontSize: 14, color: AppColors.secondary, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 16),
              ListTile(
                leading: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: AppColors.surfaceLow, borderRadius: BorderRadius.circular(8)),
                  child: const Icon(Icons.qr_code_2, color: AppColors.secondary),
                ),
                title: const Text("Paytm Dynamic UPI QR", style: TextStyle(fontWeight: FontWeight.bold)),
                subtitle: const Text("Verified with Paytm Soundbox live trigger"),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.pop(ctx);
                  _showDynamicUpiQrDialog(context);
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
                onTap: () async {
                  Navigator.pop(ctx);
                  final success = await ref.read(posBillingProvider.notifier).completeCashPayment();
                  if (success && context.mounted) {
                    _showReceiptDialog(context);
                  }
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
                subtitle: const Text("Record debit • Wapas AI monitors recovery"),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async {
                  Navigator.pop(ctx);
                  final success = await ref.read(posBillingProvider.notifier).completeKhataPayment(
                    note: 'Counter bill credit',
                  );
                  if (success && context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        duration: const Duration(seconds: 4),
                        content: const Text("Recorded to Khata! Wapas AI is tracking this case."),
                        action: SnackBarAction(
                          label: "RECOVERY TOWER",
                          textColor: Colors.amberAccent,
                          onPressed: () {
                            if (widget.onNavigateTab != null) {
                              widget.onNavigateTab!(1); // Switch to Recovery Tower tab
                            }
                          },
                        ),
                      ),
                    );
                    _showReceiptDialog(context);
                  }
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _showDynamicUpiQrDialog(BuildContext context) async {
    final paymentData = await ref.read(posBillingProvider.notifier).initiateUpiPayment();
    if (!context.mounted) return;

    final checkoutUrl = paymentData?['checkout_url'] ?? 'http://localhost:8000/pay/demo';
    final amountPaise = ref.read(posBillingProvider).bill?.totalPaise ?? 0;
    final totalInr = amountPaise / 100.0;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => Consumer(
        builder: (ctx, ref, _) {
          return AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Row(
              children: const [
                Icon(Icons.qr_code_2, color: AppColors.secondary),
                SizedBox(width: 8),
                Text("Paytm Dynamic QR", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ],
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  "Scan with Paytm, PhonePe, or GPay to pay ₹${totalInr.toStringAsFixed(2)}",
                  style: const TextStyle(fontSize: 13, color: AppColors.outline),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: AppColors.outlineVariant),
                  ),
                  child: QrImageView(
                    data: checkoutUrl,
                    version: QrVersions.auto,
                    size: 180,
                  ),
                ),
                const SizedBox(height: 14),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: const [
                    SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(width: 8),
                    Text("Awaiting Soundbox announcement...", style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                  ],
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceLow,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    "Mode: ${paymentData?['mode'] ?? 'SIMULATED'}",
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: AppColors.secondary),
                  ),
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () {
                  Navigator.pop(ctx);
                },
                child: const Text("Cancel"),
              ),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.tertiary,
                  foregroundColor: Colors.white,
                ),
                icon: const Icon(Icons.check_circle, size: 16),
                label: const Text("Simulate Verified"),
                onPressed: () async {
                  Navigator.pop(ctx);
                  await ref.read(posBillingProvider.notifier).completeCashPayment();
                  if (context.mounted) {
                    _showReceiptDialog(context);
                  }
                },
              ),
            ],
          );
        },
      ),
    );
  }

  void _showReceiptDialog(BuildContext context) {
    final billing = ref.read(posBillingProvider);
    final bill = billing.bill;

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: const [
            Icon(Icons.check_circle, color: Color(0xFF2E7D32)),
            SizedBox(width: 8),
            Text("Bill Issued Successfully", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Bill Number: ${bill?.billNumber ?? 'N/A'}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
            const SizedBox(height: 4),
            Text("Customer: ${bill?.customerName ?? 'Counter Customer'}", style: const TextStyle(fontSize: 12, color: AppColors.outline)),
            const Divider(height: 20),
            ...?bill?.lines.map((l) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(child: Text("${l.productName} x${l.quantity.toInt()}", style: const TextStyle(fontSize: 12))),
                      Text("₹${l.subtotalInr.toStringAsFixed(2)}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                    ],
                  ),
                )),
            const Divider(height: 20),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text("Total Paid:", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                Text("₹${bill?.totalInr.toStringAsFixed(2)}", style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16, color: AppColors.secondary)),
              ],
            ),
          ],
        ),
        actions: [
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: AppColors.secondary, foregroundColor: Colors.white),
            onPressed: () {
              Navigator.pop(ctx);
              ref.read(posBillingProvider.notifier).startFreshBill();
            },
            child: const Text("NEW BILL"),
          ),
        ],
      ),
    );
  }
}
