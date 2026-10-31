import '../core/network/api_client.dart';
import '../models/recovery_models.dart';

abstract class RecoveryRepo {
  Future<RecoveryStateData> fetchState();
  Future<CaseDetailData> fetchCaseDetail(String caseId);
  Future<Map<String, dynamic>> fetchEvidence(String caseId);
  Future<String> approveCase(String caseId);
  Future<String> skipCase(String caseId);
  Future<bool> demoPay(String caseId);
  Future<bool> replayWebhook(String caseId);
  Future<bool> resetIncident();
}

class HttpRecoveryRepo implements RecoveryRepo {
  final ApiClient _client;

  HttpRecoveryRepo(this._client);

  @override
  Future<RecoveryStateData> fetchState() async {
    final res = await _client.get('/api/state');
    return RecoveryStateData.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<CaseDetailData> fetchCaseDetail(String caseId) async {
    final res = await _client.get('/api/cases/$caseId');
    return CaseDetailData.fromJson(res as Map<String, dynamic>);
  }

  @override
  Future<Map<String, dynamic>> fetchEvidence(String caseId) async {
    final res = await _client.get('/api/cases/$caseId/evidence');
    return res is Map<String, dynamic> ? res : {};
  }

  @override
  Future<String> approveCase(String caseId) async {
    final res = await _client.post('/api/owner/approve/$caseId');
    if (res is Map<String, dynamic> && res['state'] != null) {
      return res['state'].toString();
    }
    return 'APPROVED';
  }

  @override
  Future<String> skipCase(String caseId) async {
    final res = await _client.post('/api/owner/skip/$caseId');
    if (res is Map<String, dynamic> && res['state'] != null) {
      return res['state'].toString();
    }
    return 'SKIPPED';
  }

  @override
  Future<bool> demoPay(String caseId) async {
    final res = await _client.post('/api/demo/pay/$caseId');
    return res is Map<String, dynamic> && res['ok'] == true;
  }

  @override
  Future<bool> replayWebhook(String caseId) async {
    final res = await _client.post('/api/demo/duplicate-callback/$caseId');
    return res is Map<String, dynamic> && res['ok'] == true;
  }

  @override
  Future<bool> resetIncident() async {
    final res = await _client.post('/api/demo/reset-incident');
    return res is Map<String, dynamic> && res['ok'] == true;
  }
}
