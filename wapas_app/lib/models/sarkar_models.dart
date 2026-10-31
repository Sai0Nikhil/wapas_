class SarkarInputTrace {
  final String mode; // TEXT, TURN_BASED_STT
  final String provider; // Sarvam, none
  final String? model;
  final String? language;
  final int latencyMs;

  SarkarInputTrace({
    required this.mode,
    required this.provider,
    this.model,
    this.language,
    required this.latencyMs,
  });

  factory SarkarInputTrace.fromJson(Map<String, dynamic> json) {
    return SarkarInputTrace(
      mode: (json['mode'] ?? 'TEXT').toString(),
      provider: (json['provider'] ?? 'none').toString(),
      model: json['model']?.toString(),
      language: json['language']?.toString(),
      latencyMs: (json['latency_ms'] as num?)?.toInt() ?? 0,
    );
  }
}

class SarkarToolTraceItem {
  final String tool;
  final String version;
  final String correlationId;
  final Map<String, dynamic> arguments;
  final dynamic result;

  SarkarToolTraceItem({
    required this.tool,
    required this.version,
    required this.correlationId,
    required this.arguments,
    required this.result,
  });

  factory SarkarToolTraceItem.fromJson(Map<String, dynamic> json) {
    return SarkarToolTraceItem(
      tool: (json['tool'] ?? '').toString(),
      version: (json['version'] ?? '').toString(),
      correlationId: (json['correlation_id'] ?? '').toString(),
      arguments: json['arguments'] is Map<String, dynamic> ? json['arguments'] as Map<String, dynamic> : {},
      result: json['result'],
    );
  }
}

class SarkarPendingAction {
  final String actionId;
  final String token;
  final String summary;

  SarkarPendingAction({
    required this.actionId,
    required this.token,
    required this.summary,
  });

  factory SarkarPendingAction.fromJson(Map<String, dynamic> json) {
    return SarkarPendingAction(
      actionId: (json['action_id'] ?? '').toString(),
      token: (json['confirmation_token'] ?? json['token'] ?? '').toString(),
      summary: (json['summary'] ?? 'Action requires confirmation').toString(),
    );
  }
}

class SarkarAskResponse {
  final String status; // SUCCESS, NEEDS_CONFIRMATION, NEEDS_CLARIFICATION
  final String engine;
  final String message;
  final Map<String, dynamic>? data;
  final SarkarPendingAction? confirmation;
  final List<SarkarToolTraceItem> toolTrace;
  final SarkarInputTrace? input;
  final String? transcript;

  SarkarAskResponse({
    required this.status,
    required this.engine,
    required this.message,
    this.data,
    this.confirmation,
    this.toolTrace = const [],
    this.input,
    this.transcript,
  });

  factory SarkarAskResponse.fromJson(Map<String, dynamic> json) {
    return SarkarAskResponse(
      status: (json['status'] ?? 'SUCCESS').toString(),
      engine: (json['engine'] ?? 'DETERMINISTIC_TYPED_ROUTER').toString(),
      message: (json['message'] ?? '').toString(),
      data: json['data'] is Map<String, dynamic> ? json['data'] as Map<String, dynamic> : null,
      confirmation: json['confirmation'] is Map<String, dynamic>
          ? SarkarPendingAction.fromJson(json['confirmation'] as Map<String, dynamic>)
          : null,
      toolTrace: (json['tool_trace'] as List?)
              ?.map((t) => SarkarToolTraceItem.fromJson(t as Map<String, dynamic>))
              .toList() ??
          [],
      input: json['input'] is Map<String, dynamic>
          ? SarkarInputTrace.fromJson(json['input'] as Map<String, dynamic>)
          : null,
      transcript: json['transcript']?.toString(),
    );
  }

  bool get needsConfirmation => status == 'NEEDS_CONFIRMATION' && confirmation != null;
  bool get needsClarification => status == 'NEEDS_CLARIFICATION';
}
