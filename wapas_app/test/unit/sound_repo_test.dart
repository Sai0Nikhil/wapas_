import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/models/sound_models.dart';
import 'package:wapas_app/repositories/sound_repo.dart';

class FakeSoundRepo implements SoundRepo {
  bool ackCalled = false;

  @override
  Future<SoundDeviceModel> registerDevice(String deviceKey) async {
    return SoundDeviceModel(
      deviceKey: deviceKey,
      cursor: 10,
      soundDefault: 'ACTIVE',
    );
  }

  @override
  Future<List<SoundEventModel>> getEvents(String deviceKey, {int limit = 50}) async {
    return [
      SoundEventModel(
        id: 11,
        paymentId: 'pay_xyz123',
        sourceType: 'COUNTER_BILL',
        amountPaise: 24500,
        currency: 'INR',
        verifiedAt: '2026-10-31T10:00:00Z',
      ),
    ];
  }

  @override
  Future<void> acknowledgeEvent(String deviceKey, int eventId) async {
    ackCalled = true;
  }
}

void main() {
  group('SoundRepo Tests', () {
    test('FakeSoundRepo registers device and retrieves events', () async {
      final fake = FakeSoundRepo();
      final dev = await fake.registerDevice('test-device-uuid');

      expect(dev.deviceKey, 'test-device-uuid');
      expect(dev.cursor, 10);

      final events = await fake.getEvents('test-device-uuid');
      expect(events.length, 1);
      expect(events.first.amountInr, 245.0);
      expect(events.first.id, 11);

      await fake.acknowledgeEvent('test-device-uuid', 11);
      expect(fake.ackCalled, isTrue);
    });
  });
}
