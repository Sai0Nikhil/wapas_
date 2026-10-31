import '../core/network/api_client.dart';
import '../models/order_models.dart';

abstract class OrdersRepo {
  Future<List<StoreOrderModel>> getOrders();
  Future<void> fulfillOrder(String orderId);
  Future<Map<String, dynamic>> getStorefrontQr();
}

class HttpOrdersRepo implements OrdersRepo {
  final ApiClient _client;

  HttpOrdersRepo(this._client);

  @override
  Future<List<StoreOrderModel>> getOrders() async {
    final res = await _client.get('/api/merchant/orders');
    if (res is Map<String, dynamic> && res['orders'] is List) {
      return (res['orders'] as List)
          .map((o) => StoreOrderModel.fromJson(o as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<void> fulfillOrder(String orderId) async {
    await _client.post('/api/merchant/orders/$orderId/fulfill');
  }

  @override
  Future<Map<String, dynamic>> getStorefrontQr() async {
    final res = await _client.get('/api/merchant/storefront/qr');
    return res is Map<String, dynamic> ? res : {};
  }
}
