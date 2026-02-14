import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import 'config.dart';
import 'main.dart'; // Import to use central theme colors

class AdminDashboard extends StatefulWidget {
  const AdminDashboard({super.key});

  @override
  State<AdminDashboard> createState() => _AdminDashboardState();
}

class _AdminDashboardState extends State<AdminDashboard> {
  bool _isLoggedIn = false;
  String? _token;
  bool _isLoading = true;
  Map<String, dynamic> _kpis = {};
  List<dynamic> _serviceUsage = [];
  List<dynamic> _trends = [];
  List<dynamic> _geoData = [];
  List<dynamic> _fallbackTrends = [];
  List<dynamic> _confidenceDist = [];
  List<dynamic> _ussdStats = [];
  List<dynamic> _intents = [];

  @override
  void initState() {
    super.initState();
    _checkLoginStatus();
  }

  Future<void> _checkLoginStatus() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString('admin_token');
    if (token != null) {
      setState(() {
        _isLoggedIn = true;
        _token = token;
      });
      _fetchData();
    } else {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _login(String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('${AppConfig.adminBaseUrl}/api/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'username': username, 'password': password}),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('admin_token', data['access_token']);
        setState(() {
          _isLoggedIn = true;
          _token = data['access_token'];
        });
        _fetchData();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invalid credentials')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e')),
      );
    }
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('admin_token');
    setState(() {
      _isLoggedIn = false;
      _token = null;
    });
  }

  Future<void> _exportCSV() async {
    if (_token == null) return;
    final url = Uri.parse('${AppConfig.adminBaseUrl}/api/export/csv?table=messages');
    if (await canLaunchUrl(url)) {
      await launchUrl(url, mode: LaunchMode.externalApplication);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not launch export URL')),
      );
    }
  }

  Future<void> _fetchData() async {
    if (_token == null) return;
    setState(() => _isLoading = true);
    
    final headers = {'Authorization': 'Bearer $_token'};
    final baseUrl = '${AppConfig.adminBaseUrl}/api';

    try {
      // 1. Try to fetch standard analytics from existing backend
      final responses = await Future.wait([
        http.get(Uri.parse('$baseUrl/stats'), headers: headers).timeout(const Duration(seconds: 5)),
        http.get(Uri.parse('$baseUrl/geo'), headers: headers).timeout(const Duration(seconds: 5)),
        http.get(Uri.parse('$baseUrl/trends'), headers: headers).timeout(const Duration(seconds: 5)),
      ]);

      if (responses.every((r) => r.statusCode == 200)) {
        final statsData = jsonDecode(responses[0].body);
        setState(() {
          _kpis = statsData['kpis'] ?? {};
          _intents = statsData['intents'] ?? [];
          _fallbackTrends = statsData['fallback_trends'] ?? [];
          _confidenceDist = statsData['confidence_dist'] ?? [];
          _ussdStats = statsData['ussd_stats'] ?? [];
          
          _geoData = jsonDecode(responses[1].body);
          _trends = jsonDecode(responses[2].body);
        });
      }
    } catch (e) {
      debugPrint("Standard analytics unavailable: $e");
    }

    try {
      // 2. Fetch live interaction data from the proxy backend
      final liveResponse = await http.get(
        Uri.parse('${AppConfig.backendBaseUrl}/analytics/data'),
      ).timeout(const Duration(seconds: 5));

      if (liveResponse.statusCode == 200) {
        final List<dynamic> liveData = jsonDecode(liveResponse.body);
        // We'll use this data to update KPIs locally if standard ones are missing
        if (_kpis.isEmpty) {
          setState(() {
            _kpis = {
              'total_messages': liveData.length,
              'unique_users': liveData.map((d) => d['sender']).toSet().length,
              'active_today': liveData.length, // Simplified for now
            };
          });
        }
      }
    } catch (e) {
      debugPrint("Live analytics unavailable: $e");
    }

    setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    if (!_isLoggedIn) return Scaffold(body: _LoginView(onLogin: _login));
    if (_isLoading) return const Scaffold(body: Center(child: CircularProgressIndicator(color: kPrimaryGreen)));

    return Scaffold(
      backgroundColor: kBackgroundBeige,
      appBar: AppBar(
        title: const Text('Admin Analytics Dashboard (Anonymized Data)', 
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
        backgroundColor: kPrimaryGreen,
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.download), 
            tooltip: 'Export CSV',
            onPressed: () => _exportCSV(),
          ),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _fetchData),
          IconButton(icon: const Icon(Icons.logout), onPressed: _logout),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildKPISection(),
            const SizedBox(height: 24),
            LayoutBuilder(
              builder: (context, constraints) {
                if (constraints.maxWidth > 900) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: _buildChartCard("Service Usage Breakdown", _buildServiceBarChart())),
                      const SizedBox(width: 20),
                      Expanded(child: _buildChartCard("Message Trends (Last 7 Days)", _buildTrendLineChart())),
                      const SizedBox(width: 20),
                      Expanded(child: _buildChartCard("Fallback Trends (Last 7 Days)", _buildFallbackChart())),
                    ],
                  );
                } else {
                  return Column(
                    children: [
                      _buildChartCard("Service Usage Breakdown", _buildServiceBarChart()),
                      const SizedBox(height: 20),
                      _buildChartCard("Message Trends (Last 7 Days)", _buildTrendLineChart()),
                      const SizedBox(height: 20),
                      _buildChartCard("Fallback Trends (Last 7 Days)", _buildFallbackChart()),
                    ],
                  );
                }
              },
            ),
            const SizedBox(height: 20),
            LayoutBuilder(
              builder: (context, constraints) {
                if (constraints.maxWidth > 900) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: _buildChartCard("County-wise Distribution", _buildGeoChart())),
                      const SizedBox(width: 20),
                      Expanded(child: _buildChartCard("Top Intents & Confidence", _buildIntentTable())),
                    ],
                  );
                } else {
                  return Column(
                    children: [
                      _buildChartCard("County-wise Distribution", _buildGeoChart()),
                      const SizedBox(height: 20),
                      _buildChartCard("Top Intents & Confidence", _buildIntentTable()),
                    ],
                  );
                }
              },
            ),
            const SizedBox(height: 20),
            LayoutBuilder(
              builder: (context, constraints) {
                if (constraints.maxWidth > 900) {
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: _buildChartCard("Confidence Distribution", _buildConfidenceChart())),
                      const SizedBox(width: 20),
                      Expanded(child: _buildChartCard("USSD Popularity", _buildUSSDChart())),
                    ],
                  );
                } else {
                  return Column(
                    children: [
                      _buildChartCard("Confidence Distribution", _buildConfidenceChart()),
                      const SizedBox(height: 20),
                      _buildChartCard("USSD Popularity", _buildUSSDChart()),
                    ],
                  );
                }
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConfidenceChart() {
    if (_confidenceDist.isEmpty) return const Center(child: Text("No confidence data"));
    return Column(
      children: _confidenceDist.map((item) {
        return Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(
            children: [
              SizedBox(width: 60, child: Text(item['range'])),
              Expanded(
                child: LinearProgressIndicator(
                  value: item['count'] / (_kpis['total_messages'] ?? 1),
                  color: kPrimaryGreen,
                  backgroundColor: kBackgroundBeige,
                  minHeight: 10,
                ),
              ),
              const SizedBox(width: 10),
              Text("${item['count']}"),
            ],
          ),
        );
      }).toList(),
    );
  }

  Widget _buildUSSDChart() {
    if (_ussdStats.isEmpty) return const Center(child: Text("No USSD data"));
    return ListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: _ussdStats.length,
      itemBuilder: (context, i) {
        final item = _ussdStats[i];
        return ListTile(
          title: Text(item['intent']),
          trailing: Text("${item['count']} hits"),
          dense: true,
        );
      },
    );
  }

  Widget _buildGeoChart() {
    if (_geoData.isEmpty) return const Center(child: Text("No county data available"));
    return ListView.separated(
      itemCount: _geoData.length,
      separatorBuilder: (_, __) => const Divider(),
      itemBuilder: (context, i) {
        final item = _geoData[i];
        return ListTile(
          title: Text(item['county'] ?? 'Unknown'),
          trailing: Text("${item['count']} users", style: const TextStyle(fontWeight: FontWeight.bold)),
          dense: true,
        );
      },
    );
  }

  Widget _buildKPISection() {
    return Wrap(
      spacing: 16,
      runSpacing: 16,
      children: [
        _KPICard(title: "Total Users", value: "${_kpis['total_users'] ?? 0}", icon: Icons.people),
        _KPICard(title: "Total Messages", value: "${_kpis['total_messages'] ?? 0}", icon: Icons.message),
        _KPICard(title: "Total Sessions", value: "${_kpis['total_sessions'] ?? 0}", icon: Icons.forum),
        _KPICard(title: "Fallback Rate", value: "${_kpis['fallback_rate'] ?? 0}%", icon: Icons.warning_amber, color: kAccentRed),
      ],
    );
  }

  Widget _buildChartCard(String title, Widget chart) {
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: Colors.grey.shade300)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: kPrimaryGreen)),
            const SizedBox(height: 24),
            SizedBox(height: 300, child: chart),
          ],
        ),
      ),
    );
  }

  Widget _buildServiceBarChart() {
    if (_serviceUsage.isEmpty) return const Center(child: Text("No data available"));
    
    double maxCount = 0;
    for (var e in _serviceUsage) {
      double val = (e['count'] ?? 0).toDouble();
      if (val > maxCount) maxCount = val;
    }
    if (maxCount == 0) maxCount = 10;

    return BarChart(
      BarChartData(
        alignment: BarChartAlignment.spaceAround,
        maxY: maxCount * 1.2,
        barGroups: _serviceUsage.asMap().entries.map((e) {
          return BarChartGroupData(
            x: e.key,
            barRods: [
              BarChartRodData(
                toY: (e.value['count'] ?? 0).toDouble(), 
                color: kPrimaryGreen, 
                width: 20,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
              )
            ],
          );
        }).toList(),
        titlesData: FlTitlesData(
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                int index = value.toInt();
                if (index < 0 || index >= _serviceUsage.length) return const SizedBox();
                String name = _serviceUsage[index]['service_name']?.toString() ?? '';
                return Padding(
                  padding: const EdgeInsets.only(top: 8.0),
                  child: Text(name.split(' ').first, style: const TextStyle(fontSize: 10)),
                );
              },
            ),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true, 
              reservedSize: 30,
              getTitlesWidget: (value, meta) => Text(value.toInt().toString(), style: const TextStyle(fontSize: 10)),
            )
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        gridData: const FlGridData(show: false),
        borderData: FlBorderData(show: false),
      ),
    );
  }

  Widget _buildTrendLineChart() {
    if (_trends.isEmpty) return const Center(child: Text("No data available"));
    
    double maxVal = 0;
    for (var e in _trends) {
      double val = (e['count'] ?? 0).toDouble();
      if (val > maxVal) maxVal = val;
    }
    if (maxVal == 0) maxVal = 10;

    return LineChart(
      LineChartData(
        maxY: maxVal * 1.2,
        lineBarsData: [
          LineChartBarData(
            spots: _trends.asMap().entries.map((e) {
              return FlSpot(e.key.toDouble(), (e.value['count'] ?? 0).toDouble());
            }).toList(),
            isCurved: true,
            color: kPrimaryGreen,
            barWidth: 3,
            dotData: const FlDotData(show: true),
            belowBarData: BarAreaData(show: true, color: kPrimaryGreen.withOpacity(0.1)),
          ),
        ],
        titlesData: FlTitlesData(
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                int index = value.toInt();
                if (index < 0 || index >= _trends.length) return const SizedBox();
                String dateStr = _trends[index]['date']?.toString() ?? '';
                String label = dateStr.length >= 10 ? dateStr.substring(5) : dateStr;
                return Padding(
                  padding: const EdgeInsets.only(top: 8.0),
                  child: Text(label, style: const TextStyle(fontSize: 10)),
                );
              },
            ),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true, 
              reservedSize: 30,
              getTitlesWidget: (value, meta) => Text(value.toInt().toString(), style: const TextStyle(fontSize: 10)),
            )
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        gridData: const FlGridData(show: true, drawVerticalLine: false),
        borderData: FlBorderData(show: false),
      ),
    );
  }

  Widget _buildFallbackChart() {
    if (_fallbackTrends.isEmpty) return const Center(child: Text("No data available"));
    
    double maxVal = 0;
    for (var e in _fallbackTrends) {
      double val = (e['count'] ?? 0).toDouble();
      if (val > maxVal) maxVal = val;
    }
    if (maxVal == 0) maxVal = 10;

    return LineChart(
      LineChartData(
        maxY: maxVal * 1.2,
        lineBarsData: [
          LineChartBarData(
            spots: _fallbackTrends.asMap().entries.map((e) {
              return FlSpot(e.key.toDouble(), (e.value['count'] ?? 0).toDouble());
            }).toList(),
            isCurved: true,
            color: kAccentRed,
            barWidth: 3,
            dotData: const FlDotData(show: true),
            belowBarData: BarAreaData(show: true, color: kAccentRed.withOpacity(0.1)),
          ),
        ],
        titlesData: FlTitlesData(
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                int index = value.toInt();
                if (index < 0 || index >= _fallbackTrends.length) return const SizedBox();
                String dateStr = _fallbackTrends[index]['date']?.toString() ?? '';
                String label = dateStr.length >= 10 ? dateStr.substring(5) : dateStr;
                return Padding(
                  padding: const EdgeInsets.only(top: 8.0),
                  child: Text(label, style: const TextStyle(fontSize: 10)),
                );
              },
            ),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true, 
              reservedSize: 30,
              getTitlesWidget: (value, meta) => Text(value.toInt().toString(), style: const TextStyle(fontSize: 10)),
            )
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        gridData: const FlGridData(show: true, drawVerticalLine: false),
        borderData: FlBorderData(show: false),
      ),
    );
  }

  Widget _buildIntentTable() {
    if (_intents.isEmpty) return const Center(child: Text("No data available"));
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Intent')),
          DataColumn(label: Text('Usage Count')),
          DataColumn(label: Text('Avg Confidence')),
        ],
        rows: _intents.map((i) {
          return DataRow(cells: [
            DataCell(Text(i['intent'] ?? 'unknown')),
            DataCell(Text(i['count'].toString())),
            DataCell(Text("${((i['avg_confidence'] ?? 0) * 100).toStringAsFixed(1)}%")),
          ]);
        }).toList(),
      ),
    );
  }
}

class _KPICard extends StatelessWidget {
  final String title;
  final String value;
  final IconData icon;
  final Color color;

  const _KPICard({required this.title, required this.value, required this.icon, this.color = kPrimaryGreen});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 200,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.shade300),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 28),
          const SizedBox(height: 16),
          Text(title, style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
        ],
      ),
    );
  }
}

class _LoginView extends StatefulWidget {
  final Function(String, String) onLogin;
  const _LoginView({required this.onLogin});

  @override
  State<_LoginView> createState() => _LoginViewState();
}

class _LoginViewState extends State<_LoginView> {
  final _userController = TextEditingController();
  final _passController = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBackgroundBeige,
      body: Center(
        child: Container(
          width: 400,
          padding: const EdgeInsets.all(40),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.1), blurRadius: 20)],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.admin_panel_settings, size: 64, color: kPrimaryGreen),
              const SizedBox(height: 24),
              const Text("Admin Portal", style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: kPrimaryGreen)),
              const SizedBox(height: 8),
              const Text("Msaidizi Mkononi Management", style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 32),
              TextField(
                controller: _userController,
                decoration: const InputDecoration(labelText: 'Username', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _passController,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Password', border: OutlineInputBorder()),
              ),
              const SizedBox(height: 32),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: () => widget.onLogin(_userController.text, _passController.text),
                  style: ElevatedButton.styleFrom(backgroundColor: kPrimaryGreen, foregroundColor: Colors.white),
                  child: const Text("LOGIN", style: TextStyle(fontWeight: FontWeight.bold)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
