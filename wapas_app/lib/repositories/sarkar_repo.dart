import '../core/network/api_client.dart';
import '../models/sarkar_models.dart';

abstract class SarkarRepo {
  Future<SarkarAskResponse> ask(String message, {String? audioBase64, String? mimeType});
  Future<void> confirmAction(String actionId, String token);
}

class HttpSarkarRepo implements SarkarRepo {
  final ApiClient _client;

  HttpSarkarRepo(this._client);

  @override
  Future<SarkarAskResponse> ask(String message, {String? audioBase64, String? mimeType}) async {
    final payload = {
      'message': message,
      'audio_base64': ?audioBase64,
      'mime_type': ?mimeType,
    };
    final res = await _client.post('/api/merchant/sarkar/ask', body: payload);
    return SarkarAskResponse.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<void> confirmAction(String actionId, String token) async {
    final payload = {
      'confirmation_token': token,
    };
    await _client.post('/api/merchant/sarkar/actions/$actionId/confirm', body: payload);
  }
}
