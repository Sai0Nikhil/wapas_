import '../core/network/api_client.dart';
import '../models/sound_models.dart';

abstract class SoundRepo {
  Future<SoundDeviceModel> registerDevice(String deviceKey);
  Future<List<SoundEventModel>> getEvents(String deviceKey, {int limit = 50});
  Future<void> acknowledgeEvent(String deviceKey, int eventId);
}

class HttpSoundRepo implements SoundRepo {
  final ApiClient _client;

  HttpSoundRepo(this._client);

  @override
  Future<SoundDeviceModel> registerDevice(String deviceKey) async {
    final payload = {'device_key': deviceKey};
    final res = await _client.post('/api/merchant/sound/device', body: payload);
    return SoundDeviceModel.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<List<SoundEventModel>> getEvents(String deviceKey, {int limit = 50}) async {
    final params = {
      'device_key': deviceKey,
      'limit': limit,
    };
    final res = await _client.get('/api/merchant/sound/events', queryParams: params);
    if (res is Map<String, dynamic> && res['events'] is List) {
      return (res['events'] as List)
          .map((e) => SoundEventModel.fromJson(e as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<void> acknowledgeEvent(String deviceKey, int eventId) async {
    final payload = {
      'device_key': deviceKey,
      'event_id': eventId,
    };
    await _client.post('/api/merchant/sound/events/ack', body: payload);
  }
}
