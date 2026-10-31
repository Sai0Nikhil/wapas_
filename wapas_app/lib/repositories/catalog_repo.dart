import '../core/network/api_client.dart';
import '../models/catalog_models.dart';

abstract class CatalogRepo {
  Future<List<ProductModel>> getProducts({String? query, String? category});
  Future<ProductModel?> lookupByBarcode(String barcode);
  Future<ProductModel> addProduct(Map<String, dynamic> data);
  Future<void> adjustStock(String productId, double delta, String reason);
  Future<List<StockMovementModel>> getMovements({String? productId});
}

class HttpCatalogRepo implements CatalogRepo {
  final ApiClient _client;

  HttpCatalogRepo(this._client);

  @override
  Future<List<ProductModel>> getProducts({String? query, String? category}) async {
    final params = <String, dynamic>{
      if (query != null && query.isNotEmpty) 'q': query,
      if (category != null && category.isNotEmpty) 'category': category,
      'limit': 100,
    };
    final res = await _client.get('/api/merchant/catalog/products', queryParams: params);
    if (res is Map<String, dynamic> && res['items'] is List) {
      return (res['items'] as List)
          .map((p) => ProductModel.fromJson(p as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<ProductModel?> lookupByBarcode(String barcode) async {
    try {
      final res = await _client.get(
        '/api/merchant/catalog/products/lookup',
        queryParams: {'barcode': barcode},
      );
      if (res is Map<String, dynamic>) {
        return ProductModel.fromJson(res);
      }
    } catch (_) {}
    return null;
  }

  @override
  Future<ProductModel> addProduct(Map<String, dynamic> data) async {
    final res = await _client.post('/api/merchant/catalog/products', body: data);
    return ProductModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<void> adjustStock(String productId, double delta, String reason) async {
    final idempotencyKey = _client.generateIdempotencyKey('stock');
    final payload = {
      'delta': delta,
      'reason': reason,
      'idempotency_key': idempotencyKey,
    };
    await _client.post(
      '/api/merchant/catalog/products/$productId/stock-adjustments',
      body: payload,
    );
  }

  @override
  Future<List<StockMovementModel>> getMovements({String? productId}) async {
    final params = <String, dynamic>{
      'product_id': ?productId,
      'limit': 50,
    };
    final res = await _client.get('/api/merchant/catalog/movements', queryParams: params);
    if (res is Map<String, dynamic> && res['movements'] is List) {
      return (res['movements'] as List)
          .map((m) => StockMovementModel.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    return [];
  }
}
