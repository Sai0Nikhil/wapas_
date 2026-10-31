import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/models/sarkar_models.dart';
import 'package:wapas_app/repositories/sarkar_repo.dart';

class FakeSarkarRepo implements SarkarRepo {
  bool confirmCalled = false;

  @override
  Future<SarkarAskResponse> ask(String message, {String? audioBase64, String? mimeType}) async {
    if (message.contains("received 10 kg")) {
      return SarkarAskResponse(
        status: 'NEEDS_CONFIRMATION',
        engine: 'DETERMINISTIC_TYPED_ROUTER',
        message: 'Prepared stock receipt for 10 kg of Atta.',
        confirmation: SarkarPendingAction(
          actionId: 'act_sarkar_001',
          token: 'token_secret_123',
          summary: 'Receive 10 kg of Atta into inventory',
        ),
        toolTrace: [
          SarkarToolTraceItem(
            tool: 'prepare_stock_receipt',
            version: '2026.1',
            correlationId: 'corr_101',
            arguments: {'message': message},
            result: {'status': 'PENDING_CONFIRMATION'},
          ),
        ],
        input: SarkarInputTrace(
          mode: 'TEXT',
          provider: 'none',
          latencyMs: 12,
        ),
      );
    }

    return SarkarAskResponse(
      status: 'SUCCESS',
      engine: 'DETERMINISTIC_TYPED_ROUTER',
      message: "Today's sales stand at ₹14,240 across 32 counter bills.",
      data: {'sales_inr': 14240.0, 'bills_count': 32},
      toolTrace: [
        SarkarToolTraceItem(
          tool: 'inspect_business_summary',
          version: '2026.1',
          correlationId: 'corr_102',
          arguments: {},
          result: {'sales': 14240.0},
        ),
      ],
      input: SarkarInputTrace(
        mode: 'TEXT',
        provider: 'Sarvam',
        model: 'saaras:v3',
        language: 'en',
        latencyMs: 45,
      ),
    );
  }

  @override
  Future<void> confirmAction(String actionId, String token) async {
    confirmCalled = true;
  }
}

void main() {
  group('SarkarRepo Tests', () {
    test('FakeSarkarRepo handles queries and traces', () async {
      final fake = FakeSarkarRepo();
      final res = await fake.ask('Summary today');

      expect(res.status, 'SUCCESS');
      expect(res.engine, 'DETERMINISTIC_TYPED_ROUTER');
      expect(res.message, contains('₹14,240'));
      expect(res.toolTrace.first.tool, 'inspect_business_summary');
      expect(res.input?.latencyMs, 45);
    });

    test('FakeSarkarRepo provides confirmation card on mutating action', () async {
      final fake = FakeSarkarRepo();
      final res = await fake.ask('We received 10 kg of Atta');

      expect(res.needsConfirmation, isTrue);
      expect(res.confirmation?.actionId, 'act_sarkar_001');
      expect(res.confirmation?.summary, contains('10 kg of Atta'));

      await fake.confirmAction(res.confirmation!.actionId, res.confirmation!.token);
      expect(fake.confirmCalled, isTrue);
    });
  });
}
