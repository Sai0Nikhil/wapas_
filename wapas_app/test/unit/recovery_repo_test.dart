import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/models/recovery_models.dart';
import 'package:wapas_app/repositories/recovery_repo.dart';

class FakeRecoveryRepo implements RecoveryRepo {
  bool approveCalled = false;
  bool skipCalled = false;

  @override
  Future<RecoveryStateData> fetchState() async {
    return RecoveryStateData(
      merchant: 'Sharma Kirana',
      gateway: 'paytm',
      llm: true,
      sarvam: true,
      counts: RecoveryCounts(
        flagged: 3,
        contacted: 2,
        paid: 1,
        waitingOwner: 1,
        stoppedByPolicy: 0,
        unknown: 0,
        recoveredInr: 1450.0,
        recoveredFmt: '₹1,450',
      ),
      cases: [
        RecoveryCaseSummary(
          id: 'case_001',
          name: 'Suresh Gupta',
          customerId: 'cust_001',
          language: 'hi',
          languageName: 'Hindi',
          amount: 1450.0,
          amountFmt: '₹1,450',
          state: 'WAITING_OWNER',
          diagnosis: 'Bank technical decline',
          confidence: 0.94,
          messagesSent: 0,
        ),
      ],
    );
  }

  @override
  Future<CaseDetailData> fetchCaseDetail(String caseId) async {
    return CaseDetailData(
      summary: RecoveryCaseSummary(
        id: caseId,
        name: 'Suresh Gupta',
        customerId: 'cust_001',
        language: 'hi',
        languageName: 'Hindi',
        amount: 1450.0,
        amountFmt: '₹1,450',
        state: 'WAITING_OWNER',
        confidence: 0.94,
        messagesSent: 0,
      ),
      decision: CaseDecisionData(
        diagnosis: 'UPI decline',
        chosenAction: 'WHATSAPP_LINK',
        confidence: 0.94,
        reasoner: 'RuleReasoner',
      ),
      policy: [
        CasePolicyItem(outcome: 'ASK_OWNER', rule: 'HIGH_VALUE_THRESHOLD', version: '2026.1'),
      ],
      actions: [],
    );
  }

  @override
  Future<Map<String, dynamic>> fetchEvidence(String caseId) async {
    return {'telemetry': 'ok'};
  }

  @override
  Future<String> approveCase(String caseId) async {
    approveCalled = true;
    return 'APPROVED';
  }

  @override
  Future<String> skipCase(String caseId) async {
    skipCalled = true;
    return 'SKIPPED';
  }

  @override
  Future<bool> demoPay(String caseId) async => true;

  @override
  Future<bool> replayWebhook(String caseId) async => true;

  @override
  Future<bool> resetIncident() async => true;
}

void main() {
  group('RecoveryRepo and Notifier Tests', () {
    test('FakeRecoveryRepo fetches live state and counts', () async {
      final fake = FakeRecoveryRepo();
      final data = await fake.fetchState();

      expect(data.merchant, 'Sharma Kirana');
      expect(data.gateway, 'paytm');
      expect(data.counts.paid, 1);
      expect(data.cases.length, 1);
      expect(data.cases.first.isWaitingOwner, isTrue);

      final approveRes = await fake.approveCase('case_001');
      expect(approveRes, 'APPROVED');
      expect(fake.approveCalled, isTrue);

      final detail = await fake.fetchCaseDetail('case_001');
      expect(detail.policy.first.outcome, 'ASK_OWNER');
      expect(detail.policy.first.rule, 'HIGH_VALUE_THRESHOLD');
    });
  });
}
