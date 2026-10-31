class ProductModel {
  final String id;
  final String name;
  final String category;
  final double price;
  final String unit;
  final String barcode;
  final double currentStock;
  final double minStockAlert;
  final bool isActive;

  ProductModel({
    required this.id,
    required this.name,
    required this.category,
    required this.price,
    required this.unit,
    required this.barcode,
    required this.currentStock,
    required this.minStockAlert,
    required this.isActive,
  });

  factory ProductModel.fromJson(Map<String, dynamic> json) {
    return ProductModel(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? '').toString(),
      category: (json['category'] ?? 'General').toString(),
      price: (json['price'] as num?)?.toDouble() ?? 0.0,
      unit: (json['unit'] ?? 'each').toString(),
      barcode: (json['barcode'] ?? '').toString(),
      currentStock: (json['current_stock'] as num?)?.toDouble() ?? 0.0,
      minStockAlert: (json['min_stock_alert'] as num?)?.toDouble() ?? 0.0,
      isActive: json['is_active'] != false,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'category': category,
        'price': price,
        'unit': unit,
        'barcode': barcode,
        'current_stock': currentStock,
        'min_stock_alert': minStockAlert,
        'is_active': isActive,
      };

  bool get isLowStock => currentStock <= minStockAlert;
}

class StockMovementModel {
  final String id;
  final String productId;
  final String productName;
  final double delta;
  final String reason;
  final double balanceAfter;
  final String createdAt;

  StockMovementModel({
    required this.id,
    required this.productId,
    required this.productName,
    required this.delta,
    required this.reason,
    required this.balanceAfter,
    required this.createdAt,
  });

  factory StockMovementModel.fromJson(Map<String, dynamic> json) {
    return StockMovementModel(
      id: (json['id'] ?? '').toString(),
      productId: (json['product_id'] ?? '').toString(),
      productName: (json['product_name'] ?? '').toString(),
      delta: (json['delta'] as num?)?.toDouble() ?? 0.0,
      reason: (json['reason'] ?? '').toString(),
      balanceAfter: (json['balance_after'] as num?)?.toDouble() ?? 0.0,
      createdAt: (json['created_at'] ?? '').toString(),
    );
  }
}
