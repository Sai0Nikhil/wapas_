class ApiException implements Exception {
  final int statusCode;
  final String message;
  final String messageHindi;
  final String? detail;
  final bool isNetworkError;
  final bool isAuthError;
  final bool isForbidden;

  ApiException({
    required this.statusCode,
    required this.message,
    required this.messageHindi,
    this.detail,
    this.isNetworkError = false,
    this.isAuthError = false,
    this.isForbidden = false,
  });

  factory ApiException.fromResponse(int statusCode, dynamic body) {
    String detailStr = '';
    if (body is Map<String, dynamic>) {
      detailStr = (body['detail'] ?? body['message'] ?? '').toString();
    } else if (body is String) {
      detailStr = body;
    }

    if (statusCode == 401) {
      return ApiException(
        statusCode: 401,
        message: detailStr.isNotEmpty ? detailStr : 'Sign-in session expired. Please log in again.',
        messageHindi: 'साइन-इन सत्र समाप्त हो गया है। कृपया पुनः लॉग इन करें।',
        detail: detailStr,
        isAuthError: true,
      );
    }

    if (statusCode == 403) {
      return ApiException(
        statusCode: 403,
        message: detailStr.isNotEmpty ? detailStr : 'Action available only to the store owner.',
        messageHindi: 'यह कार्रवाई केवल स्टोर के मालिक के लिए उपलब्ध है।',
        detail: detailStr,
        isForbidden: true,
      );
    }

    if (statusCode == 404) {
      return ApiException(
        statusCode: 404,
        message: detailStr.isNotEmpty ? detailStr : 'The requested item was not found.',
        messageHindi: 'अनुरोधित आइटम नहीं मिला।',
        detail: detailStr,
      );
    }

    if (statusCode == 409) {
      return ApiException(
        statusCode: 409,
        message: detailStr.isNotEmpty ? detailStr : 'Conflict occurred. Duplicate entity or stale state.',
        messageHindi: 'विवाद उत्पन्न हुआ। डुप्लिकेट या पुराना डेटा।',
        detail: detailStr,
      );
    }

    if (statusCode == 422) {
      return ApiException(
        statusCode: 422,
        message: detailStr.isNotEmpty ? detailStr : 'Invalid input data.',
        messageHindi: 'अमान्य इनपुट डेटा।',
        detail: detailStr,
      );
    }

    if (statusCode >= 500) {
      return ApiException(
        statusCode: statusCode,
        message: detailStr.isNotEmpty ? detailStr : 'Server error occurred. Please try again later.',
        messageHindi: 'सर्वर त्रुटि। कृपया थोड़ी देर बाद पुनः प्रयास करें।',
        detail: detailStr,
      );
    }

    return ApiException(
      statusCode: statusCode,
      message: detailStr.isNotEmpty ? detailStr : 'Unexpected error ($statusCode).',
      messageHindi: 'अप्रत्याशित त्रुटि ($statusCode)।',
      detail: detailStr,
    );
  }

  factory ApiException.networkError([dynamic error]) {
    final String errorText = error?.toString() ?? '';
    final bool isTimeout = errorText.toLowerCase().contains('timeout');

    return ApiException(
      statusCode: 0,
      message: isTimeout
          ? 'Network request timed out. Please check server connectivity.'
          : 'Unable to connect to Wapas backend. Please check your network and server URL.',
      messageHindi: isTimeout
          ? 'नेटवर्क अनुरोध का समय समाप्त हो गया। कृपया सर्वर कनेक्टिविटी की जांच करें।'
          : 'सर्वर से कनेक्ट करने में असमर्थ। कृपया नेटवर्क और सर्वर URL जांचें।',
      detail: errorText,
      isNetworkError: true,
    );
  }

  @override
  String toString() => 'ApiException($statusCode): $message';
}
