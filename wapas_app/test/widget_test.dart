import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/main.dart';

void main() {
  testWidgets('Wapas App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const WapasMerchantApp());
    expect(find.text('Billing'), findsOneWidget);
    expect(find.text('Recovery'), findsOneWidget);
    expect(find.text('Khata'), findsOneWidget);
    expect(find.text('Sarkar AI'), findsOneWidget);
    expect(find.text('Soundbox'), findsOneWidget);
  });
}
